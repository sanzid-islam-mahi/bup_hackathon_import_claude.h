"""
Pydantic-level edge case tests — exercise the schema validation
without invoking the LLM.

These test that the schema REJECTS malformed inputs and ACCEPTS edge-case
but valid inputs.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from pydantic import ValidationError
from app.schemas import (
    OptimizeRequest, BatterySpec, HourEntry,
    DirectiveInterpretation, SolarReduction, MinimumBatteryReserve,
    NoChargeWindow, NoDischargeWindow, MaxGridWindow,
)


def expect_accept(name: str, fn):
    try:
        fn()
        print(f"  [PASS] {name}")
        return True
    except ValidationError as e:
        print(f"  [FAIL] {name}: should have accepted but got {e}")
        return False
    except Exception as e:
        print(f"  [FAIL] {name}: unexpected {type(e).__name__}: {e}")
        return False


def expect_reject(name: str, fn):
    try:
        fn()
        print(f"  [FAIL] {name}: should have rejected but accepted")
        return False
    except ValidationError:
        print(f"  [PASS] {name} (rejected as expected)")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: unexpected {type(e).__name__}: {e}")
        return False


# ===================== SolarReduction =====================
def test_solar_reduction():
    print("--- SolarReduction ---")
    failures = 0
    # Accept: valid factor
    if not expect_accept("factor=0.5", lambda: SolarReduction(hours=[10], factor=0.5)):
        failures += 1
    # Accept: factor=0 (total blackout)
    if not expect_accept("factor=0 (blackout)", lambda: SolarReduction(hours=[10], factor=0.0)):
        failures += 1
    # Accept: factor=1 (no reduction)
    if not expect_accept("factor=1 (no reduction)", lambda: SolarReduction(hours=[10], factor=1.0)):
        failures += 1
    # Reject: factor < 0
    if not expect_reject("factor=-0.1", lambda: SolarReduction(hours=[10], factor=-0.1)):
        failures += 1
    # Reject: factor > 1
    if not expect_reject("factor=1.5", lambda: SolarReduction(hours=[10], factor=1.5)):
        failures += 1
    # Reject: empty hours
    if not expect_reject("hours=[]", lambda: SolarReduction(hours=[], factor=0.5)):
        failures += 1
    # Reject: hour out of range
    if not expect_reject("hours=[24]", lambda: SolarReduction(hours=[24], factor=0.5)):
        failures += 1
    if not expect_reject("hours=[-1]", lambda: SolarReduction(hours=[-1], factor=0.5)):
        failures += 1
    # Accept: multiple hours
    if not expect_accept("multiple hours",
                         lambda: SolarReduction(hours=[10, 11, 12], factor=0.5)):
        failures += 1
    return failures


# ===================== MaxGridWindow =====================
def test_max_grid_window():
    print("--- MaxGridWindow ---")
    failures = 0
    # Accept: cap=0 (blackout)
    if not expect_accept("cap=0 (blackout)", lambda: MaxGridWindow(hours=[10], max_grid_kwh=0)):
        failures += 1
    # Accept: cap=1000
    if not expect_accept("cap=1000", lambda: MaxGridWindow(hours=[10], max_grid_kwh=1000)):
        failures += 1
    # Reject: cap < 0
    if not expect_reject("cap=-10", lambda: MaxGridWindow(hours=[10], max_grid_kwh=-10)):
        failures += 1
    # Reject: empty hours
    if not expect_reject("hours=[]", lambda: MaxGridWindow(hours=[], max_grid_kwh=100)):
        failures += 1
    return failures


# ===================== MinimumBatteryReserve =====================
def test_min_battery_reserve():
    print("--- MinimumBatteryReserve ---")
    failures = 0
    if not expect_accept("reserve=100", lambda: MinimumBatteryReserve(hours=[10], minimum_energy_kwh=100)):
        failures += 1
    if not expect_accept("reserve=0", lambda: MinimumBatteryReserve(hours=[10], minimum_energy_kwh=0)):
        failures += 1
    if not expect_reject("reserve=-10", lambda: MinimumBatteryReserve(hours=[10], minimum_energy_kwh=-10)):
        failures += 1
    if not expect_reject("hours=[]", lambda: MinimumBatteryReserve(hours=[], minimum_energy_kwh=100)):
        failures += 1
    return failures


# ===================== DirectiveInterpretation =====================
def test_directive_interpretation():
    print("--- DirectiveInterpretation ---")
    failures = 0
    # Accept: no_op with applies=false and adj=null
    if not expect_accept("no_op applies=false",
                         lambda: DirectiveInterpretation(note_index=0, applies=False,
                                                          directive_type="no_op",
                                                          structured_adjustment=None,
                                                          explanation="test")):
        failures += 1
    # Reject: no_op with applies=true
    if not expect_reject("no_op applies=true",
                         lambda: DirectiveInterpretation(note_index=0, applies=True,
                                                          directive_type="no_op",
                                                          structured_adjustment=None,
                                                          explanation="test")):
        failures += 1
    # Reject: no_op with adj present
    if not expect_reject("no_op adj present",
                         lambda: DirectiveInterpretation(note_index=0, applies=False,
                                                          directive_type="no_op",
                                                          structured_adjustment={"hours": [10]},
                                                          explanation="test")):
        failures += 1
    # Reject: max_grid_window with applies=false
    if not expect_reject("max_grid_window applies=false",
                         lambda: DirectiveInterpretation(note_index=0, applies=False,
                                                          directive_type="max_grid_window",
                                                          structured_adjustment={"hours": [10], "max_grid_kwh": 100},
                                                          explanation="test")):
        failures += 1
    # Reject: max_grid_window with no adjustment
    if not expect_reject("max_grid_window no adj",
                         lambda: DirectiveInterpretation(note_index=0, applies=True,
                                                          directive_type="max_grid_window",
                                                          structured_adjustment=None,
                                                          explanation="test")):
        failures += 1
    # Accept: solar_reduction with valid adj
    if not expect_accept("solar_reduction valid",
                         lambda: DirectiveInterpretation(note_index=0, applies=True,
                                                          directive_type="solar_reduction",
                                                          structured_adjustment={"hours": [10], "factor": 0.5},
                                                          explanation="test")):
        failures += 1
    # Reject: solar_reduction with invalid factor
    if not expect_reject("solar_reduction factor=1.5",
                         lambda: DirectiveInterpretation(note_index=0, applies=True,
                                                          directive_type="solar_reduction",
                                                          structured_adjustment={"hours": [10], "factor": 1.5},
                                                          explanation="test")):
        failures += 1
    # Reject: solar_reduction with empty hours
    if not expect_reject("solar_reduction hours=[]",
                         lambda: DirectiveInterpretation(note_index=0, applies=True,
                                                          directive_type="solar_reduction",
                                                          structured_adjustment={"hours": [], "factor": 0.5},
                                                          explanation="test")):
        failures += 1
    # Reject: max_grid_window with negative cap
    if not expect_reject("max_grid_window cap=-1",
                         lambda: DirectiveInterpretation(note_index=0, applies=True,
                                                          directive_type="max_grid_window",
                                                          structured_adjustment={"hours": [10], "max_grid_kwh": -1},
                                                          explanation="test")):
        failures += 1
    # Accept: max_grid_window with cap=0 (blackout allowed)
    if not expect_accept("max_grid_window cap=0 (blackout)",
                         lambda: DirectiveInterpretation(note_index=0, applies=True,
                                                          directive_type="max_grid_window",
                                                          structured_adjustment={"hours": [10], "max_grid_kwh": 0},
                                                          explanation="test")):
        failures += 1
    return failures


# ===================== OptimizeRequest =====================
def test_optimize_request():
    print("--- OptimizeRequest ---")
    failures = 0
    valid_hour = lambda h: HourEntry(hour=h, demand_kwh=100, solar_kwh=50, tariff_bdt_per_kwh=10)
    valid_battery = lambda: BatterySpec(
        capacity_kwh=200, initial_energy_kwh=100, minimum_energy_kwh=20,
        max_charge_kwh_per_hour=50, max_discharge_kwh_per_hour=50,
    )

    # Accept: 24 unique hours
    if not expect_accept("24 unique hours",
                         lambda: OptimizeRequest(
                             scenario_id="test", operator_notes=["test"],
                             hours=[valid_hour(h) for h in range(24)],
                             battery=valid_battery(),
                         )):
        failures += 1
    # Reject: missing hours
    if not expect_reject("missing hours",
                         lambda: OptimizeRequest(
                             scenario_id="test", operator_notes=["test"],
                             hours=[valid_hour(h) for h in range(23)],
                             battery=valid_battery(),
                         )):
        failures += 1
    # Reject: duplicate hours (hour 0 appears twice)
    if not expect_reject("duplicate hours",
                         lambda: OptimizeRequest(
                             scenario_id="test", operator_notes=["test"],
                             hours=[valid_hour(0), valid_hour(0)] + [valid_hour(h) for h in range(2, 24)],
                             battery=valid_battery(),
                         )):
        failures += 1
    # Reject: hour out of range
    if not expect_reject("hour=24",
                         lambda: OptimizeRequest(
                             scenario_id="test", operator_notes=["test"],
                             hours=[valid_hour(h) for h in range(23)] + [HourEntry(hour=24, demand_kwh=100, solar_kwh=50, tariff_bdt_per_kwh=10)],
                             battery=valid_battery(),
                         )):
        failures += 1
    # Reject: empty operator_notes
    if not expect_reject("empty operator_notes",
                         lambda: OptimizeRequest(
                             scenario_id="test", operator_notes=[],
                             hours=[valid_hour(h) for h in range(24)],
                             battery=valid_battery(),
                         )):
        failures += 1
    # Reject: too many notes
    if not expect_reject("4 operator_notes",
                         lambda: OptimizeRequest(
                             scenario_id="test", operator_notes=["a", "b", "c", "d"],
                             hours=[valid_hour(h) for h in range(24)],
                             battery=valid_battery(),
                         )):
        failures += 1
    # Reject: initial_energy > capacity
    if not expect_reject("initial > capacity",
                         lambda: OptimizeRequest(
                             scenario_id="test", operator_notes=["test"],
                             hours=[valid_hour(h) for h in range(24)],
                             battery=BatterySpec(
                                 capacity_kwh=100, initial_energy_kwh=200,
                                 minimum_energy_kwh=20, max_charge_kwh_per_hour=50,
                                 max_discharge_kwh_per_hour=50,
                             ),
                         )):
        failures += 1
    # Reject: initial < minimum
    if not expect_reject("initial < minimum",
                         lambda: OptimizeRequest(
                             scenario_id="test", operator_notes=["test"],
                             hours=[valid_hour(h) for h in range(24)],
                             battery=BatterySpec(
                                 capacity_kwh=200, initial_energy_kwh=10,
                                 minimum_energy_kwh=50, max_charge_kwh_per_hour=50,
                                 max_discharge_kwh_per_hour=50,
                             ),
                         )):
        failures += 1
    return failures


def main():
    tests = [
        test_solar_reduction,
        test_max_grid_window,
        test_min_battery_reserve,
        test_directive_interpretation,
        test_optimize_request,
    ]
    total_failures = 0
    for test in tests:
        group_failures = test()
        total_failures += group_failures
        print()
    print(f"{'=' * 60}")
    if total_failures == 0:
        print("ALL PYDANTIC TESTS PASSED")
        return 0
    print(f"{total_failures} TEST(S) FAILED ACROSS ALL GROUPS")
    return 1


if __name__ == "__main__":
    sys.exit(main())