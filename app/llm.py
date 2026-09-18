"""
LLM via Groq — FASTEST free inference. Best for structured output.
Free tier: very generous.
Get key: https://console.groq.com/keys
Env: GROQ_API_KEY

Models (check console.groq.com for latest):
- openai/gpt-oss-120b (best quality, OpenAI open-source)
- qwen/qwen3.8-27b (fast, good quality)
- groq/compound-mini (Groq default, fast)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


DEFAULT_MODEL = "openai/gpt-oss-120b"


def chat(prompt: str, system: str = "", model: str = DEFAULT_MODEL, temperature: float = 0.7) -> str:
    """Simple chat completion."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = _get_client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


def structured_chat(prompt: str, json_schema_description: str, system: str = "", model: str = DEFAULT_MODEL) -> dict:
    """
    Ask LLM to return JSON matching a schema.
    Returns parsed dict. Use json_schema_description to describe fields.
    """
    full_prompt = f"""{prompt}

Return ONLY valid JSON matching this schema:
{json_schema_description}

No markdown, no explanation. Just the JSON object."""

    raw = chat(full_prompt, system=system, model=model, temperature=0.1)

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "JSON parse failed", "raw": raw}


if __name__ == "__main__":
    # Smoke test
    print(chat("Reply with the word 'ok'.", temperature=0.0))