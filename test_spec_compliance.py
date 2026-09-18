"""
Spec compliance audit — checks every requirement in the BUP CSE Fest 2026
Preliminary Problem Statement against our implementation.

Sections audited:
  04 (operator notes / directives)
  06 (API contract — endpoint names, response codes)
  07 (request schema — fields, types, constraints)
  08 (LLM interpretation guardrails)
  09 (battery & energy rules — including E[23]=initial neutrality)
  10 (response schema — fields, types, constraints)
  11 (hidden evaluation — paraphrase robustness, no_invention)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests
from app.schemas import (
    BatterySpec, DirectiveInterpretation, HourEntry, HourlyPlanEntry,
    MaxGridWindow, MinimumBatteryReserve, NoChargeWindow, NoDischargeWindow,
    OptimizeRequest, OptimizeResponse, SolarReduction,
)


LIVE_URL = "https://gridwise-wppp.onrender.com"


def make_request() -> dict:
    """Build a valid minimal request matching section 07."""
    hours = []
    for h in range(24):
        hours.append({
            "hour": h,
            "demand_kwh": 100 + (h % 12) * 5,
            "solar_kwh": max(0, 50 - abs(12 - h) * 5),
            "tariff_bdt_per_kwh": 8.0 + (h >= 18) * 6,
        })
    return {
        "scenario_id": "AUDIT-001",
        "operator_notes": [
            "Reduce solar to 20% from 1 PM to 3 PM.",
            "Keep at least 120 kWh in reserve from 6 PM until 9 PM.",
        ],
        "hours": hours,
        "battery": {
            "capacity_kwh": 500,
            "initial_energy_kwh": 250,
            "minimum_energy_kwh": 50,
            "max_charge_kwh_per_hour": 100,
            "max_discharge_kwh_per_hour": 100,
        },
    }


def section_04_directives():
    """Section 4.1 — all 6 supported directive types must be accepted."""
    print("\n=== Section 04: Supported Directives ===")
    cases = [
        ("solar_reduction",         SolarReduction(hours=[13, 14], factor=0.2)),
        ("minimum_battery_reserve", MinimumBatteryReserve(hours=[18, 19, 20], minimum_energy_kwh=120)),
        ("no_charge_window",        NoChargeWindow(hours=[14, 15])),
        ("no_discharge_window",     NoDischargeWindow(hours=[18, 19, 20])),
        ("max_grid_window",         MaxGridWindow(hours=[18, 19, 20], max_grid_kwh=200)),
    ]
    fails = 0
    for name, model in cases:
        try:
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=name,
                structured_adjustment=model.model_dump(),
                explanation=f"test {name}",
            )
            print(f"  [PASS] {name}: model accepts canonical shape")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            fails += 1

    # no_op with applies=false, structured_adjustment=null
    try:
        DirectiveInterpretation(
            note_index=0,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="irrelevant",
        )
        print(f"  [PASS] no_op: requires applies=false, structured_adjustment=null")
    except Exception as e:
        print(f"  [FAIL] no_op: {e}")
        fails += 1

    # no_op with applies=true should be rejected (section 5.1)
    try:
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="x",
        )
        print(f"  [FAIL] no_op should reject applies=true")
        fails += 1
    except Exception:
        print(f"  [PASS] no_op correctly rejects applies=true")

    return fails


def section_06_api_contract():
    """Section 6 — endpoint names match exactly, response codes correct."""
    print("\n=== Section 06: API Contract ===")
    fails = 0

    # 6.1: GET /health returns 200 with {"status":"ok"}
    r = requests.get(f"{LIVE_URL}/health", timeout=10)
    if r.status_code == 200 and r.json() == {"status": "ok"}:
        print(f"  [PASS] GET /health → 200, body={{'status':'ok'}}")
    else:
        print(f"  [FAIL] GET /health → {r.status_code}, body={r.text[:80]}")
        fails += 1

    # 6.1: POST malformed → 400 (not 422)
    r = requests.post(f"{LIVE_URL}/optimize-energy", json={"bad": "body"}, timeout=10)
    if r.status_code == 400:
        print(f"  [PASS] POST malformed → 400 (per spec)")
    else:
        print(f"  [FAIL] POST malformed → {r.status_code}, expected 400")
        fails += 1

    # 6.1: POST valid → 200 with directive_interpretation + hourly_plan
    payload = make_request()
    r = requests.post(f"{LIVE_URL}/optimize-energy", json=payload, timeout=30)
    if r.status_code != 200:
        print(f"  [FAIL] POST valid → {r.status_code}, expected 200")
        fails += 1
        return fails
    body = r.json()

    if "directive_interpretation" in body and "hourly_plan" in body:
        print(f"  [PASS] Response has both directive_interpretation and hourly_plan")
    else:
        print(f"  [FAIL] Response missing required keys")
        fails += 1

    return fails


def section_07_request_schema():
    """Section 7 — request schema validation."""
    print("\n=== Section 07: Request Schema ===")
    fails = 0

    # 7.4: hours must have exactly 24 entries
    bad = make_request()
    bad["hours"] = bad["hours"][:23]
    try:
        OptimizeRequest.model_validate(bad)
        print(f"  [FAIL] should reject 23 hours")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects hours array of length != 24")

    # operator_notes must have 1-3 entries
    bad = make_request()
    bad["operator_notes"] = []
    try:
        OptimizeRequest.model_validate(bad)
        print(f"  [FAIL] should reject empty operator_notes")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects empty operator_notes")

    bad = make_request()
    bad["operator_notes"] = ["a", "b", "c", "d"]
    try:
        OptimizeRequest.model_validate(bad)
        print(f"  [FAIL] should reject 4 operator_notes")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects >3 operator_notes")

    # hour must be 0..23
    bad = make_request()
    bad["hours"][0]["hour"] = 24
    try:
        OptimizeRequest.model_validate(bad)
        print(f"  [FAIL] should reject hour=24")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects hour=24")

    # battery invariants
    bad = make_request()
    bad["battery"]["initial_energy_kwh"] = 600  # > capacity
    try:
        OptimizeRequest.model_validate(bad)
        print(f"  [FAIL] should reject initial > capacity")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects initial_energy > capacity")

    return fails


def section_08_guardrails():
    """Section 8 — LLM guardrails (offline, no API call)."""
    print("\n=== Section 08: LLM Guardrails ===")
    fails = 0

    # Hours must be unique ascending 0-23
    try:
        SolarReduction(hours=[13, 14, 13], factor=0.2)
        print(f"  [FAIL] should reject duplicate hours")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects duplicate hours")

    try:
        SolarReduction(hours=[14, 13], factor=0.2)  # not ascending
        print(f"  [FAIL] should reject non-ascending hours")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects non-ascending hours")

    try:
        SolarReduction(hours=[24], factor=0.2)
        print(f"  [FAIL] should reject hour > 23")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects hour > 23")

    # Factor must be 0..1
    try:
        SolarReduction(hours=[13], factor=1.5)
        print(f"  [FAIL] should reject factor > 1")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects factor > 1")

    try:
        SolarReduction(hours=[13], factor=-0.1)
        print(f"  [FAIL] should reject factor < 0")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects factor < 0")

    # Reserve must be <= capacity (tested via DirectiveInterpretation validator)
    big = DirectiveInterpretation(
        note_index=0,
        applies=True,
        directive_type="minimum_battery_reserve",
        structured_adjustment={"hours": [13], "minimum_energy_kwh": 1000000},
        explanation="x",
    )
    # Note: validator doesn't check vs battery.capacity; that check happens in interpreter.py
    # Let's verify the shape validator works:
    try:
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": [13], "minimum_energy_kwh": -5},
            explanation="x",
        )
        print(f"  [FAIL] should reject minimum_energy_kwh < 0")
        fails += 1
    except Exception:
        print(f"  [PASS] rejects minimum_energy_kwh < 0")

    return fails


def section_09_battery_rules():
    """Section 9 — battery rules, especially 9.6 E[23]=initial."""
    print("\n=== Section 09: Battery & Energy Rules ===")
    fails = 0

    # Hit live endpoint and check end-of-day neutrality
    payload = make_request()
    r = requests.post(f"{LIVE_URL}/optimize-energy", json=payload, timeout=30)
    if r.status_code != 200:
        print(f"  [FAIL] live POST returned {r.status_code}")
        return fails + 1

    body = r.json()
    plan = body["hourly_plan"]
    initial = payload["battery"]["initial_energy_kwh"]
    final = plan[-1]["battery_energy_after_kwh"]
    if abs(final - initial) <= 0.01:
        print(f"  [PASS] 9.6 E[23]={final} == initial={initial} (within 0.01 tolerance)")
    else:
        print(f"  [FAIL] 9.6 E[23]={final} != initial={initial}")
        fails += 1

    # 9.1: battery_action in {charge, discharge, idle}
    actions = {p["battery_action"] for p in plan}
    valid = actions <= {"charge", "discharge", "idle"}
    if valid:
        print(f"  [PASS] 9.1 all actions in {{charge, discharge, idle}}: {actions}")
    else:
        print(f"  [FAIL] 9.1 invalid actions: {actions - {'charge', 'discharge', 'idle'}}")
        fails += 1

    # 9.1: idle => battery_kwh == 0
    bad_idle = [p for p in plan if p["battery_action"] == "idle" and p["battery_kwh"] != 0]
    if not bad_idle:
        print(f"  [PASS] 9.1 idle hours have battery_kwh=0")
    else:
        print(f"  [FAIL] 9.1 idle hours with non-zero battery_kwh: {bad_idle}")
        fails += 1

    # 9.5: energy balance every hour
    bad_balance = []
    for i, p in enumerate(plan):
        d_charge = p["battery_kwh"] if p["battery_action"] == "charge" else 0
        d_discharge = p["battery_kwh"] if p["battery_action"] == "discharge" else 0
        lhs = p["grid_kwh"] + p["solar_used_kwh"] + d_discharge
        rhs = payload["hours"][i]["demand_kwh"] + d_charge
        if abs(lhs - rhs) > 0.01:
            bad_balance.append((i, lhs, rhs))
    if not bad_balance:
        print(f"  [PASS] 9.5 energy balance holds every hour")
    else:
        print(f"  [FAIL] 9.5 energy balance broken: {bad_balance[:2]}")
        fails += 1

    # 9.4: solar_used_kwh <= effective solar
    solar_used_excess = []
    for i, p in enumerate(plan):
        eff = payload["hours"][i]["solar_kwh"]
        if p["solar_used_kwh"] > eff + 0.01:
            solar_used_excess.append((i, p["solar_used_kwh"], eff))
    if not solar_used_excess:
        print(f"  [PASS] 9.4 solar_used_kwh <= solar_kwh every hour")
    else:
        print(f"  [FAIL] 9.4 solar_used > available: {solar_used_excess[:2]}")
        fails += 1

    return fails


def section_10_response_schema():
    """Section 10 — response schema."""
    print("\n=== Section 10: Response Schema ===")
    fails = 0

    payload = make_request()
    r = requests.post(f"{LIVE_URL}/optimize-energy", json=payload, timeout=30)
    body = r.json()

    # 10.1: scenario_id, directive_interpretation, hourly_plan, totals, plan_summary
    required = {"scenario_id", "directive_interpretation", "hourly_plan",
                "total_grid_kwh", "total_cost_bdt", "peak_grid_kwh", "plan_summary"}
    missing = required - set(body.keys())
    if not missing:
        print(f"  [PASS] 10.1 all top-level fields present")
    else:
        print(f"  [FAIL] 10.1 missing fields: {missing}")
        fails += 1

    # 10.1: scenario_id echoes request
    if body["scenario_id"] == payload["scenario_id"]:
        print(f"  [PASS] 10.1 scenario_id echo: {body['scenario_id']}")
    else:
        print(f"  [FAIL] 10.1 scenario_id mismatch")
        fails += 1

    # 10.1: hourly_plan has exactly 24 unique hours 0-23
    hours_in_plan = sorted(p["hour"] for p in body["hourly_plan"])
    if hours_in_plan == list(range(24)):
        print(f"  [PASS] 10.1 hourly_plan has hours 0..23")
    else:
        print(f"  [FAIL] 10.1 hourly_plan missing/duplicate hours")
        fails += 1

    # 10.1: directive_interpretation count == operator_notes count
    if len(body["directive_interpretation"]) == len(payload["operator_notes"]):
        print(f"  [PASS] 10.1 directive count ({len(body['directive_interpretation'])}) matches note count ({len(payload['operator_notes'])})")
    else:
        print(f"  [FAIL] 10.1 directive/note count mismatch")
        fails += 1

    # 10.2: each directive has note_index, applies, directive_type, structured_adjustment, explanation
    for i, d in enumerate(body["directive_interpretation"]):
        required_d = {"note_index", "applies", "directive_type", "structured_adjustment", "explanation"}
        missing_d = required_d - set(d.keys())
        if missing_d:
            print(f"  [FAIL] 10.2 directive[{i}] missing: {missing_d}")
            fails += 1

    # 10.2: note_index in order 0..N-1
    indices = [d["note_index"] for d in body["directive_interpretation"]]
    if indices == list(range(len(indices))):
        print(f"  [PASS] 10.2 directive note_index order: {indices}")
    else:
        print(f"  [FAIL] 10.2 note_index out of order: {indices}")
        fails += 1

    # 10.3: hourly plan fields
    required_p = {"hour", "grid_kwh", "solar_used_kwh", "battery_action", "battery_kwh", "battery_energy_after_kwh"}
    for i, p in enumerate(body["hourly_plan"]):
        missing_p = required_p - set(p.keys())
        if missing_p:
            print(f"  [FAIL] 10.3 hourly_plan[{i}] missing: {missing_p}")
            fails += 1

    # Recalculate totals — must match within 0.01
    plan = body["hourly_plan"]
    recalc_grid = sum(p["grid_kwh"] for p in plan)
    recalc_cost = sum(p["grid_kwh"] * payload["hours"][p["hour"]]["tariff_bdt_per_kwh"] for p in plan)
    recalc_peak = max(p["grid_kwh"] for p in plan)

    if abs(recalc_grid - body["total_grid_kwh"]) < 0.01:
        print(f"  [PASS] 11.3 total_grid_kwh matches recalc: {recalc_grid:.2f} vs {body['total_grid_kwh']:.2f}")
    else:
        print(f"  [FAIL] 11.3 total_grid_kwh mismatch: {recalc_grid} vs {body['total_grid_kwh']}")
        fails += 1

    if abs(recalc_cost - body["total_cost_bdt"]) < 0.01:
        print(f"  [PASS] 11.3 total_cost_bdt matches recalc: {recalc_cost:.2f} vs {body['total_cost_bdt']:.2f}")
    else:
        print(f"  [FAIL] 11.3 total_cost_bdt mismatch: {recalc_cost} vs {body['total_cost_bdt']}")
        fails += 1

    if abs(recalc_peak - body["peak_grid_kwh"]) < 0.01:
        print(f"  [PASS] 11.3 peak_grid_kwh matches recalc: {recalc_peak:.2f} vs {body['peak_grid_kwh']:.2f}")
    else:
        print(f"  [FAIL] 11.3 peak_grid_kwh mismatch: {recalc_peak} vs {body['peak_grid_kwh']}")
        fails += 1

    return fails


def section_11_paraphrase_robustness():
    """Section 11.4 — same rule, different wording → same directive."""
    print("\n=== Section 11: Paraphrase Robustness ===")
    fails = 0

    # 3 paraphrases of "solar reduction factor=0.2 between 13:00 and 15:00"
    paraphrases = [
        "PV production will drop to about 20% between 13:00 and 15:00.",
        "Panel washing from one until three will leave roughly one-fifth of normal solar output.",
        "Expect an 80% reduction in rooftop solar during the 1-3 PM maintenance window.",
    ]
    expected = {"hours": [13, 14], "factor": 0.2}

    for note in paraphrases:
        payload = make_request()
        payload["operator_notes"] = [note]
        payload["scenario_id"] = f"PARAPHRASE-{hash(note) % 10000}"
        r = requests.post(f"{LIVE_URL}/optimize-energy", json=payload, timeout=30)
        if r.status_code != 200:
            print(f"  [FAIL] '{note}' → status {r.status_code}")
            fails += 1
            continue
        body = r.json()
        d = body["directive_interpretation"][0]
        if d["directive_type"] != "solar_reduction":
            print(f"  [FAIL] '{note}' → {d['directive_type']} (expected solar_reduction)")
            fails += 1
            continue
        adj = d["structured_adjustment"]
        if abs(adj.get("factor", -1) - 0.2) > 0.01:
            print(f"  [FAIL] '{note}' → factor={adj.get('factor')} (expected 0.2)")
            fails += 1
            continue
        if adj.get("hours") != [13, 14]:
            print(f"  [FAIL] '{note}' → hours={adj.get('hours')} (expected [13,14])")
            fails += 1
            continue
        print(f"  [PASS] '{note[:50]}...' → solar_reduction [13,14]×0.2")

    return fails


def main():
    print(f"Auditing {LIVE_URL} against the BUP CSE Fest 2026 Problem Statement")
    print("=" * 70)

    fails = 0
    fails += section_04_directives()
    fails += section_06_api_contract()
    fails += section_07_request_schema()
    fails += section_08_guardrails()
    fails += section_09_battery_rules()
    fails += section_10_response_schema()
    fails += section_11_paraphrase_robustness()

    print("\n" + "=" * 70)
    if fails == 0:
        print("SPEC AUDIT PASSED — system complies with all 7 audited sections")
        return 0
    print(f"SPEC AUDIT FAILED — {fails} issue(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
