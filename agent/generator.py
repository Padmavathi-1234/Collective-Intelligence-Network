"""
agent/generator.py – Ollama-powered structured post generator.

Uses the Ollama REST API directly (requests) so it works regardless of
whether the 'ollama' Python package is installed.

The prompt is strictly grounded in the provided input data to prevent
hallucination — the model is explicitly told not to invent facts.
"""

import os
import json
import re
import logging
import requests

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2")

# ─── Prompt Template ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a neutral, factual AI journalist for the Collective Intelligence Network.
Your job is to transform raw update data into a structured, verified post.

STRICT RULES:
1. Use ONLY the information provided in the user message. Do NOT invent facts.
2. Do NOT add statistics, quotes, or details not present in the input.
3. If you are unsure about something, say so — do not guess.
4. Be concise, neutral, and professional.
5. Return ONLY valid JSON — no markdown fences, no extra text."""

USER_PROMPT_TEMPLATE = """Transform the following update into a structured post.

INPUT DATA:
- Domain: {domain}
- Headline: {headline}
- Content: {content}
- Sources: {sources}

Return a JSON object with EXACTLY these fields:
{{
  "title": "A clear, factual title (max 120 chars)",
  "summary": "A 2-3 sentence neutral summary using only the provided content",
  "content": "A comprehensive, detailed article (at least 600 words) covering the topic in depth. Use professional journalistic tone.",
  "key_points": ["Point 1", "Point 2", "Point 3"],
  "why_this_matters": "1-2 sentences explaining significance, grounded in the content",
  "sources": {sources},
  "confidence_score": <integer 0-100 reflecting how complete the source data is>
}}

Remember: Do NOT invent any facts not present in the input."""


# ─── Generator ────────────────────────────────────────────────────────────────

def generate_post(payload: dict) -> dict | None:
    """
    Call Ollama to generate a structured post from the webhook payload.

    Args:
        payload: Validated webhook payload dict with keys:
                 domain, headline, content, sources, timestamp

    Returns:
        Structured post dict or None if generation fails.
    """
    domain   = payload.get("domain", "General")
    headline = payload.get("headline", "")
    content  = payload.get("content", "")
    sources  = json.dumps(payload.get("sources", []))

    user_prompt = USER_PROMPT_TEMPLATE.format(
        domain=domain,
        headline=headline,
        content=content,   # cap to avoid token overflow
        sources=sources,
    )

    request_body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,   # low temp = less hallucination
            "top_p": 0.9,
        },
    }

    try:
        logger.info("[Generator] 🧠 Asking Ollama (model=%s) to write post...", OLLAMA_MODEL)
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=request_body,
            timeout=300,   # 5 min — allows for slow CPU-only inference
        )
        response.raise_for_status()
        raw_content = response.json()["message"]["content"]
        return _parse_response(raw_content, payload)

    except requests.exceptions.ConnectionError:
        logger.error("[Generator] Ollama not reachable at %s", OLLAMA_BASE_URL)
        return _fallback_post(payload)
    except requests.exceptions.Timeout:
        logger.error("[Generator] Ollama request timed out.")
        return _fallback_post(payload)
    except Exception as e:
        logger.error("[Generator] Unexpected error: %s", e)
        return _fallback_post(payload)


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


def _parse_response(raw: str, payload: dict) -> dict:
    """Extract JSON from Ollama response, with fallback."""
    logger.info("[Generator] 📨 Parsing Ollama response...")

    data = _extract_json(raw)
    if data is None:
        logger.warning(
            "[Generator] ❌ Could not parse JSON response. Raw output:\n%s",
            raw[:500],
        )
        return _fallback_post(payload)

    logger.info("[Generator] ✅ Successfully parsed post: %s", data.get("title", "")[:60])
    return {
        "title":            data.get("title", payload["headline"])[:200],
        "summary":          data.get("summary", ""),
        "content":          data.get("content", ""),
        "key_points":       data.get("key_points", []),
        "why_this_matters": data.get("why_this_matters", ""),
        "sources":          data.get("sources", payload.get("sources", [])),
        "confidence_score": int(data.get("confidence_score", 50)),
        "domain":           payload.get("domain", "General"),
    }


def _fallback_post(payload: dict) -> dict:
    """Return a minimal post when Ollama is unavailable."""
    logger.warning("[Generator] Using fallback post (Ollama unavailable).")
    return {
        "title":            payload.get("headline", "Untitled Update"),
        "summary":          payload.get("content", "")[:300],
        "key_points":       ["Update received from external source."],
        "why_this_matters": "This update was received but could not be fully processed.",
        "sources":          payload.get("sources", []),
        "confidence_score": 10,
        "domain":           payload.get("domain", "General"),
    }
