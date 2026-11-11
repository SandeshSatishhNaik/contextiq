"""GenAI reasoning layer — Groq (free tier, OpenAI-compatible API) or Anthropic Claude.

Used ONLY for language and reasoning: understanding questions the router can't place,
extracting policy terms from merchant pages, and wording explanations in plain language.
Never used for payment execution, balances, eligibility arithmetic or authorization.

Configure in .env:
  LLM_PROVIDER=groq        GROQ_API_KEY=...       (free key at console.groq.com)
  LLM_PROVIDER=anthropic   ANTHROPIC_API_KEY=...  (paid, per use)
Without a key every caller falls back to deterministic code, so the app always runs.
"""
from __future__ import annotations

import json
import os
import time

import httpx

from ..config import settings

METER = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0.0, "errors": 0}

PROVIDER = os.getenv("LLM_PROVIDER", "groq" if os.getenv("GROQ_API_KEY") else "anthropic").lower()
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_SMALL = os.getenv("GROQ_MODEL_SMALL", "llama-3.1-8b-instant")
GROQ_LARGE = os.getenv("GROQ_MODEL_LARGE", "llama-3.3-70b-versatile")


def available() -> bool:
    return bool(GROQ_KEY) if PROVIDER == "groq" else bool(settings.anthropic_api_key)


def provider_name() -> str:
    if not available():
        return "none"
    return f"Groq ({GROQ_LARGE})" if PROVIDER == "groq" else f"Claude ({settings.llm_model_large})"


def complete(system: str, user: str, *, large: bool = False, max_tokens: int = 400,
             want_json: bool = False) -> str | dict | None:
    if not available():
        return None
    t0 = time.time()
    try:
        if PROVIDER == "groq":
            body = {"model": GROQ_LARGE if large else GROQ_SMALL, "max_tokens": max_tokens, "temperature": 0.1,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if want_json:
                body["response_format"] = {"type": "json_object"}
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                           headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                           json=body, timeout=30)
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            METER["input_tokens"] += usage.get("prompt_tokens", 0)
            METER["output_tokens"] += usage.get("completion_tokens", 0)
        else:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": settings.llm_model_large if large else settings.llm_model_small,
                      "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]},
                timeout=30)
            r.raise_for_status()
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []))
            METER["input_tokens"] += data.get("usage", {}).get("input_tokens", 0)
            METER["output_tokens"] += data.get("usage", {}).get("output_tokens", 0)
    except Exception:  # noqa: BLE001 — optional layer; fall back to deterministic code
        METER["errors"] += 1
        return None
    METER["calls"] += 1
    METER["latency_ms"] += (time.time() - t0) * 1000
    if want_json:
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            return json.loads(text[start:end])
        except ValueError:
            return None
    return text


INJECTION_MARKERS = ("ignore previous", "ignore all previous", "system prompt", "you are now", "disregard",
                     "assistant:", "<|", "approve this refund", "transfer funds", "ai assistant:")


def sanitize_untrusted(text: str, limit: int = 6000) -> tuple[str, list[str]]:
    """Merchant pages and invoices are untrusted: strip likely prompt-injection lines and flag them."""
    flagged, kept = [], []
    for line in text.splitlines():
        low = line.lower()
        if any(m in low for m in INJECTION_MARKERS):
            flagged.append(line.strip()[:120])
        else:
            kept.append(line)
    return "\n".join(kept)[:limit], flagged


EXPLAIN_SYSTEM = ("You rewrite a financial assistant's answer for an everyday customer. Use 2-3 short, warm, plain "
                  "sentences. Keep every number, date, amount and ID exactly as given. Do not add facts, advice or "
                  "promises. Never say a refund is approved unless the text says so.")


def humanize(text: str) -> str:
    out = complete(EXPLAIN_SYSTEM, text, max_tokens=200)
    return out.strip() if isinstance(out, str) and out.strip() else text
