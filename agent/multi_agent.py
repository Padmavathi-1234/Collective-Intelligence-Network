"""
agent/multi_agent.py – Multi-Agent AI Controller using Groq API.

Runs multiple AI agents in parallel, each representing a different analytical
perspective. Each agent uses a different Groq-hosted model to generate its
analysis, and all results are collected and returned with model attribution.

Pipeline:
    1. Receive validated payload from controller
    2. Dispatch payload to all registered agents concurrently
    3. Each agent calls Groq Chat Completions API
    4. Collect results tagged with model name and role
    5. Return list of per-agent analyses
"""

import os
import json
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ─── Agent Registry ──────────────────────────────────────────────────────────
# Each agent has a unique perspective and uses a different model.

AGENT_REGISTRY = [
    {
        "agent_id": "technology_analyst",
        "model": "mixtral-8x7b-32768",
        "display_model": "Mixtral-8x7B",
        "role": "Technology Analyst",
        "system_prompt": (
            "You are a Technology Analyst for the Collective Intelligence Network. "
            "Your job is to analyse incoming updates with a deep technical and "
            "technology lens — focusing on technological implications, innovation "
            "trends, digital transformation impact, and technical feasibility. "
            "Be precise, cite only the provided data, and never invent information. "
            "Return ONLY valid JSON — no markdown fences, no extra text."
        ),
    },
    {
        "agent_id": "economic_analyst",
        "model": "llama-3.3-70b-versatile",
        "display_model": "Llama-3-70B",
        "role": "Economic Analyst",
        "system_prompt": (
            "You are an Economic Analyst for the Collective Intelligence Network. "
            "Your job is to analyse incoming updates from an economic and financial "
            "perspective — focusing on market impact, economic consequences, "
            "investment implications, and fiscal policy effects. "
            "Be factual, cite only the provided data, and never invent information. "
            "Return ONLY valid JSON — no markdown fences, no extra text."
        ),
    },
    {
        "agent_id": "cybersecurity_analyst",
        "model": "gemma2-9b-it",
        "display_model": "Gemma-9B",
        "role": "Cybersecurity Analyst",
        "system_prompt": (
            "You are a Cybersecurity Analyst for the Collective Intelligence Network. "
            "Your job is to analyse incoming updates from a security perspective — "
            "focusing on cybersecurity risks, data privacy, threat assessment, "
            "vulnerability analysis, and security implications. "
            "Be thorough, cite only the provided data, and never invent information. "
            "Return ONLY valid JSON — no markdown fences, no extra text."
        ),
    },
]

# ─── Prompt Template (shared across agents) ───────────────────────────────────

USER_PROMPT_TEMPLATE = """Transform the following update into a structured analysis from your unique perspective.

INPUT DATA:
- Domain: {domain}
- Headline: {headline}
- Content: {content}
- Sources: {sources}

Return a JSON object with EXACTLY these fields:
{{
  "title": "A clear, factual title (max 120 chars)",
  "summary": "A 2-3 sentence summary from your analytical perspective using only the provided content",
  "content": "A comprehensive, detailed analysis (at least 400 words) from your perspective. Use professional tone.",
  "key_points": ["Point 1", "Point 2", "Point 3"],
  "why_this_matters": "1-2 sentences explaining significance from your perspective, grounded in the content",
  "sources": {sources},
  "confidence_score": <integer 0-100 reflecting how complete and reliable the source data is>
}}

Remember: Do NOT invent any facts not present in the input."""


# ─── Core Functions ───────────────────────────────────────────────────────────

def run_multi_agent(payload: dict) -> list[dict]:
    """
    Run all registered agents in parallel against the same payload.

    Args:
        payload: Validated webhook payload dict with keys:
                 domain, headline, content, sources, timestamp

    Returns:
        List of per-agent result dicts. Each contains the analysis fields
        plus 'agent_id', 'model', and 'role' for attribution.
        Returns empty list if all agents fail.
    """
    if not GROQ_API_KEY:
        logger.error("[MultiAgent] GROQ_API_KEY is not set! Cannot run agents.")
        return []

    results = []
    agent_count = len(AGENT_REGISTRY)

    logger.info(
        "[MultiAgent] 🚀 Dispatching %d agents in parallel for: %s",
        agent_count, payload.get("headline", "")[:80],
    )

    with ThreadPoolExecutor(max_workers=agent_count, thread_name_prefix="groq-agent") as executor:
        future_to_agent = {
            executor.submit(_call_groq_agent, agent_cfg, payload): agent_cfg
            for agent_cfg in AGENT_REGISTRY
        }

        for future in as_completed(future_to_agent):
            agent_cfg = future_to_agent[future]
            try:
                result = future.result(timeout=120)
                if result:
                    results.append(result)
                    logger.info(
                        "[MultiAgent] ✅ Agent '%s' (%s) completed successfully",
                        agent_cfg["role"], agent_cfg["model"],
                    )
                else:
                    logger.warning(
                        "[MultiAgent] ⚠️ Agent '%s' (%s) returned empty result",
                        agent_cfg["role"], agent_cfg["model"],
                    )
            except Exception as e:
                logger.error(
                    "[MultiAgent] ❌ Agent '%s' (%s) failed: %s",
                    agent_cfg["role"], agent_cfg["model"], e,
                )

    logger.info(
        "[MultiAgent] 📊 %d/%d agents returned results",
        len(results), agent_count,
    )
    return results


def _call_groq_agent(agent_cfg: dict, payload: dict) -> dict | None:
    """
    Call one Groq agent and return its analysis tagged with model attribution.

    Args:
        agent_cfg: Agent config dict from AGENT_REGISTRY
        payload:   Validated webhook payload

    Returns:
        Dict with analysis fields + agent_id, model, role; or None on failure.
    """
    agent_id = agent_cfg["agent_id"]
    model = agent_cfg["model"]
    role = agent_cfg["role"]
    system_prompt = agent_cfg["system_prompt"]

    domain = payload.get("domain", "General")
    headline = payload.get("headline", "")
    content = payload.get("content", "")
    sources = json.dumps(payload.get("sources", []))

    user_prompt = USER_PROMPT_TEMPLATE.format(
        domain=domain,
        headline=headline,
        content=content,
        sources=sources,
    )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    try:
        logger.info(
            "[MultiAgent] 🧠 Agent '%s' calling Groq (model=%s)...",
            role, model,
        )
        response = requests.post(
            GROQ_API_URL,
            headers=headers,
            json=request_body,
            timeout=120,
        )
        response.raise_for_status()

        raw_content = response.json()["choices"][0]["message"]["content"]
        parsed = _parse_agent_response(raw_content, payload, agent_cfg)
        return parsed

    except requests.exceptions.HTTPError as e:
        err_body = getattr(e.response, "text", "")[:500]
        logger.error(
            "[MultiAgent] Agent '%s' HTTP error: %s — %s",
            role, e, err_body,
        )
        # If model is decommissioned, try fallback model
        if "decommissioned" in err_body.lower() or "not found" in err_body.lower():
            return _fallback_agent_call(agent_cfg, payload, user_prompt, headers)
        return None
    except requests.exceptions.Timeout:
        logger.error("[MultiAgent] Agent '%s' request timed out.", role)
        return None
    except Exception as e:
        logger.error("[MultiAgent] Agent '%s' unexpected error: %s", role, e)
        return None


def _fallback_agent_call(agent_cfg: dict, payload: dict,
                         user_prompt: str, headers: dict) -> dict | None:
    """
    If the primary model is decommissioned/unavailable, retry with
    llama-3.3-70b-versatile as a fallback.
    """
    fallback_model = "llama-3.3-70b-versatile"
    role = agent_cfg["role"]
    logger.warning(
        "[MultiAgent] 🔄 Agent '%s' falling back to %s...",
        role, fallback_model,
    )

    request_body = {
        "model": fallback_model,
        "messages": [
            {"role": "system", "content": agent_cfg["system_prompt"]},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            GROQ_API_URL,
            headers=headers,
            json=request_body,
            timeout=120,
        )
        response.raise_for_status()

        raw_content = response.json()["choices"][0]["message"]["content"]
        # Override model name to show the fallback was used
        fallback_cfg = {**agent_cfg, "model": fallback_model, "display_model": "Llama-3-70B (Fallback)"}
        parsed = _parse_agent_response(raw_content, payload, fallback_cfg)
        if parsed:
            logger.info("[MultiAgent] ✅ Fallback succeeded for agent '%s'", role)
        return parsed
    except Exception as e:
        logger.error("[MultiAgent] ❌ Fallback also failed for agent '%s': %s", role, e)
        return None


# ─── Response Parsing ─────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict | None:
    """
    Try multiple strategies to extract a JSON object from the LLM response.
    """
    # 1. Strip <think>...</think> blocks
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()

    # 2. Try markdown code fences
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Try bare JSON object { ... }
    brace_match = re.search(r"\{[\s\S]*\}", cleaned)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # 4. Last resort
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _parse_agent_response(raw: str, payload: dict, agent_cfg: dict) -> dict | None:
    """Parse the Groq response and tag it with agent attribution."""
    data = _extract_json(raw)
    if data is None:
        logger.warning(
            "[MultiAgent] ❌ Could not parse JSON from agent '%s'. Raw:\n%s",
            agent_cfg["role"], raw[:500],
        )
        return None

    return {
        # ── Attribution ──
        "agent_id": agent_cfg["agent_id"],
        "model": agent_cfg.get("display_model", agent_cfg["model"]),
        "role": agent_cfg["role"],
        # ── Analysis ──
        "title": data.get("title", payload.get("headline", ""))[:200],
        "summary": data.get("summary", ""),
        "content": data.get("content", ""),
        "key_points": data.get("key_points", []),
        "why_this_matters": data.get("why_this_matters", ""),
        "sources": data.get("sources", payload.get("sources", [])),
        "confidence_score": int(data.get("confidence_score", 50)),
    }
