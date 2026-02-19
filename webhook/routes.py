"""
webhook/routes.py – Flask Blueprint for POST /webhook/update

Security:
    - X-Webhook-Token header authentication (HMAC-safe constant-time compare)
    - JSON payload validation via utils/validation.py
    - Duplicate headline detection via database.py

Flow:
    1. Authenticate token           → 401
    2. Parse JSON                   → 400
    3. Validate payload             → 400
    4. Duplicate check              → 200 (duplicate)
    5. Agent ready-check            → 503 if busy
    6. Pre-register placeholder row
    7. Acquire agent lock & spawn background thread
    8. Return 202 Accepted immediately

Agent Gate:
    The AI agent is modelled as a single-slot worker (READY / BUSY).
    While BUSY the webhook rejects all new requests with 503.
    The gate is released automatically when the pipeline finishes —
    whether the post is published, rejected, or an error is raised.
"""

import os
import uuid
import hmac
import logging
import threading
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from utils.validation import validate_payload
import database
from agent.controller import run_agent_pipeline
from agent.state import agent_state          # ← ready/busy gate

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__, url_prefix="/webhook")

# ─── Auth Helper ──────────────────────────────────────────────────────────────

def _get_secret() -> str:
    secret = os.getenv("WEBHOOK_SECRET", "")
    if not secret:
        logger.critical("[Webhook] WEBHOOK_SECRET is not set! All requests will be rejected.")
    return secret


def _token_valid(provided: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    expected = _get_secret()
    if not expected:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


# ─── Background Worker ────────────────────────────────────────────────────────

def _run_pipeline_in_background(payload: dict, post_id: str) -> None:
    """
    Run the full pipeline in a dedicated thread, then release the agent gate
    so the webhook can accept the next request.

    This is the ONLY place where agent_state.release() is called, guaranteeing
    that the gate is always freed — even if the pipeline raises an exception.
    """
    try:
        result = run_agent_pipeline(payload, post_id=post_id)
        logger.info(
            "[Webhook] Pipeline done | post_id=%s | status=%s | duration=%.2fs",
            result.get("post_id", post_id),
            result.get("status"),
            result.get("duration_seconds", 0),
        )
    except Exception as e:
        logger.error("[Webhook] Pipeline error for post_id=%s: %s", post_id, e)
    finally:
        # Always release — agent is READY again after this
        agent_state.release()


# ─── Route ────────────────────────────────────────────────────────────────────

@webhook_bp.route("/update", methods=["POST"])
def receive_update():
    """
    POST /webhook/update

    Headers required:
        X-Webhook-Token: <WEBHOOK_SECRET from .env>
        Content-Type: application/json

    Returns 202 immediately if the agent is READY; 503 if BUSY.
    """
    received_at = datetime.now(timezone.utc)
    logger.info(
        "[Webhook] ▶ Request received at %s from %s",
        received_at.isoformat(), request.remote_addr,
    )

    # ── 1. Authenticate ───────────────────────────────────────────────────────
    token = request.headers.get("X-Webhook-Token", "")
    if not token:
        logger.warning("[Webhook] ✘ 401 – Missing X-Webhook-Token header.")
        return jsonify({
            "status":  "error",
            "message": "Missing authentication token. Provide X-Webhook-Token header.",
        }), 401

    if not _token_valid(token):
        logger.warning("[Webhook] ✘ 401 – Invalid token from %s", request.remote_addr)
        return jsonify({
            "status":  "error",
            "message": "Invalid authentication token.",
        }), 401

    # ── 2. Parse JSON ─────────────────────────────────────────────────────────
    if not request.is_json:
        logger.warning("[Webhook] ✘ 400 – Non-JSON Content-Type.")
        return jsonify({
            "status":  "error",
            "message": "Request body must be JSON (Content-Type: application/json).",
        }), 400

    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        data = None

    if data is None:
        logger.warning("[Webhook] ✘ 400 – Malformed JSON body.")
        return jsonify({
            "status":  "error",
            "message": "Malformed JSON body.",
        }), 400

    # ── 3. Validate Payload ───────────────────────────────────────────────────
    valid, error_msg = validate_payload(data)
    if not valid:
        logger.warning("[Webhook] ✘ 400 – Validation failed: %s", error_msg)
        return jsonify({
            "status":  "error",
            "message": error_msg,
        }), 400

    # ── 4. Duplicate Detection ────────────────────────────────────────────────
    headline = data["headline"]
    if database.headline_exists(headline):
        logger.info("[Webhook] Duplicate headline ignored: %s", headline[:80])
        return jsonify({
            "status":  "duplicate",
            "message": "This headline has already been processed.",
            "post_id": None,
        }), 200

    # ── 5. Agent Ready-Check ──────────────────────────────────────────────────
    # try_acquire() atomically flips the gate to BUSY and returns True,
    # OR returns False if the agent is already processing another article.
    if not agent_state.try_acquire(headline=headline):
        current = agent_state.current_headline() or "unknown"
        logger.warning(
            "[Webhook] 503 – Agent busy (processing '%s'). Rejected: %s",
            current[:60], headline[:60],
        )
        return jsonify({
            "status":  "busy",
            "message": "AI agent is currently processing another article. Please retry later.",
            "current_headline": current,
        }), 503

    # ── 6. Pre-register placeholder ───────────────────────────────────────────
    post_id_hint = str(uuid.uuid4())
    placeholder = {
        "id":               post_id_hint,
        "title":            headline,
        "domain":           data.get("domain", "General"),
        "summary":          "",
        "key_points":       [],
        "why_this_matters": "",
        "sources":          data.get("sources", []),
        "confidence_score": 0,
        "status":           "processing",
    }
    database.save_post(placeholder)

    # ── 7. Spawn Background Pipeline ──────────────────────────────────────────
    thread = threading.Thread(
        target=_run_pipeline_in_background,
        args=(data, post_id_hint),
        daemon=True,
        name=f"agent-pipeline-{post_id_hint[:8]}",
    )
    thread.start()

    duration_ms = (datetime.now(timezone.utc) - received_at).total_seconds() * 1000
    logger.info(
        "[Webhook] 202 Accepted | headline=%s | gate_acquire_time=%.1fms",
        headline[:80], duration_ms,
    )

    # ── 8. Return Immediately ─────────────────────────────────────────────────
    return jsonify({
        "status":  "accepted",
        "message": "Agent is now processing your article. It is busy until the post is published.",
        "post_id": post_id_hint,
    }), 202
