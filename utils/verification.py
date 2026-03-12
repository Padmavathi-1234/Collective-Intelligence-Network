"""
utils/verification.py – Two-Stage Data Verification Layer for the CIN.

Stage 1: Deterministic checks (source credibility, multi-source confirmation, recency)
Stage 2: LLM-based content plausibility validation via Ollama

The verification layer runs BEFORE AI generation to ensure only reliable
data enters the intelligence pipeline.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2")

# Stage 1 thresholds
STAGE1_REJECT_THRESHOLD = 0.5

# Final combined thresholds
FINAL_VERIFIED_THRESHOLD      = 0.7
FINAL_LOW_CONFIDENCE_THRESHOLD = 0.5

# ─── Trusted Sources ─────────────────────────────────────────────────────────

TRUSTED_SOURCES = {
    "reuters.com":       0.95,
    "bbc.co.uk":         0.95,
    "bbc.com":           0.95,
    "techcrunch.com":    0.85,
    "theverge.com":      0.80,
    "nature.com":        0.95,
    "arxiv.org":         0.90,
    "github.com":        0.80,
    "nytimes.com":       0.90,
    "arstechnica.com":   0.85,
    "wired.com":         0.80,
    "sciencedaily.com":  0.85,
    "nasa.gov":          0.95,
    "who.int":           0.95,
    "reddit.com":        0.60,
    "krebsonsecurity.com": 0.85,
    "bleepingcomputer.com": 0.80,
}

DEFAULT_SOURCE_SCORE = 0.5


# ─── Stage 1: Source and Data Validation ──────────────────────────────────────

def get_source_score(url: str) -> float:
    """
    Extract domain from URL and return its credibility score.
    Unknown domains get a default score of 0.5.
    """
    try:
        parsed = urlparse(url)
        domain = (parsed.netloc or parsed.path).lower().strip()
        # Strip 'www.' prefix
        if domain.startswith("www."):
            domain = domain[4:]
        # Strip port
        if ":" in domain:
            domain = domain.split(":")[0]

        # Direct match
        if domain in TRUSTED_SOURCES:
            return TRUSTED_SOURCES[domain]

        # Check if domain is a subdomain of a trusted source
        for trusted_domain, score in TRUSTED_SOURCES.items():
            if domain.endswith(f".{trusted_domain}"):
                return score

        return DEFAULT_SOURCE_SCORE
    except Exception as e:
        logger.warning("[VERIFICATION] Error parsing URL '%s': %s", url, e)
        return DEFAULT_SOURCE_SCORE


def authenticate_source(url: str) -> bool:
    """
    Verify the source URL meets basic quality requirements:
      - Must use HTTPS
      - Domain must not be malformed
      - Domain must be non-empty
    """
    try:
        parsed = urlparse(url)

        # Must use HTTPS
        if parsed.scheme != "https":
            logger.debug("[VERIFICATION] Source rejected: not HTTPS – %s", url)
            return False

        # Domain must be present and valid
        domain = parsed.netloc
        if not domain or "." not in domain:
            logger.debug("[VERIFICATION] Source rejected: malformed domain – %s", url)
            return False

        return True
    except Exception:
        return False


def check_multi_source_confirmation(headline: str, db_conn) -> float:
    """
    Check if similar headlines already exist in the database.
    Extracts keywords from the headline and searches for matches.

    Returns:
        0.0  – no matches (completely new)
        0.3  – 1 match
        0.6  – 2 matches
        1.0  – 3+ matches
    """
    # Extract meaningful keywords (words > 3 chars, skip stop words)
    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all",
        "can", "had", "her", "was", "one", "our", "out", "has",
        "have", "been", "from", "this", "that", "with", "will",
        "they", "their", "what", "about", "which", "when", "make",
        "like", "just", "over", "such", "into", "than", "more",
        "some", "very", "after", "also", "most", "new", "says",
    }
    words = re.findall(r'\b[a-zA-Z]{4,}\b', headline.lower())
    keywords = [w for w in words if w not in stop_words]

    if not keywords:
        return 0.0

    total_matches = 0
    try:
        for keyword in keywords[:5]:  # Limit to 5 keywords for efficiency
            cursor = db_conn.execute(
                "SELECT COUNT(*) FROM posts WHERE title LIKE ? AND status = 'published'",
                (f"%{keyword}%",)
            )
            count = cursor.fetchone()[0]
            if count > 0:
                total_matches += 1
    except Exception as e:
        logger.warning("[VERIFICATION] Multi-source check failed: %s", e)
        return 0.0

    if total_matches >= 3:
        return 1.0
    elif total_matches == 2:
        return 0.6
    elif total_matches == 1:
        return 0.3
    return 0.0


def calculate_recency_score(published_at: str) -> float:
    """
    Score the freshness of the information.

    Returns:
        1.0  – less than 24 hours old
        0.8  – 1-3 days old
        0.6  – 3-7 days old
        0.3  – older than 7 days
    """
    try:
        ts = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age = now - ts

        hours = age.total_seconds() / 3600

        if hours < 24:
            return 1.0
        elif hours < 72:    # 3 days
            return 0.8
        elif hours < 168:   # 7 days
            return 0.6
        else:
            return 0.3
    except Exception as e:
        logger.warning("[VERIFICATION] Cannot parse timestamp '%s': %s", published_at, e)
        return 0.5  # neutral default


def compute_verification_score(payload: dict, db_conn) -> float:
    """
    Stage 1 – Compute a weighted verification score from all deterministic signals.

    Formula: (0.5 * source_score) + (0.3 * multi_source_score) + (0.2 * recency_score)

    Returns a value between 0 and 1.
    """
    sources = payload.get("sources", [])
    headline = payload.get("headline", "")
    timestamp = payload.get("timestamp", "")

    # Source credibility: use the best score among all provided sources
    if sources:
        source_score = max(get_source_score(url) for url in sources)
    else:
        source_score = DEFAULT_SOURCE_SCORE

    # Source authentication: check if at least one source is authenticated
    any_authenticated = any(authenticate_source(url) for url in sources) if sources else False
    if not any_authenticated:
        # Penalise score if no source passes authentication
        source_score *= 0.7

    # Multi-source confirmation
    multi_source_score = check_multi_source_confirmation(headline, db_conn)

    # Recency
    recency_score = calculate_recency_score(timestamp)

    # Weighted composite
    score = (0.5 * source_score) + (0.3 * multi_source_score) + (0.2 * recency_score)

    logger.info(
        "[VERIFICATION] Stage 1 | source=%.2f auth=%s multi=%.2f recency=%.2f → score=%.2f",
        source_score, any_authenticated, multi_source_score, recency_score, score,
    )

    return round(score, 4)


# ─── Stage 2: Content Reconfirmation (LLM Validation) ────────────────────────

VERIFICATION_PROMPT = """You are a fact verification assistant.

Evaluate whether the following news claim appears valid and plausible.

Headline:
{headline}

Summary:
{summary}

Return JSON only:

{{
  "validity": "valid / uncertain / false",
  "confidence": 0.0-1.0,
  "reason": "short explanation"
}}"""


def reconfirm_content_with_llm(headline: str, summary: str) -> float:
    """
    Stage 2 – Use Ollama to assess plausibility of the content.

    Returns:
        LLM confidence score (0.0 – 1.0).
        Falls back to 0.5 if Ollama is unreachable.
    """
    prompt = VERIFICATION_PROMPT.format(headline=headline, summary=summary)

    request_body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        logger.info("[VERIFICATION] Stage 2 | Asking Ollama to verify content plausibility...")
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=request_body,
            timeout=90,
        )
        response.raise_for_status()
        raw = response.json()["message"]["content"]
        return _parse_llm_verification(raw)

    except requests.exceptions.ConnectionError:
        logger.warning("[VERIFICATION] Ollama not reachable – using neutral confidence (0.5)")
        return 0.5
    except requests.exceptions.Timeout:
        logger.warning("[VERIFICATION] Ollama timed out – using neutral confidence (0.5)")
        return 0.5
    except Exception as e:
        logger.error("[VERIFICATION] LLM verification error: %s", e)
        return 0.5


def _parse_llm_verification(raw: str) -> float:
    """Extract the confidence score from the LLM JSON response."""
    # Strip <think> blocks
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()

    # Try markdown fences
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return _extract_confidence(data)
        except json.JSONDecodeError:
            pass

    # Try bare JSON
    brace_match = re.search(r"\{[\s\S]*\}", cleaned)
    if brace_match:
        try:
            data = json.loads(brace_match.group(0))
            return _extract_confidence(data)
        except json.JSONDecodeError:
            pass

    # Fallback
    logger.warning("[VERIFICATION] Could not parse LLM verification response")
    return 0.5


def _extract_confidence(data: dict) -> float:
    """Extract and clamp confidence score from parsed LLM response."""
    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    validity = data.get("validity", "uncertain").lower()
    reason = data.get("reason", "no reason provided")

    logger.info(
        "[VERIFICATION] Stage 2 | validity=%s confidence=%.2f reason=%s",
        validity, confidence, reason,
    )
    return confidence


# ─── Final Decision ──────────────────────────────────────────────────────────

def compute_final_verification(payload: dict, db_conn) -> tuple[float, str]:
    """
    Run both stages and compute the final verification decision.

    Formula: final = (0.6 * stage1) + (0.4 * stage2)

    Returns:
        (final_score, status) where status is one of:
            'verified'       – score >= 0.6
            'low_confidence' – score 0.4–0.6
            'rejected'       – score < 0.4
    """
    # ── Stage 1 ───────────────────────────────────────────────────────────────
    stage1_score = compute_verification_score(payload, db_conn)

    if stage1_score < STAGE1_REJECT_THRESHOLD:
        logger.warning(
            "[VERIFICATION] Rejected payload from source(s): %s | "
            "Reason: low verification score (%.2f < %.2f)",
            ", ".join(payload.get("sources", ["unknown"])),
            stage1_score, STAGE1_REJECT_THRESHOLD,
        )
        return round(stage1_score, 4), "rejected"

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    headline = payload.get("headline", "")
    summary = payload.get("content", "")[:500]  # Use content snippet as summary
    llm_confidence = reconfirm_content_with_llm(headline, summary)

    # ── Final Score ───────────────────────────────────────────────────────────
    final_score = (0.6 * stage1_score) + (0.4 * llm_confidence)
    final_score = round(final_score, 4)

    if final_score >= 0.6:
        status = "verified"
    elif final_score >= 0.4:
        status = "moderate"
    else:
        status = "rejected"

    logger.info(
        "[VERIFICATION] Final | stage1=%.2f llm=%.2f → final=%.2f → %s",
        stage1_score, llm_confidence, final_score, status,
    )

    if status == "rejected":
        logger.warning(
            "[VERIFICATION] Rejected payload from source(s): %s | "
            "Reason: low final verification score (%.2f)",
            ", ".join(payload.get("sources", ["unknown"])),
            final_score,
        )

    return final_score, status
