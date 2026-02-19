"""
feed_collector.py – Standalone feed collector for the Collective Intelligence Network.

Polls three source types and pushes updates to the webhook endpoint:
  1. RSS Feeds   – BBC, Reuters, TechCrunch, Ars Technica, etc.
  2. Reddit      – Top posts from configured subreddits (via PRAW)
  3. Nitter RSS  – Public Twitter content via Nitter's RSS (no API key needed)

Usage:
    python feed_collector.py

Environment variables (from .env):
    WEBHOOK_SECRET              – must match the Flask server's secret
    WEBHOOK_URL                 – default: http://localhost:5000/webhook/update
    REDDIT_CLIENT_ID            – from reddit.com/prefs/apps
    REDDIT_CLIENT_SECRET        – from reddit.com/prefs/apps
    REDDIT_USER_AGENT           – e.g. "CIN-FeedCollector/1.0 by YourUsername"
    FEED_POLL_INTERVAL_MINUTES  – default: 10
"""

import os
import time
import logging
import hashlib
import datetime
from typing import Iterator

import requests
import feedparser
from dotenv import load_dotenv

load_dotenv()

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("FeedCollector")

# ─── Config ───────────────────────────────────────────────────────────────────
WEBHOOK_URL    = os.getenv("WEBHOOK_URL", "http://localhost:5000/webhook/update")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
POLL_INTERVAL  = int(os.getenv("FEED_POLL_INTERVAL_MINUTES", "10")) * 60

# Seen-headline cache (in-memory; resets on restart — DB dedup is the real guard)
_SEEN: set[str] = set()


# ─── RSS Feeds ────────────────────────────────────────────────────────────────

RSS_SOURCES = [
    # (url, domain)
    ("https://feeds.bbci.co.uk/news/technology/rss.xml",          "Technology"),
    ("https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "Science"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml",               "Politics"),
    ("https://feeds.bbci.co.uk/news/health/rss.xml",              "Health"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml",            "Economics"),
    ("https://techcrunch.com/feed/",                              "Technology"),
    ("https://feeds.arstechnica.com/arstechnica/index",           "Technology"),
    ("https://www.theverge.com/rss/index.xml",                    "Technology"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "Technology"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",  "Science"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",   "Health"),
    ("https://feeds.reuters.com/reuters/technologyNews",          "Technology"),
    ("https://feeds.reuters.com/reuters/scienceNews",             "Science"),
    ("https://www.nasa.gov/rss/dyn/breaking_news.rss",            "Space"),
    ("https://www.wired.com/feed/rss",                            "Technology"),
    ("https://www.sciencedaily.com/rss/top/technology.xml",       "Technology"),
    ("https://www.sciencedaily.com/rss/top/science.xml",          "Science"),
    ("https://krebsonsecurity.com/feed/",                         "Security"),
    ("https://www.bleepingcomputer.com/feed/",                    "Security"),
]


def _parse_rss_entry(entry, domain: str) -> dict | None:
    """Convert a feedparser entry to a webhook payload."""
    headline = getattr(entry, "title", "").strip()
    content  = (
        getattr(entry, "summary", "")
        or getattr(entry, "description", "")
        or ""
    ).strip()
    link     = getattr(entry, "link", "")

    if not headline or not content:
        return None

    published = getattr(entry, "published_parsed", None)
    if published:
        ts = datetime.datetime(*published[:6], tzinfo=datetime.timezone.utc).isoformat()
    else:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return {
        "domain":    domain,
        "headline":  headline,
        "content":   content,
        "sources":   [link] if link else ["RSS feed"],
        "timestamp": ts,
    }


def collect_rss() -> Iterator[dict]:
    """Yield webhook payloads from all RSS sources."""
    for url, domain in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:   # top 5 per feed per cycle
                payload = _parse_rss_entry(entry, domain)
                if payload:
                    yield payload
        except Exception as e:
            logger.warning("[RSS] Error parsing %s: %s", url, e)


# ─── Reddit ───────────────────────────────────────────────────────────────────

REDDIT_SUBREDDITS = [
    ("technology",    "Technology"),
    ("worldnews",     "Politics"),
    ("science",       "Science"),
    ("cybersecurity", "Security"),
    ("space",         "Space"),
    ("economics",     "Economics"),
    ("health",        "Health"),
    ("environment",   "Environment"),
    ("energy",        "Energy"),
    ("MachineLearning", "Technology"),
    ("artificial",    "Technology"),
]


def _get_reddit_client():
    """Return a PRAW Reddit client, or None if credentials are missing."""
    client_id     = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    user_agent    = os.getenv("REDDIT_USER_AGENT", "CIN-FeedCollector/1.0")

    if not client_id or client_id == "YOUR_REDDIT_CLIENT_ID":
        logger.warning("[Reddit] Credentials not configured – skipping Reddit collection.")
        return None

    try:
        import praw
        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except ImportError:
        logger.warning("[Reddit] 'praw' not installed. Run: pip install praw")
        return None
    except Exception as e:
        logger.error("[Reddit] Failed to initialise PRAW client: %s", e)
        return None


def collect_reddit() -> Iterator[dict]:
    """Yield webhook payloads from configured subreddits."""
    reddit = _get_reddit_client()
    if not reddit:
        return

    for subreddit_name, domain in REDDIT_SUBREDDITS:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            for post in subreddit.hot(limit=5):
                if post.is_self and post.selftext:
                    content = post.selftext[:3000]
                elif post.url:
                    content = f"Reddit post linking to: {post.url}"
                else:
                    continue

                ts = datetime.datetime.fromtimestamp(
                    post.created_utc, tz=datetime.timezone.utc
                ).isoformat()

                yield {
                    "domain":    domain,
                    "headline":  post.title,
                    "content":   content,
                    "sources":   [f"https://reddit.com{post.permalink}"],
                    "timestamp": ts,
                }
        except Exception as e:
            logger.warning("[Reddit] Error fetching r/%s: %s", subreddit_name, e)


# ─── Nitter RSS (Twitter via Nitter) ─────────────────────────────────────────
# Nitter exposes RSS for hashtags and accounts without requiring an API key.
# Public Nitter instances may go offline; we try multiple.

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

NITTER_FEEDS = [
    # (path, domain)
    ("/search/rss?q=%23AI&f=tweets",          "Technology"),
    ("/search/rss?q=%23MachineLearning",      "Technology"),
    ("/search/rss?q=%23CyberSecurity",        "Security"),
    ("/search/rss?q=%23ClimateChange",        "Environment"),
    ("/search/rss?q=%23SpaceExploration",     "Space"),
    ("/search/rss?q=%23BreakingNews",         "Politics"),
    ("/Reuters/rss",                          "Politics"),
    ("/BBCWorld/rss",                         "Politics"),
    ("/NASAHubble/rss",                       "Space"),
    ("/WHO/rss",                              "Health"),
]


def _try_nitter_feed(path: str, domain: str) -> Iterator[dict]:
    """Try each Nitter instance for a given feed path."""
    for instance in NITTER_INSTANCES:
        url = f"{instance}{path}"
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                continue
            for entry in feed.entries[:3]:
                headline = getattr(entry, "title", "").strip()
                content  = getattr(entry, "summary", "").strip() or headline
                link     = getattr(entry, "link", url)

                if not headline:
                    continue

                published = getattr(entry, "published_parsed", None)
                ts = (
                    datetime.datetime(*published[:6], tzinfo=datetime.timezone.utc).isoformat()
                    if published
                    else datetime.datetime.now(datetime.timezone.utc).isoformat()
                )

                yield {
                    "domain":    domain,
                    "headline":  headline[:300],
                    "content":   content[:3000],
                    "sources":   [link],
                    "timestamp": ts,
                }
            break   # success — don't try other instances
        except Exception:
            continue   # try next instance


def collect_nitter() -> Iterator[dict]:
    """Yield webhook payloads from Nitter RSS feeds."""
    for path, domain in NITTER_FEEDS:
        yield from _try_nitter_feed(path, domain)


# ─── Dispatcher ───────────────────────────────────────────────────────────────

def _fingerprint(payload: dict) -> str:
    """Create a dedup fingerprint from headline."""
    return hashlib.md5(payload["headline"].lower().strip().encode()).hexdigest()


def _is_stale(payload: dict) -> bool:
    """Skip items older than 24 hours."""
    try:
        ts = datetime.datetime.fromisoformat(
            payload["timestamp"].replace("Z", "+00:00")
        )
        age = datetime.datetime.now(datetime.timezone.utc) - ts
        return age.total_seconds() > 86400
    except Exception:
        return False


def send_to_webhook(payload: dict) -> bool:
    """POST a payload to the webhook endpoint. Returns True on success.

    When the agent is busy (503), waits and retries up to MAX_BUSY_RETRIES
    times instead of dropping the article.
    """
    MAX_BUSY_RETRIES = 10
    BUSY_WAIT_SECS   = 30   # wait between 503 retries

    fp = _fingerprint(payload)
    if fp in _SEEN:
        return False
    if _is_stale(payload):
        logger.debug("[Collector] Skipping stale item: %s", payload["headline"][:60])
        return False

    for attempt in range(1, MAX_BUSY_RETRIES + 1):
        try:
            resp = requests.post(
                WEBHOOK_URL,
                json=payload,
                headers={
                    "X-Webhook-Token": WEBHOOK_SECRET,
                    "Content-Type":    "application/json",
                },
                timeout=15,
            )
            _SEEN.add(fp)

            if resp.status_code == 202:
                logger.info("[Collector] ✔ Sent: %s", payload["headline"][:80])
                return True
            elif resp.status_code == 200:
                logger.info("[Collector] ⟳ Duplicate (server): %s", payload["headline"][:60])
                return False
            elif resp.status_code == 503:
                # Agent is busy — wait and retry this same article
                logger.info(
                    "[Collector] ⏳ Agent busy — waiting %ds before retry (%d/%d): %s",
                    BUSY_WAIT_SECS, attempt, MAX_BUSY_RETRIES,
                    payload["headline"][:60],
                )
                time.sleep(BUSY_WAIT_SECS)
                continue   # retry the same article
            else:
                logger.warning("[Collector] ✘ Server returned %d: %s",
                               resp.status_code, resp.text[:100])
                return False

        except requests.exceptions.ConnectionError:
            logger.error("[Collector] Cannot reach webhook at %s – is the server running?", WEBHOOK_URL)
            return False
        except Exception as e:
            logger.error("[Collector] Error sending payload: %s", e)
            return False

    # Exhausted all retries
    logger.warning(
        "[Collector] ✘ Agent stayed busy for %d retries — skipping: %s",
        MAX_BUSY_RETRIES, payload["headline"][:60],
    )
    return False


# ─── Main Loop ────────────────────────────────────────────────────────────────

def run_collection_cycle() -> int:
    """Run one full collection cycle. Returns count of items sent."""
    sent = 0
    sources = [
        ("RSS",     collect_rss()),
        ("Reddit",  collect_reddit()),
        ("Nitter",  collect_nitter()),
    ]
    for source_name, generator in sources:
        for payload in generator:
            if send_to_webhook(payload):
                sent += 1
                time.sleep(1)   # gentle rate limiting between sends
    return sent


def main():
    logger.info("=" * 60)
    logger.info("  CIN Feed Collector starting")
    logger.info("  Webhook URL  : %s", WEBHOOK_URL)
    logger.info("  Poll interval: %d minutes", POLL_INTERVAL // 60)
    logger.info("  Reddit       : %s",
                "configured" if os.getenv("REDDIT_CLIENT_ID", "YOUR_REDDIT_CLIENT_ID")
                != "YOUR_REDDIT_CLIENT_ID" else "not configured (skipped)")
    logger.info("=" * 60)

    if not WEBHOOK_SECRET:
        logger.critical("WEBHOOK_SECRET is not set in .env – collector will be rejected by server.")

    cycle = 0
    while True:
        cycle += 1
        logger.info("[Collector] ── Cycle %d starting ──", cycle)
        try:
            sent = run_collection_cycle()
            logger.info("[Collector] ── Cycle %d complete | %d items sent ──", cycle, sent)
        except Exception as e:
            logger.error("[Collector] Cycle %d error: %s", cycle, e)

        logger.info("[Collector] Sleeping %d minutes until next cycle...", POLL_INTERVAL // 60)
        time.sleep(POLL_INTERVAL)


def start_collector_thread() -> None:
    """
    Launch the feed collector loop in a background daemon thread.
    Call this from app.py to auto-start the collector with the server.
    """
    import threading

    def _loop():
        # Small initial delay so the Flask server is fully up before first POST
        time.sleep(15)
        main()

    t = threading.Thread(target=_loop, name="feed-collector", daemon=True)
    t.start()
    logger.info("[Collector] Background thread started (first cycle in 15s).")


if __name__ == "__main__":
    main()
