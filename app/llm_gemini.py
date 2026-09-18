"""
LLM via Google Gemini — multimodal (image + text), long context.
Free tier: 15 RPM, generous.
Get key: https://aistudio.google.com/app/apikey
Env: GEMINI_API_KEY

Models:
- gemini-2.0-flash-exp (fast, multimodal)
- gemini-1.5-pro (longer context)
- gemini-1.5-flash (fast, free)
"""
import os
import json
import google.generativeai as genai

_configured = False

def _ensure_configured():
    global _configured
    if not _configured:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        _configured = True

DEFAULT_MODEL = "gemini-2.0-flash-exp"


def chat(prompt: str, system: str = "", model: str = DEFAULT_MODEL, temperature: float = 0.7) -> str:
    """Simple text chat."""
    _ensure_configured()
    m = genai.GenerativeModel(
        model_name=model,
        system_instruction=system if system else None,
    )
    response = m.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(temperature=temperature),
    )
    return response.text


def structured_chat(prompt: str, json_schema_description: str, system: str = "", model: str = DEFAULT_MODEL) -> dict:
    """Ask for JSON response."""
    _ensure_configured()
    m = genai.GenerativeModel(
        model_name=model,
        system_instruction=system if system else None,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",  # Force JSON
        ),
    )
    full_prompt = f"{prompt}\n\nReturn JSON matching:\n{json_schema_description}"
    response = m.generate_content(full_prompt)
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        return {"error": "JSON parse failed", "raw": response.text}


if __name__ == "__main__":
    print("Gemini ready. Set GEMINI_API_KEY in .env")
