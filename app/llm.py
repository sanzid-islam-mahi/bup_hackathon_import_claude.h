"""
LLM via Groq — FASTEST free inference. Best for structured output.
Free tier: very generous.
Get key: https://console.groq.com/keys
Env: GROQ_API_KEY

Models (check console.groq.com for latest):
- openai/gpt-oss-120b     (best quality, OpenAI open-source; 30 RPM, 8K TPM, 200K TPD)
- groq/compound-mini      (Groq router model; 30 RPM, 70K TPM, NO TPD, only 250 RPD)
- qwen/qwen3.8-27b        (fast, good quality; 30 RPM, 8K TPM, 200K TPD)

`chat_with_fallback` rotates through these models in order whenever the
Groq API returns HTTP 429 (rate limit) or a transient error. The first
model that succeeds is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from groq import Groq

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

_client = None
_provider = None


def _get_client():
    """OpenAI is the primary provider (used whenever OPENAI_API_KEY is set).
    Groq is the fallback when only a Groq key is available. Same
    chat()/chat_with_fallback() interface either way, so interpreter.py
    never needs to know which one is active.
    """
    global _client, _provider
    if _client is not None:
        return _client, _provider
    if os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        _provider = "openai"
    elif os.getenv("GROQ_API_KEY"):
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        _provider = "groq"
    else:
        raise RuntimeError("No LLM API key configured. Set OPENAI_API_KEY or GROQ_API_KEY in .env")
    return _client, _provider


DEFAULT_MODEL = "openai/gpt-oss-120b"  # Groq default; ignored when provider is openai

# Rotation order: tried in this sequence. Order matters — cheaper/faster first.
# compound-mini has no daily token cap but only 250 RPD, so we use it
# after our primary exhausts its tokens but before we hit a hard wall.
GROQ_MODEL_CHAIN: List[str] = [
    "openai/gpt-oss-120b",
    "groq/compound-mini",
    "qwen/qwen3.8-27b",
]

OPENAI_MODEL_CHAIN: List[str] = ["gpt-4o-mini"]


def _is_rate_limit(exc: Exception) -> bool:
    """Return True if the exception looks like a Groq rate-limit (HTTP 429).

    We avoid importing the full Groq exception hierarchy here so the module
    stays importable even if the SDK changes. Inspect the string instead.
    """
    name = type(exc).__name__
    msg = str(exc).lower()
    return (
        "429" in msg
        or "rate" in msg and "limit" in msg
        or "rate_limit" in name.lower()
        or name == "RateLimitError"
    )


def _is_transient(exc: Exception) -> bool:
    """Return True for transient errors worth retrying (timeout, 5xx, conn)."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "timeout" in msg
        or "timed out" in msg
        or "connection" in msg
        or "503" in msg or "502" in msg or "500" in msg
        or "service" in msg and "unavailable" in msg
        or "internal" in name
    )


def chat(
    prompt: str,
    system: str = "",
    model: str = None,
    temperature: float = 0.7,
) -> str:
    """Single-model chat completion (no fallback)."""
    client, provider = _get_client()
    if model is None:
        model = DEFAULT_MODEL if provider == "groq" else OPENAI_MODEL_CHAIN[0]

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {"model": model, "messages": messages, "temperature": temperature}
    if provider == "openai" and "json" in (system + prompt).lower():
        # OpenAI requires the literal word "json" in the prompt to use this mode;
        # every structured-output caller here (interpreter.py) already demands
        # JSON in its system prompt, so this guarantees a parseable response.
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


def chat_with_fallback(
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    models: List[str] = None,
) -> tuple[str, str]:
    """Chat completion with automatic model rotation on rate-limit / transient errors.

    Returns (content, model_used). Raises the last exception only if every
    model in the chain failed. Each 429 immediately triggers the next model
    (no retry-with-backoff: the budget is gone, retrying just wastes latency).
    """
    _, provider = _get_client()
    default_chain = GROQ_MODEL_CHAIN if provider == "groq" else OPENAI_MODEL_CHAIN
    chain = models if models is not None else default_chain
    last_exc: Exception | None = None
    for model in chain:
        try:
            content = chat(prompt, system=system, model=model, temperature=temperature)
            return content, model
        except Exception as e:
            last_exc = e
            if _is_rate_limit(e):
                # Bound budget is gone — try next model immediately
                continue
            if _is_transient(e):
                # 5xx / timeout — try next model instead of retrying same one
                continue
            # Non-rate-limit, non-transient: don't bother with the rest of the chain
            raise
    # All models exhausted
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("chat_with_fallback called with empty model list")


def structured_chat(prompt: str, json_schema_description: str, system: str = "", model: str = None) -> dict:
    """Ask LLM to return JSON matching a schema (no model rotation)."""
    full_prompt = f"""{prompt}

Return ONLY valid JSON matching this schema:
{json_schema_description}

No markdown, no explanation. Just the JSON object."""

    raw = chat(full_prompt, system=system, model=model, temperature=0.1)
    raw = _strip_fences(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "JSON parse failed", "raw": raw}


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


if __name__ == "__main__":
    # Demo with rotation
    answer, used = chat_with_fallback("Reply with the word 'ok'.", temperature=0.0)
    print(f"[{used}] {answer}")
