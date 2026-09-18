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
import os
import json
from groq import Groq

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


# Pre-built helpers for common hackathon tasks
def extract_intent(text: str, language: str = "bn") -> dict:
    """Extract structured intent from farmer query (matches sample problem Task 1)."""
    schema = """
{
  "crop_type": "string (e.g., rice, potato, tomato)",
  "planting_date_estimate": "string (ISO date or 'unknown')",
  "damage_description": "string (English summary)",
  "geographic_union": "string (union/upazila name or 'unknown')",
  "language": "string ('bn' or 'en')",
  "urgency": "string ('low', 'medium', 'high')"
}"""
    system = "You are an agricultural assistant for Bangladesh. Extract structured info from farmer queries."
    prompt = f"Farmer query (in {'Bengali' if language == 'bn' else 'English'}): {text}"
    return structured_chat(prompt, schema, system=system)


def recommend_treatment(symptoms: dict, weather: dict, image_findings: str = "") -> dict:
    """Generate treatment recommendation (matches sample problem Task 3)."""
    schema = """
{
  "probable_cause": "string",
  "severity": "string ('Mild', 'Moderate', 'Severe', 'Critical')",
  "organic_controls": ["string"],
  "chemical_treatment": {
    "product": "string",
    "dosage": "string",
    "frequency": "string"
  },
  "pre_harvest_interval_days": "number",
  "weather_advice": "string"
}"""
    system = "You are a senior agronomist specializing in Bangladesh crops."
    prompt = f"""Based on these inputs, recommend treatment:

Symptoms: {json.dumps(symptoms)}
Weather: {json.dumps(weather)}
Image findings: {image_findings or 'Not provided'}
"""
    return structured_chat(prompt, schema, system=system)


if __name__ == "__main__":
    # Demo
    test = extract_intent("আমার ধানের পাতায় হলুদ দাগ পড়েছে", language="bn")
    print(json.dumps(test, indent=2, ensure_ascii=False))
