"""
LLM-driven interpreter for operator notes.

Flow:
  1. Build a tight prompt with all 6 directive types, examples, and rules.
  2. Call Groq (gpt-oss-120b) with response_format=json_object.
  3. Validate the output strictly against Pydantic + extra guardrails.
  4. On any validation failure, fall back to no_op for that note (safe failure).
"""
from __future__ import annotations

import json
import re
from typing import List, Dict, Any, Optional
from pydantic import ValidationError

from app.llm import chat as groq_chat
from app.llm_gemini import chat as gemini_chat
from app.schemas import (
    DirectiveInterpretation,
    OptimizeRequest,
)


SYSTEM_PROMPT = """You are a strict JSON extractor for an energy scheduling system.

Your job: for each operator note, decide if it affects today's 24-hour energy schedule and output ONE structured directive per note.

## Output format — must be valid JSON only, no prose outside the array

{
  "directives": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
      "explanation": "Solar output reduced to 20% during panel cleaning."
    }
  ]
}

## Rules

1. Return exactly one directive per note, in note_index order: 0, 1, 2.
2. If the note does NOT affect today's 24-hour energy schedule, use directive_type="no_op", applies=false, structured_adjustment=null.
3. Choose ONE directive_type from this list:
   - "solar_reduction": reduces usable solar. shape: {"hours":[...], "factor": 0..1}. factor = fraction that REMAINS. "80% reduction" → factor=0.2. "20% of normal" → factor=0.2. "reduced to 25%" → factor=0.25.
   - "minimum_battery_reserve": raises battery floor. shape: {"hours":[...], "minimum_energy_kwh": number}.
   - "no_charge_window": blocks battery charging. shape: {"hours":[...]}.
   - "no_discharge_window": blocks battery discharging. shape: {"hours":[...]}.
   - "max_grid_window": caps grid import. shape: {"hours":[...], "max_grid_kwh": number}.
   - "no_op": note is irrelevant. shape: null.

## Time window parsing (critical)

- "1 PM to 3 PM" → hours [13, 14]  (start inclusive, end EXCLUSIVE)
- "noon until 2 PM" → [12, 13]
- "from 1 PM to 3 PM" → [13, 14]
- "between 13:00 and 15:00" → [13, 14]
- "between 2 PM and 4 PM" → [14, 15]
- "6 PM until 9 PM" → [18, 19, 20]
- "from 6 PM to 9 PM" → [18, 19, 20]
- "1-3 PM" → [13, 14]
- "the 1-3 PM maintenance window" → [13, 14]
- "hours 13 through 15" → [13, 14, 15]  (inclusive on both ends)
- "the morning" → use context (typically 6-12, so [6,7,8,9,10,11])
- "this afternoon" → [12,13,14,15,16]
- "evening" → [17,18,19,20,21,22]

If end time is unclear (e.g. "from 1 PM"), assume next distinct boundary or 1 hour.

## Reduction wording (factor = fraction remaining)

- "drop to 20%" → factor 0.2
- "reduced to 25%" → factor 0.25
- "80% reduction" → factor 0.2
- "leave roughly one-fifth" → factor 0.2 (1/5 = 20%)
- "halved" / "50% reduction" → factor 0.5
- "10% of normal" → factor 0.1

## Reserve values

- Absolute kWh: "at least 120 kWh" → minimum_energy_kwh: 120
- Percentage of capacity: "20% of capacity" → use battery.capacity_kwh * 0.20
- Percentage without capacity context: cannot determine — fall back to no_op with explanation
- A battery capacity reference is provided in the prompt when relevant.

## Numeric range guardrails

- factor must be in [0.0, 1.0]
- minimum_energy_kwh must be in [0, battery.capacity_kwh]
- max_grid_kwh must be >= 0 (0 = absolute grid blackout allowed)

## When NOT to apply a directive

- Notes about events tomorrow / next week / unrelated topics → no_op
- Notes about non-energy topics (cafeteria, registration, sports) → no_op
- Notes that reference unspecified time ranges without any anchor → no_op
- Be conservative: if you cannot confidently extract hours and numbers, use no_op

## Format requirement

Return ONLY the JSON object {"directives": [...]}. No markdown, no commentary.
"""


def _build_user_prompt(notes: List[str], battery_capacity_kwh: float) -> str:
    notes_block = "\n".join(
        f"[note_index={i}] {n}" for i, n in enumerate(notes)
    )
    return f"""Battery capacity for this scenario: {battery_capacity_kwh} kWh.

Operator notes (interpret each one):
{notes_block}

Return JSON only."""


def _parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from raw LLM output. Handles markdown fences."""
    s = raw.strip()
    # Strip markdown fences (greedy match — nested braces survive)
    if s.startswith("```"):
        blocks = re.findall(r"```(?:json)?\s*(\{.*\})\s*```", s, re.DOTALL)
        if blocks:
            s = blocks[-1]
        else:
            s = s.split("```", 2)[1] if "```" in s else s
    s = s.strip()
    # Try parsing
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Find first { to last }
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None


def _validate_one(note_index: int, raw_dir: Dict[str, Any]) -> Optional[DirectiveInterpretation]:
    """Try to validate a single directive dict. Returns None on failure."""
    try:
        return DirectiveInterpretation.model_validate(raw_dir)
    except ValidationError:
        return None


def _shape_adjustment(directive_type: str, raw: Any, battery_capacity_kwh: float) -> Optional[Dict[str, Any]]:
    """Coerce and shape structured_adjustment based on directive_type. Returns None if invalid."""
    if directive_type == "no_op":
        return None
    if not isinstance(raw, dict):
        return None

    def _hours(h) -> Optional[List[int]]:
        if not isinstance(h, list) or not h:
            return None
        try:
            hs = [int(x) for x in h]
        except (TypeError, ValueError):
            return None
        if any(x < 0 or x > 23 for x in hs):
            return None
        # Deduplicate and sort — don't reject LLM output that has repeated hours
        return sorted(set(hs))

    if directive_type == "solar_reduction":
        hs = _hours(raw.get("hours"))
        f = raw.get("factor")
        if hs is None or not isinstance(f, (int, float)):
            return None
        if not (0.0 <= float(f) <= 1.0):
            return None
        return {"hours": hs, "factor": float(f)}

    if directive_type == "minimum_battery_reserve":
        hs = _hours(raw.get("hours"))
        v = raw.get("minimum_energy_kwh")
        if hs is None or not isinstance(v, (int, float)):
            return None
        if v < 0 or v > battery_capacity_kwh:
            return None
        return {"hours": hs, "minimum_energy_kwh": float(v)}

    if directive_type == "no_charge_window":
        hs = _hours(raw.get("hours"))
        if hs is None:
            return None
        return {"hours": hs}

    if directive_type == "no_discharge_window":
        hs = _hours(raw.get("hours"))
        if hs is None:
            return None
        return {"hours": hs}

    if directive_type == "max_grid_window":
        hs = _hours(raw.get("hours"))
        cap = raw.get("max_grid_kwh")
        if hs is None or not isinstance(cap, (int, float)):
            return None
        if cap < 0:  # canonical spec: max_grid_kwh >= 0 (zero = blackout allowed)
            return None
        return {"hours": hs, "max_grid_kwh": float(cap)}

    return None


def interpret_notes(req: OptimizeRequest) -> List[DirectiveInterpretation]:
    """Interpret all operator notes for a request. Always returns one entry per note, in order."""
    notes = req.operator_notes
    capacity = req.battery.capacity_kwh

    user_prompt = _build_user_prompt(notes, capacity)

    # Default fallback: all no_op
    fallback = [
        DirectiveInterpretation(
            note_index=i,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="LLM interpretation unavailable; defaulted to no_op.",
        )
        for i in range(len(notes))
    ]

    try:
        raw = groq_chat(
            user_prompt,
            system=SYSTEM_PROMPT,
            temperature=0.1,
        )
    except Exception as e_primary:
        # Failover to Gemini if Groq is rate-limited / down
        try:
            raw = gemini_chat(
                user_prompt,
                system=SYSTEM_PROMPT,
                temperature=0.1,
            )
        except Exception as e_backup:
            return fallback

    parsed = _parse_llm_json(raw)
    if not parsed or "directives" not in parsed or not isinstance(parsed["directives"], list):
        return fallback

    raw_directives = parsed["directives"]

    # Build one DirectiveInterpretation per note, in order
    out: List[DirectiveInterpretation] = []
    for i in range(len(notes)):
        # Find the directive for this index
        match = None
        for d in raw_directives:
            if isinstance(d, dict) and d.get("note_index") == i:
                match = d
                break

        if match is None:
            out.append(DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation="No directive returned for this note.",
            ))
            continue

        dtype = match.get("directive_type")
        if dtype not in {"solar_reduction", "minimum_battery_reserve", "no_charge_window",
                          "no_discharge_window", "max_grid_window", "no_op"}:
            out.append(DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation=f"Unsupported directive_type '{dtype}'.",
            ))
            continue

        if dtype == "no_op":
            out.append(DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation=match.get("explanation", "Marked as not applicable."),
            ))
            continue

        adj = _shape_adjustment(dtype, match.get("structured_adjustment"), capacity)
        if adj is None:
            out.append(DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation="Could not validate structured_adjustment; defaulted to no_op.",
            ))
            continue

        # Final Pydantic validation
        candidate = {
            "note_index": i,
            "applies": True,
            "directive_type": dtype,
            "structured_adjustment": adj,
            "explanation": match.get("explanation", ""),
        }
        validated = _validate_one(i, candidate)
        if validated is None:
            out.append(DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation="Validation failed; defaulted to no_op.",
            ))
        else:
            out.append(validated)

    return out
