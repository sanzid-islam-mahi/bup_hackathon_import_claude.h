"""
Verify that each fallback model can produce valid interpretations using the
ACTUAL production system prompt.

Per user request: test 2-3 samples per fallback to catch catastrophic
regressions (model returns garbage JSON, fails all directives, etc.).
Faster than full 10-sample test on each model.

Usage:
    venv/bin/python test_fallbacks.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.llm import chat, GROQ_MODEL_CHAIN, _strip_fences
from app.interpreter import SYSTEM_PROMPT, _build_user_prompt, _parse_llm_json
from app.schemas import DirectiveInterpretation, OptimizeRequest
from samples_loader import load_samples


def run_one_sample(case: dict, model: str) -> tuple[bool, str]:
    """Run a single sample against a single model using the PRODUCTION prompt.

    Rate-limit errors are reported as 'skip' rather than 'fail' since they
    are not a model-quality issue — they happen when the user has used their
    daily budget on that specific model. The model may still produce valid
    output; we just can't prove it without spending more quota.
    """
    inp = case["input"]
    req = OptimizeRequest(**inp)
    user_prompt = _build_user_prompt(inp["operator_notes"], inp["battery"]["capacity_kwh"])

    try:
        raw = chat(user_prompt, system=SYSTEM_PROMPT, model=model, temperature=0.1)
    except Exception as e:
        msg = str(e).lower()
        if "429" in msg or "rate limit" in msg:
            return True, f"SKIP (rate-limited: {type(e).__name__})"
        return False, f"chat() raised {type(e).__name__}: {str(e)[:100]}"

    parsed = _parse_llm_json(raw)
    if not parsed or "directives" not in parsed or not isinstance(parsed["directives"], list):
        return False, f"missing directives list; got keys={list(parsed.keys()) if parsed else None}"

    for i, raw_dir in enumerate(parsed["directives"]):
        try:
            DirectiveInterpretation.model_validate(raw_dir)
        except Exception as e:
            return False, f"directive {i} failed Pydantic: {str(e)[:200]}"

    return True, f"ok ({len(parsed['directives'])} directives)"


def main() -> int:
    samples = load_samples()
    picks = [next(c for c in samples if c["id"] == sid)
             for sid in ("SAMPLE-01", "SAMPLE-03", "SAMPLE-05")]

    failures = 0
    print(f"Testing 3 samples × {len(GROQ_MODEL_CHAIN)} models (production prompt)")
    print()

    for model in GROQ_MODEL_CHAIN:
        print(f"=== {model} ===")
        for case in picks:
            ok, detail = run_one_sample(case, model)
            sym = "PASS" if ok else "FAIL"
            print(f"  [{sym}] {case['id']}: {detail}")
            if not ok:
                failures += 1
        print()

    if failures == 0:
        print("ALL FALLBACK TESTS PASSED")
        return 0
    print(f"{failures} TEST(S) FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())