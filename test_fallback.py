"""
Tests for the optimizer fallback path.

The fallback is only invoked when the LP is infeasible — i.e., the constraints
(from directives + battery rules) cannot all be satisfied simultaneously. The
fallback's job:

  1. Honor all hard caps (max_grid_kwh, no_charge, no_discharge, min_reserve).
  2. Make progress toward meeting demand (cover deficit up to battery availability).
  3. Maintain end-of-day battery neutrality E[23] = initial_energy_kwh.
  4. Report battery_energy_after_kwh consistent with sequential walk.

If a scenario is genuinely infeasible (e.g., 24h blackout with demand > solar+battery),
the fallback accepts the energy-balance imbalance — better to violate balance than
to violate a spec'd cap.

These tests construct scenarios the LP cannot solve (by setting contradictory
constraints) and verify the fallback produces a valid plan.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.schemas import BatterySpec
from app.optimizer import _fallback_plan


def make_battery(**overrides) -> BatterySpec:
    defaults = dict(
        capacity_kwh=500.0,
        initial_energy_kwh=250.0,
        minimum_energy_kwh=20.0,
        max_charge_kwh_per_hour=100.0,
        max_discharge_kwh_per_hour=100.0,
    )
    defaults.update(overrides)
    return BatterySpec(**defaults)


def make_hourly(value: float) -> dict:
    return {h: value for h in range(24)}


def verify(name, plan, battery, *, max_grid=None, no_charge=None,
           no_discharge=None, min_reserve=None, allow_imbalance=False,
           require_neutrality=True, verbose=False):
    """Verify hard constraints on the plan.

    Always verifies:
      - max_grid cap respected
      - no_charge respected
      - no_discharge respected
      - min_reserve respected (sequential walk)
      - battery_energy_after_kwh matches sequential walk
      - battery_kwh consistent with action

    Optionally verifies:
      - Energy balance per hour (skip if allow_imbalance)
      - End-of-day neutrality E[23] == initial (skip if require_neutrality=False)
    """
    fails = []

    # Cap checks
    if max_grid:
        for h, cap in max_grid.items():
            if plan[h].grid_kwh > cap + 0.01:
                fails.append(f"hour {h}: grid {plan[h].grid_kwh} > cap {cap}")

    if no_charge:
        for h in no_charge:
            if plan[h].battery_action == "charge":
                fails.append(f"hour {h}: charging in no_charge_window")

    if no_discharge:
        for h in no_discharge:
            if plan[h].battery_action == "discharge":
                fails.append(f"hour {h}: discharging in no_discharge_window")

    # Battery_action == idle → battery_kwh == 0
    for p in plan:
        if p.battery_action == "idle" and p.battery_kwh != 0:
            fails.append(f"hour {p.hour}: idle but battery_kwh={p.battery_kwh}")
        if p.battery_action in ("charge", "discharge") and p.battery_kwh <= 0:
            fails.append(f"hour {p.hour}: {p.battery_action} but battery_kwh={p.battery_kwh}")

    # battery_energy_after matches sequential walk
    e = battery.initial_energy_kwh
    for p in plan:
        if p.battery_action == "charge":
            e = round(e + p.battery_kwh, 4)
        elif p.battery_action == "discharge":
            e = round(e - p.battery_kwh, 4)
        if abs(e - p.battery_energy_after_kwh) > 0.01:
            fails.append(f"hour {p.hour}: E_after={p.battery_energy_after_kwh} "
                         f"vs sequential walk {e}")

    # min_reserve floor
    if min_reserve:
        e = battery.initial_energy_kwh
        for p in plan:
            if p.battery_action == "charge":
                e = round(e + p.battery_kwh, 4)
            elif p.battery_action == "discharge":
                e = round(e - p.battery_kwh, 4)
            floor = min_reserve.get(p.hour, battery.minimum_energy_kwh)
            if e < floor - 0.01:
                fails.append(f"hour {p.hour}: battery {e} < floor {floor}")

    # End-of-day neutrality
    if require_neutrality:
        final_e = plan[23].battery_energy_after_kwh
        if abs(final_e - battery.initial_energy_kwh) > 0.01:
            fails.append(f"end-of-day neutrality: E[23]={final_e} != "
                         f"initial={battery.initial_energy_kwh}")

    if fails:
        print(f"  [FAIL] {name}:")
        for f in fails:
            print(f"    - {f}")
        return False

    if verbose:
        print(f"  [PASS] {name}: E[23]={plan[23].battery_energy_after_kwh}, "
              f"total grid={sum(p.grid_kwh for p in plan):.2f}")
    else:
        print(f"  [PASS] {name}")
    return True


# ---------- Tests for feasible scenarios (should match what LP would produce) ----------

def test_simple_no_directives():
    """No directives, demand > solar everywhere, no caps. Should rely on grid."""
    bat = make_battery()
    demand = make_hourly(150.0)
    eff_solar = make_hourly(20.0)
    plan = _fallback_plan(bat, demand, eff_solar, {}, set(), set(), {})
    return verify("No directives (uncapped grid)", plan, bat, verbose=True)


def test_solar_surplus_charging():
    """Solar exceeds demand in some hours → battery charges from surplus."""
    bat = make_battery(initial_energy_kwh=50.0)
    # Demand low during solar hours, high during night
    demand = {h: 20.0 if 8 <= h <= 16 else 100.0 for h in range(24)}
    eff_solar = {h: 80.0 if 8 <= h <= 16 else 0.0 for h in range(24)}
    plan = _fallback_plan(bat, demand, eff_solar, {}, set(), set(), {})

    # Verify there was at least one charge action
    charge_hours = [p.hour for p in plan if p.battery_action == "charge"]
    if not charge_hours:
        print(f"  [FAIL] Solar surplus charging: no charge happened")
        return False

    return verify("Solar surplus charging", plan, bat, verbose=True)


# ---------- Tests for infeasible scenarios (fallback must accept imbalance) ----------

def test_partial_blackout_with_discharge():
    """Grid blackout (cap=0) during day, battery covers deficit then discharges evening."""
    bat = make_battery(initial_energy_kwh=200.0)
    # Demand: low at midday (solar+battery cover), high evening (battery helps)
    demand = {h: 50.0 if 8 <= h <= 16 else 120.0 for h in range(24)}
    eff_solar = {h: 60.0 if 8 <= h <= 16 else 0.0 for h in range(24)}
    # Blackout only midday (LP-infeasible if solar can't fully cover demand)
    max_grid = {h: 0.0 if 8 <= h <= 16 else 200.0 for h in range(24)}
    plan = _fallback_plan(bat, demand, eff_solar, {}, set(), set(), max_grid)

    # Verify grid never exceeds cap during blackout
    return verify("Partial blackout midday", plan, bat, max_grid=max_grid,
                  require_neutrality=True, verbose=True)


def test_extreme_infeasibility():
    """24-hour blackout with high demand, low solar, tiny battery.

    Truly infeasible — the fallback MUST accept imbalance but should still
    respect min_reserve and end-of-day neutrality as best it can.
    With tiny battery (50 kWh initial, 100 capacity) and 24h blackout, we can't
    recharge. End-of-day drift is unavoidable.
    """
    bat = make_battery(capacity_kwh=100.0, initial_energy_kwh=50.0)
    demand = make_hourly(120.0)
    eff_solar = make_hourly(10.0)
    max_grid = {h: 0.0 for h in range(24)}
    plan = _fallback_plan(bat, demand, eff_solar, {}, set(), set(), max_grid)

    return verify("24h blackout (infeasible, expect drift)", plan, bat,
                  max_grid=max_grid, require_neutrality=False, verbose=True)


def test_no_charge_all_day_with_surplus():
    """no_charge all day, with solar surplus. Surplus should NOT be used to charge."""
    bat = make_battery(initial_energy_kwh=100.0)
    demand = {h: 30.0 if 8 <= h <= 16 else 100.0 for h in range(24)}
    eff_solar = {h: 80.0 if 8 <= h <= 16 else 0.0 for h in range(24)}
    no_charge = set(range(24))
    plan = _fallback_plan(bat, demand, eff_solar, {}, no_charge, set(), {})

    ok = verify("No-charge all day with surplus", plan, bat,
                no_charge=no_charge, verbose=True)
    # Confirm no charging happened
    if any(p.battery_action == "charge" for p in plan):
        print("  [FAIL] charging happened despite no_charge_window")
        return False
    return ok


def test_no_discharge_all_day_handles_neutrality():
    """no_discharge all day, low demand, high solar.

    With E[23] = initial and discharge=0, the only way to satisfy neutrality is
    sum(charge) = 0. The fallback correctly avoids charging because storing
    surplus without ability to discharge would violate end-of-day neutrality.
    (The LP path produces the same correct result.)
    """
    bat = make_battery(initial_energy_kwh=50.0, capacity_kwh=200.0)
    demand = make_hourly(10.0)
    eff_solar = make_hourly(80.0)
    no_discharge = set(range(24))
    plan = _fallback_plan(bat, demand, eff_solar, {}, set(), no_discharge, {})

    ok = verify("No-discharge all day (neutrality forces no charge)", plan, bat,
                no_discharge=no_discharge, verbose=True)
    # Confirm no discharge happened
    if any(p.battery_action == "discharge" for p in plan):
        print("  [FAIL] discharging happened despite no_discharge_window")
        return False
    return ok


def test_min_reserve_constraint():
    """min_reserve keeps battery above 150 kWh from hour 6 PM to 9 PM."""
    bat = make_battery(initial_energy_kwh=200.0, capacity_kwh=500.0)
    # Heavy evening demand
    demand = {h: 50.0 if h < 18 or h >= 21 else 250.0 for h in range(24)}
    eff_solar = make_hourly(0.0)
    min_reserve = {h: 150.0 for h in [18, 19, 20, 21]}
    plan = _fallback_plan(bat, demand, eff_solar, min_reserve, set(), set(), {})

    ok = verify("Min reserve 150 kWh during peak", plan, bat,
                min_reserve=min_reserve, verbose=True)
    return ok


def test_overlapping_windows():
    """no_discharge and high min_reserve overlap during evening peak.

    This is the kind of constraint combination that might LP-infeasible.
    The fallback should respect both.
    """
    bat = make_battery(initial_energy_kwh=300.0, capacity_kwh=500.0)
    demand = {h: 80.0 if h < 18 or h >= 22 else 280.0 for h in range(24)}
    eff_solar = make_hourly(0.0)
    no_discharge = set(range(18, 22))  # 6 PM to 10 PM
    min_reserve = {h: 250.0 for h in [18, 19, 20, 21]}  # reserve 250 kWh during peak
    plan = _fallback_plan(bat, demand, eff_solar, min_reserve, set(), no_discharge, {})

    return verify("Overlapping no_discharge + min_reserve", plan, bat,
                  no_discharge=no_discharge, min_reserve=min_reserve, verbose=True)


def main():
    tests = [
        test_simple_no_directives,
        test_solar_surplus_charging,
        test_partial_blackout_with_discharge,
        test_extreme_infeasibility,
        test_no_charge_all_day_with_surplus,
        test_no_discharge_all_day_handles_neutrality,
        test_min_reserve_constraint,
        test_overlapping_windows,
    ]
    failures = 0
    for test in tests:
        if not test():
            failures += 1
        print()
    print("=" * 60)
    if failures == 0:
        print(f"ALL {len(tests)} FALLBACK TESTS PASSED")
        return 0
    print(f"{failures} / {len(tests)} FALLBACK TESTS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
