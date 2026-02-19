"""
agent/verifier.py – Fact verification step for the AI agent pipeline.

Asks Ollama to cross-check the generated post against the original input
and flag any invented facts or unsupported claims.
"""

import os
import json
import re
import logging
import requests

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2")

VERIFIER_SYSTEM = """You are a strict fact-checker for the Collective Intelligence Network.
Your job is to verify that a generated post contains ONLY information supported by the original source data.
You must be conservative — if something cannot be confirmed from the source, flag it."""

VERIFIER_PROMPT = """Compare the GENERATED POST against the ORIGINAL SOURCE DATA.

ORIGINAL SOURCE DATA:
- Headline: {headline}
- Content: {content}
- Sources: {sources}

GENERATED POST:
{generated_post}

Answer with a JSON object:
{{
  "verified": true or false,
  "confidence_score": <integer 0-100>,
  "issues": ["list of invented or unsupported claims, empty if none"],
  "verdict": "A one-sentence summary of your finding"
}}

Rules:
- Set verified=false if ANY claim in the post cannot be traced to the source data.
- Set verified=true only if all key claims are supported.
- Be strict but fair."""


def verify_post(generated: dict, original_payload: dict) -> tuple[bool, str]:
    """
    Verify that the generated post is grounded in the original payload.

    Args:
        generated:        Output from agent/generator.py
        original_payload: The original validated webhook payload

    Returns:
        (True, verdict)   – post is verified
        (False, reason)   – post contains invented facts
    """
    prompt = VERIFIER_PROMPT.format(
        headline=original_payload.get("headline", ""),
        content=original_payload.get("content", "")[:3000],
        sources=json.dumps(original_payload.get("sources", [])),
        generated_post=json.dumps(generated, indent=2),
    )

    request_body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": VERIFIER_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        logger.info("[Verifier] 🔍 Asking Ollama to verify facts...")
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=request_body,
            timeout=90,
        )
        response.raise_for_status()
        raw = response.json()["message"]["content"]
        return _parse_verdict(raw)

    except requests.exceptions.ConnectionError:
        logger.warning("[Verifier] Ollama unavailable – skipping verification, marking as unverified.")
        return False, "Verification skipped: Ollama not reachable."
    except Exception as e:
        logger.error("[Verifier] Error during verification: %s", e)
        return False, f"Verification error: {e}"


def _extract_json(raw: str) -> dict | None:
    """
    Try multiple strategies to extract a JSON object from the LLM response.

    Models like llama3.2 may wrap output in <think> tags, markdown fences,
    or add prose before/after the JSON. This handles all of those.
    """
    # 1. Strip <think>...</think> blocks (common with reasoning models)
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()

    # 2. Try markdown code fences first
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Try to find a bare JSON object { ... }
    brace_match = re.search(r"\{[\s\S]*\}", cleaned)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # 4. Last resort: try parsing the entire cleaned string
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _parse_verdict(raw: str) -> tuple[bool, str]:
    """Parse the verifier JSON response."""
    logger.info("[Verifier] 📄 Parsing verification verdict...")

    data = _extract_json(raw)
    if data is None:
        logger.warning(
            "[Verifier] ❌ Could not parse verifier response. Raw output:\n%s",
            raw[:500],
        )
        # Conservative: if we can't parse the verdict, reject the post
        return False, "Verification failed: could not parse verifier response."

    verified = bool(data.get("verified", False))
    verdict  = data.get("verdict", "No verdict provided.")
    issues   = data.get("issues", [])

    if not verified and issues:
        verdict = f"{verdict} Issues: {'; '.join(str(i) for i in issues)}"

    logger.info("[Verifier] ✅ Result: verified=%s | %s", verified, verdict)
    return verified, verdict
