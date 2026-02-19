"""
database.py – SQLite-backed post storage for the Collective Intelligence Network.

Schema:
    posts(id, title, domain, summary, key_points, why_this_matters,
          sources, confidence_score, created_at, status)

All JSON array fields (key_points, sources) are stored as JSON strings.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "cin_posts.db")

# ─── Schema ───────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS posts (
    id                TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    domain            TEXT NOT NULL,
    summary           TEXT,
    content           TEXT,          -- Full long-form article
    key_points        TEXT,          -- JSON array
    why_this_matters  TEXT,
    sources           TEXT,          -- JSON array
    confidence_score  REAL DEFAULT 0,
    created_at        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'published',
    headline_hash     TEXT           -- normalised lowercase headline for dedup
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_headline_hash ON posts(headline_hash);
"""


# ─── Init ─────────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """Return a thread-safe SQLite connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Ensure the schema is up-to-date (e.g. add 'content' column if missing)."""
    try:
        cur = conn.execute("PRAGMA table_info(posts)")
        columns = [row["name"] for row in cur.fetchall()]
        if "content" not in columns:
            logger.info("[DB] Migrating schema: adding 'content' column to 'posts' table...")
            conn.execute("ALTER TABLE posts ADD COLUMN content TEXT")
            conn.commit()
    except Exception as e:
        logger.error("[DB] Migration failed: %s", e)


def init_db() -> None:
    """Create tables and indexes if they don't exist."""
    with get_connection() as conn:
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_INDEX_SQL)
        _migrate_schema(conn)
        conn.commit()
    logger.info("[DB] Initialised SQLite database at %s", DB_PATH)


# ─── Duplicate Detection ──────────────────────────────────────────────────────

def _normalise(headline: str) -> str:
    """Lowercase + strip whitespace for fuzzy dedup."""
    return headline.lower().strip()


def headline_exists(headline: str) -> bool:
    """
    Return True only if a post with this headline is already published or
    actively being processed. Rejected posts are allowed to be retried.
    """
    h = _normalise(headline)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM posts WHERE headline_hash = ? AND status IN ('published', 'processing') LIMIT 1",
            (h,)
        ).fetchone()
    return row is not None

def cleanup_stale_processing(max_age_minutes: int = 10) -> int:
    """
    Reset posts stuck in 'processing' status to 'rejected' so their
    headlines can be retried.

    If max_age_minutes == 0, ALL 'processing' rows are reset regardless of age
    (used on server startup to clear orphaned rows from previous crashed runs).
    Otherwise only rows older than max_age_minutes are reset.

    Returns the number of rows cleaned up.
    """
    from datetime import datetime, timezone, timedelta
    with get_connection() as conn:
        if max_age_minutes == 0:
            cur = conn.execute(
                "UPDATE posts SET status = 'rejected' WHERE status = 'processing'"
            )
        else:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()
            cur = conn.execute(
                "UPDATE posts SET status = 'rejected' WHERE status = 'processing' AND created_at < ?",
                (cutoff,)
            )
        conn.commit()
    count = cur.rowcount
    if count:
        age_desc = "all ages" if max_age_minutes == 0 else f"older than {max_age_minutes}m"
        logger.info("[DB] Cleaned up %d stale 'processing' posts (%s).", count, age_desc)
    return count


# ─── Write ────────────────────────────────────────────────────────────────────

def save_post(post: dict) -> None:
    """
    Insert a post record into the database.

    Expected keys:
        id, title, domain, summary, key_points (list), why_this_matters,
        sources (list), confidence_score, status
    Optional:
        created_at (ISO-8601 string; defaults to now)
    """
    created_at = post.get("created_at", datetime.utcnow().isoformat())
    headline_hash = _normalise(post.get("title", ""))

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO posts
                (id, title, domain, summary, content, key_points, why_this_matters,
                 sources, confidence_score, created_at, status, headline_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post["id"],
                post.get("title", ""),
                post.get("domain", "General"),
                post.get("summary", ""),
                post.get("content", ""),
                json.dumps(post.get("key_points", []), ensure_ascii=False),
                post.get("why_this_matters", ""),
                json.dumps(post.get("sources", []), ensure_ascii=False),
                post.get("confidence_score", 0),
                created_at,
                post.get("status", "published"),
                headline_hash,
            ),
        )
        conn.commit()
    logger.info("[DB] Saved post id=%s status=%s", post["id"], post.get("status"))


def update_post(post_id: str, updates: dict) -> None:
    """
    Update an existing post record by id.

    Only the fields present in `updates` are changed.
    Supports: title, domain, summary, key_points, why_this_matters,
              sources, confidence_score, status
    """
    field_map = {
        "title":            ("title",            lambda v: v),
        "domain":           ("domain",           lambda v: v),
        "summary":          ("summary",          lambda v: v),
        "content":          ("content",          lambda v: v),
        "key_points":       ("key_points",       lambda v: json.dumps(v, ensure_ascii=False)),
        "why_this_matters": ("why_this_matters", lambda v: v),
        "sources":          ("sources",          lambda v: json.dumps(v, ensure_ascii=False)),
        "confidence_score": ("confidence_score", lambda v: v),
        "status":           ("status",           lambda v: v),
    }

    set_clauses = []
    values = []
    for key, (col, transform) in field_map.items():
        if key in updates:
            set_clauses.append(f"{col} = ?")
            values.append(transform(updates[key]))

    if not set_clauses:
        return

    values.append(post_id)
    sql = f"UPDATE posts SET {', '.join(set_clauses)} WHERE id = ?"

    with get_connection() as conn:
        conn.execute(sql, values)
        conn.commit()
    logger.info("[DB] Updated post id=%s fields=%s", post_id, list(updates.keys()))




# ─── Read ─────────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["key_points"] = json.loads(d.get("key_points") or "[]")
    d["sources"] = json.loads(d.get("sources") or "[]")
    d.pop("headline_hash", None)
    return d


def get_all_posts(limit: int = 100) -> list[dict]:
    """Return the most recent posts, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_post(post_id: str) -> dict | None:
    """Return a single post by id, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_published_posts(limit: int = 100) -> list[dict]:
    """Return only published posts, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status = 'published' ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
