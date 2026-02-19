"""
agent/state.py – Thread-safe singleton that tracks whether the AI agent is
                 ready to accept a new job or currently busy.

Usage:
    from agent.state import agent_state

    # Webhook: check before accepting a request
    if not agent_state.try_acquire():
        return 503  # busy

    # Controller: release when done
    agent_state.release()

    # Anywhere: inspect current state
    agent_state.is_ready()   # True  → agent waiting for work
    agent_state.is_busy()    # True  → agent processing
    agent_state.current_headline()  # None or str
"""

import threading
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AgentState:
    """
    A simple boolean lock that models the agent as either READY or BUSY.

    Only ONE pipeline job may run at a time.  All other incoming webhook
    requests are rejected with 503 until release() is called.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._busy = False
        self._current_headline: str | None = None
        self._busy_since: datetime | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def try_acquire(self, headline: str = "") -> bool:
        """
        Atomically flip to BUSY if currently READY.

        Returns True  → caller acquired the lock (agent is now busy).
        Returns False → already busy; caller must reject the request.
        """
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            self._current_headline = headline
            self._busy_since = datetime.now(timezone.utc)
            logger.info(
                "[AgentState] → BUSY | headline=%s",
                (headline or "")[:80],
            )
            return True

    def release(self) -> None:
        """
        Mark the agent as READY again.  Call this when the pipeline finishes
        (whether the post was published, rejected, or errored).
        """
        with self._lock:
            if not self._busy:
                logger.warning("[AgentState] release() called while already READY — ignored.")
                return
            elapsed = (
                (datetime.now(timezone.utc) - self._busy_since).total_seconds()
                if self._busy_since
                else 0
            )
            logger.info(
                "[AgentState] → READY | was_processing='%s' | elapsed=%.1fs",
                (self._current_headline or "")[:80],
                elapsed,
            )
            self._busy = False
            self._current_headline = None
            self._busy_since = None

    def is_ready(self) -> bool:
        with self._lock:
            return not self._busy

    def is_busy(self) -> bool:
        with self._lock:
            return self._busy

    def current_headline(self) -> str | None:
        with self._lock:
            return self._current_headline

    def status_dict(self) -> dict:
        """Return a JSON-serialisable snapshot of the current state."""
        with self._lock:
            elapsed = None
            if self._busy and self._busy_since:
                elapsed = round(
                    (datetime.now(timezone.utc) - self._busy_since).total_seconds(), 1
                )
            return {
                "ready": not self._busy,
                "busy": self._busy,
                "current_headline": self._current_headline,
                "busy_since": self._busy_since.isoformat() if self._busy_since else None,
                "elapsed_seconds": elapsed,
            }


# ── Module-level singleton ────────────────────────────────────────────────────
agent_state: AgentState = AgentState()
