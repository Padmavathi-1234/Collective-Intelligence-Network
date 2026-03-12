"""
agent/controller.py – Orchestrates the full AI agent pipeline.

Pipeline (Multi-Agent – Independent Posts):
    1. Run multiple AI agents in parallel via Groq (multi_agent.py)
    2. Run safety filter on EACH agent's output
    3. Each safe agent creates its OWN separate post in the DB
    4. All posts are broadcast via WebSocket simultaneously
    5. Return combined result dict

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

from agent import multi_agent
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
    Run the full multi-agent pipeline for a validated webhook payload.

    Each agent's result becomes its own separate post in the database
    and is broadcast to the frontend independently.

    Args:
        payload: Validated webhook payload (domain, headline, content,
                 sources, timestamp)
        post_id: Pre-assigned ID from the webhook route (placeholder already
                 saved). If None, a new UUID is generated.

    Returns:
        dict with keys: status, post_ids, message, agents_count,
                        duration_seconds
    """
    start_time = datetime.now(timezone.utc)
    primary_post_id = post_id or str(uuid.uuid4())
    headline = payload.get("headline", "")

    logger.info(
        "[Controller] ▶ Pipeline started | primary_post_id=%s | headline=%s",
        primary_post_id, headline[:80],
    )

    # ── Step 1: Multi-Agent Generation ────────────────────────────────────────
    logger.info("[Controller] 🧠 Dispatching multi-agent analysis for: %s", headline[:60])
    _broadcast_agent_status('researching', headline[:80])
    agent_results = multi_agent.run_multi_agent(payload)

    if not agent_results:
        logger.error("[Controller] ❌ All agents failed — no results returned")
        _broadcast_agent_status('idle')
        return _reject(primary_post_id, payload, "All AI agents failed to generate analysis.", start_time)

    logger.info(
        "[Controller] 📊 Received %d agent analyses", len(agent_results),
    )

    # ── Step 2: Safety Filter (per-agent) ─────────────────────────────────────
    logger.info("[Controller] 🛡️ Running safety checks on each agent output...")
    _broadcast_agent_status('safety_check', headline[:80])

    safe_results = []
    for result in agent_results:
        check_text = safety.build_check_text(result)
        is_safe, safety_reason = safety.run_safety_filter(check_text)
        if is_safe:
            safe_results.append(result)
        else:
            logger.warning(
                "[Controller] ⚠️ Agent '%s' (%s) output blocked by safety filter: %s",
                result.get("role"), result.get("model"), safety_reason,
            )

    if not safe_results:
        logger.warning("[Controller] ❌ All agent outputs failed safety filter")
        _broadcast_agent_status('idle')
        return _reject(
            primary_post_id, payload,
            "All AI agent outputs were blocked by the safety filter.",
            start_time,
            agent_analyses=agent_results,
        )

    # ── Step 3: Create Separate Post per Agent ────────────────────────────────
    logger.info(
        "[Controller] 📝 Publishing %d separate posts (one per agent)...",
        len(safe_results),
    )
    _broadcast_agent_status('publishing', headline[:80])

    published_ids = []

    # Retrieve verification data from the primary placeholder
    primary_record = database.get_post(primary_post_id)
    v_score = primary_record.get("verification_score", 0) if primary_record else 0
    v_status = primary_record.get("verification_status", "pending") if primary_record else "pending"

    for i, result in enumerate(safe_results):
        if i == 0:
            # First agent reuses the existing placeholder post_id
            agent_post_id = primary_post_id
        else:
            # Subsequent agents get new post IDs
            agent_post_id = str(uuid.uuid4())

        post_data = {
            "title": result["title"],
            "domain": result.get("domain", payload.get("domain", "General")),
            "summary": result["summary"],
            "content": result.get("content", ""),
            "key_points": result.get("key_points", []),
            "why_this_matters": result.get("why_this_matters", ""),
            "sources": result.get("sources", payload.get("sources", [])),
            "confidence_score": result.get("confidence_score", 0),
            "status": "published",
            "agent_analyses": [result],  # Store just this agent's analysis
        }

        if i == 0:
            # Update the existing placeholder
            database.update_post(agent_post_id, post_data)
        else:
            # Create a new post for this agent
            new_post = {
                **post_data,
                "id": agent_post_id,
                "verification_score": v_score,
                "verification_status": v_status,
            }
            database.save_post(new_post)

        # Fetch the complete record from DB for broadcast
        final_post = database.get_post(agent_post_id)
        if not final_post:
            final_post = {
                **post_data,
                "id": agent_post_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        # Broadcast each post to connected browser clients
        _broadcast(final_post)
        published_ids.append(agent_post_id)

        logger.info(
            "[Controller] ✅ Agent '%s' (%s) → post_id=%s | confidence=%d",
            result["role"], result["model"], agent_post_id,
            result.get("confidence_score", 0),
        )

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        "[Controller] ✔ Published %d posts | duration=%.2fs",
        len(published_ids), duration,
    )
    _broadcast_agent_status('idle')

    return {
        "status": "published",
        "post_id": primary_post_id,
        "post_ids": published_ids,
        "message": (
            f"Published {len(published_ids)} separate agent posts. "
            f"Agents: {', '.join(r['role'] for r in safe_results)}."
        ),
        "agents_count": len(published_ids),
        "duration_seconds": round(duration, 2),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _reject(post_id: str, payload: dict, reason: str,
            start_time: datetime, agent_analyses: list | None = None) -> dict:
    """
    Update the pre-existing placeholder row to 'rejected'.
    """
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    update_data = {
        "title":            payload.get("headline", "Rejected Post"),
        "summary":          "",
        "key_points":       [],
        "why_this_matters": "",
        "sources":          payload.get("sources", []),
        "confidence_score": 0,
        "status":           "rejected",
    }
    if agent_analyses:
        update_data["agent_analyses"] = agent_analyses

    database.update_post(post_id, update_data)

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
