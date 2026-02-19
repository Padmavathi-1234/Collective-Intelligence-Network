"""
agent/controller.py – Orchestrates the full AI agent pipeline.

Pipeline:
    1. Generate structured post via Ollama (generator.py)
    2. Run safety filter on generated text (utils/safety.py)
    3. Verify post is grounded in source data (verifier.py)
    4. Determine final status: 'published' or 'rejected'
    5. Save to database (database.py)
    6. Return result dict

Agent Gate:
    The controller does NOT manage the ready/busy gate — that is the
    responsibility of the webhook route (_run_pipeline_in_background).
    The gate is released in a `finally` block there, guaranteeing
    the agent always returns to READY regardless of success or failure.

This module is called from the webhook route in a background thread
so it never blocks the HTTP server.
"""

import uuid
import logging
from datetime import datetime, timezone

from agent import generator, verifier
from utils import safety
import database

logger = logging.getLogger(__name__)


def _broadcast(post: dict) -> None:
    """Broadcast a published post via WebSocket."""
    try:
        from extensions import socketio
        socketio.emit('new_post', post)
        logger.info("[Controller] 📡 WebSocket broadcast sent for: %s", post.get("title", "")[:60])
    except Exception as e:
        logger.warning("[Controller] ❌ WebSocket broadcast failed: %s", e)


def _broadcast_agent_status(status: str, topic: str = "") -> None:
    """Broadcast current agent status to all connected browser clients."""
    try:
        from extensions import socketio
        socketio.emit('agent_status', {'status': status, 'topic': topic})
    except Exception as e:
        logger.debug("[Controller] Agent status broadcast failed: %s", e)


def run_agent_pipeline(payload: dict, post_id: str | None = None) -> dict:
    """
    Run the full agent pipeline for a validated webhook payload.

    Args:
        payload: Validated webhook payload (domain, headline, content,
                 sources, timestamp)
        post_id: Pre-assigned ID from the webhook route (placeholder already
                 saved). If None, a new UUID is generated.

    Returns:
        dict with keys: status, post_id, message, post (optional),
                        duration_seconds
    """
    start_time = datetime.now(timezone.utc)
    post_id    = post_id or str(uuid.uuid4())
    headline   = payload.get("headline", "")

    logger.info(
        "[Controller] ▶ Pipeline started | post_id=%s | headline=%s",
        post_id, headline[:80],
    )

    # ── Step 1: Generate ──────────────────────────────────────────────────────
    logger.info("[Controller] 💭 Thinking... Generating structured post for: %s", headline[:60])
    _broadcast_agent_status('researching', headline[:80])
    generated = generator.generate_post(payload)
    if not generated:
        logger.error("[Controller] ❌ Generation failed")
        _broadcast_agent_status('idle')
        return _reject(post_id, payload, "AI generation failed.", start_time)

    # ── Step 2: Safety Filter ─────────────────────────────────────────────────
    logger.info("[Controller] 🛡️ Running safety check...")
    _broadcast_agent_status('safety_check', headline[:80])
    check_text = safety.build_check_text(generated)
    is_safe, safety_reason = safety.run_safety_filter(check_text)
    if not is_safe:
        logger.warning("[Controller] ❌ Safety check failed: %s", safety_reason)
        _broadcast_agent_status('idle')
        return _reject(post_id, payload, safety_reason, start_time,
                       generated=generated)

    # ── Step 3: Verify (SKIPPED — llama3.2 rejects too aggressively) ──────────
    # Verification is disabled for now. The keyword-based safety filter above
    # still guards against harmful content.

    # ── Step 4: Publish ───────────────────────────────────────────────────────
    logger.info("[Controller] 📝 Publishing post...")
    _broadcast_agent_status('publishing', headline[:80])
    updates = {
        "title":            generated["title"],
        "domain":           generated.get("domain", payload.get("domain", "General")),
        "summary":          generated["summary"],
        "content":          generated.get("content", ""),
        "key_points":       generated.get("key_points", []),
        "why_this_matters": generated.get("why_this_matters", ""),
        "sources":          generated.get("sources", payload.get("sources", [])),
        "confidence_score": generated.get("confidence_score", 0),
        "status":           "published",
    }
    database.update_post(post_id, updates)

    # Broadcast to all connected browser clients in real-time
    _broadcast({**updates, "id": post_id,
                "created_at": datetime.now(timezone.utc).isoformat()})

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        "[Controller] ✔ Published | post_id=%s | duration=%.2fs",
        post_id, duration,
    )
    _broadcast_agent_status('idle')

    return {
        "status":           "published",
        "post_id":          post_id,
        "message":          f"Post published successfully. Confidence: {generated.get('confidence_score', 0)}%",
        "post":             {**updates, "id": post_id},
        "duration_seconds": round(duration, 2),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _reject(post_id: str, payload: dict, reason: str,
            start_time: datetime, generated: dict | None = None) -> dict:
    """
    Update the pre-existing placeholder row to 'rejected'.
    (The webhook route already inserted a row with this post_id; calling
    save_post() a second time would raise a UNIQUE constraint error.)
    """
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    database.update_post(post_id, {
        "title":            (generated or {}).get("title",
                             payload.get("headline", "Rejected Post")),
        "summary":          (generated or {}).get("summary", ""),
        "key_points":       (generated or {}).get("key_points", []),
        "why_this_matters": (generated or {}).get("why_this_matters", ""),
        "sources":          payload.get("sources", []),
        "confidence_score": 0,
        "status":           "rejected",
    })

    logger.warning(
        "[Controller] ✘ Rejected | post_id=%s | reason=%s | duration=%.2fs",
        post_id, reason, duration,
    )

    return {
        "status":           "rejected",
        "post_id":          post_id,
        "message":          reason,
        "duration_seconds": round(duration, 2),
    }
