"""
utils/safety.py – Content safety filter for the Collective Intelligence Network.

Blocks posts containing vulgar, hateful, violent, or anti-human content.
The filter is keyword-based for speed and offline operation, but is designed
to be swapped for an LLM-based moderation call in production.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ─── Blocklist ────────────────────────────────────────────────────────────────
# Organised by category for maintainability.
# Add terms in lowercase; matching is case-insensitive.

_HATE_TERMS = [
    r"\bkill\s+all\b", r"\bexterminate\b", r"\bgenocide\b",
    r"\bethnic\s+cleansing\b", r"\bsubhuman\b", r"\bvermin\b",
    r"\binfidel(s)?\b", r"\bdie\s+you\b",
]

_VIOLENCE_TERMS = [
    r"\bbomb\s+making\b", r"\bhow\s+to\s+make\s+a\s+bomb\b",
    r"\bterrorist\s+attack\b", r"\bmass\s+shooting\b",
    r"\bsuicide\s+bomb\b", r"\bbeheading\b",
]

_VULGAR_TERMS = [
    r"\bf[u\*]+ck\b", r"\bs[h\*]+it\b", r"\bc[u\*]+nt\b",
    r"\bb[i\*]+tch\b", r"\ba[s\*]+hole\b",
]

_ANTI_HUMAN_TERMS = [
    r"\bhuman\s+trafficking\b", r"\bchild\s+abuse\b",
    r"\bchild\s+pornography\b", r"\bsex\s+slave\b",
    r"\btorture\s+manual\b",
]

_ALL_PATTERNS = (
    [("hate speech", p) for p in _HATE_TERMS]
    + [("violent content", p) for p in _VIOLENCE_TERMS]
    + [("vulgar language", p) for p in _VULGAR_TERMS]
    + [("anti-human content", p) for p in _ANTI_HUMAN_TERMS]
)

_COMPILED = [(category, re.compile(pattern, re.IGNORECASE))
             for category, pattern in _ALL_PATTERNS]


# ─── Public API ───────────────────────────────────────────────────────────────

def run_safety_filter(text: str) -> tuple[bool, str | None]:
    """
    Check text for prohibited content.

    Args:
        text: The combined text to check (title + summary + key_points, etc.)

    Returns:
        (True, None)           – content is safe
        (False, reason_string) – content is blocked
    """
    for category, pattern in _COMPILED:
        if pattern.search(text):
            reason = f"Content blocked: matched {category} filter."
            logger.warning("[Safety] Blocked post – %s", reason)
            return False, reason

    return True, None


def build_check_text(post: dict) -> str:
    """Concatenate all text fields of a generated post for safety checking."""
    parts = [
        post.get("title", ""),
        post.get("summary", ""),
        post.get("why_this_matters", ""),
        " ".join(post.get("key_points", [])),
    ]
    return " ".join(parts)
