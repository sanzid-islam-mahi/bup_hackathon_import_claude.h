"""End-to-end test: send each sample case to the optimizer and verify invariants."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.schemas import OptimizeRequest, OptimizeResponse
from app.interpreter import interpret_notes
from app.optimizer import optimize
from samples_loader import load_samples


def verify_plan(req: OptimizeRequest, resp: OptimizeResponse) -> list:
    """Verify the optimizer's plan satisfies all constraints. Returns list of issues."""
    issues = []
    TOL = 0.5
    b = req.battery

    # 1. End-of-day neutrality
    final_E = resp.hourly_plan[23].battery_energy_after_kwh
    if abs(final_E - b.initial_energy_kwh) > TOL:
        issues.append(f"end-of-day battery {final_E} != initial {b.initial_energy_kwh}")

    # 2. Energy balance every hour
    for p in resp.hourly_plan:
        h = req.hours[p.hour]
        demand = h.demand_kwh
        charge = p.battery_kwh if p.battery_action == "charge" else 0.0
        discharge = p.battery_kwh if p.battery_action == "discharge" else 0.0
        balance_lhs = p.grid_kwh + p.solar_used_kwh + discharge
        balance_rhs = demand + charge
        if abs(balance_lhs - balance_rhs) > 0.5:
            issues.append(f"hour {p.hour}: energy balance LHS={balance_lhs:.2f} RHS={balance_rhs:.2f}")

    # 3. Battery bounds (no min_reserve in this check, just base)
    for p in resp.hourly_plan:
        if p.battery_energy_after_kwh < b.minimum_energy_kwh - TOL:
            issues.append(f"hour {p.hour}: battery {p.battery_energy_after_kwh} < min {b.minimum_energy_kwh}")
        if p.battery_energy_after_kwh > b.capacity_kwh + TOL:
            issues.append(f"hour {p.hour}: battery {p.battery_energy_after_kwh} > capacity {b.capacity_kwh}")

    # 4. Rate limits
    for p in resp.hourly_plan:
        if p.battery_action == "charge" and p.battery_kwh > b.max_charge_kwh_per_hour + TOL:
            issues.append(f"hour {p.hour}: charge {p.battery_kwh} > max {b.max_charge_kwh_per_hour}")
        if p.battery_action == "discharge" and p.battery_kwh > b.max_discharge_kwh_per_hour + TOL:
            issues.append(f"hour {p.hour}: discharge {p.battery_kwh} > max {b.max_discharge_kwh_per_hour}")

    # 5. Solar usage ≤ effective_solar (basic; directives need extra check)
    eff_solar = list(h.solar_kwh for h in req.hours)
    for d in resp.directive_interpretation:
        if d.directive_type == "solar_reduction" and d.applies and d.structured_adjustment:
            factor = d.structured_adjustment["factor"]
            for h in d.structured_adjustment["hours"]:
                eff_solar[h] *= factor
    for p in resp.hourly_plan:
        if p.solar_used_kwh > eff_solar[p.hour] + 0.01:
            issues.append(f"hour {p.hour}: solar_used {p.solar_used_kwh} > eff_solar {eff_solar[p.hour]}")

    # 6. Directive application
    for d in resp.directive_interpretation:
        if not d.applies or d.directive_type == "no_op":
            continue
        adj = d.structured_adjustment or {}
        if d.directive_type == "no_charge_window":
            for h in adj.get("hours", []):
                if resp.hourly_plan[h].battery_action == "charge":
                    issues.append(f"hour {h}: charging in no_charge_window")
        elif d.directive_type == "no_discharge_window":
            for h in adj.get("hours", []):
                if resp.hourly_plan[h].battery_action == "discharge":
                    issues.append(f"hour {h}: discharging in no_discharge_window")
        elif d.directive_type == "max_grid_window":
            for h in adj.get("hours", []):
                if resp.hourly_plan[h].grid_kwh > adj["max_grid_kwh"] + 0.5:
                    issues.append(f"hour {h}: grid {resp.hourly_plan[h].grid_kwh} > cap {adj['max_grid_kwh']}")

    # 7. Totals
    recalc_grid = sum(p.grid_kwh for p in resp.hourly_plan)
    recalc_cost = sum(p.grid_kwh * req.hours[p.hour].tariff_bdt_per_kwh for p in resp.hourly_plan)
    recalc_peak = max(p.grid_kwh for p in resp.hourly_plan)
    if abs(recalc_grid - resp.total_grid_kwh) > 0.5:
        issues.append(f"total_grid_kwh mismatch: {recalc_grid} vs {resp.total_grid_kwh}")
    if abs(recalc_cost - resp.total_cost_bdt) > 0.5:
        issues.append(f"total_cost_bdt mismatch: {recalc_cost} vs {resp.total_cost_bdt}")
    if abs(recalc_peak - resp.peak_grid_kwh) > 0.5:
        issues.append(f"peak_grid_kwh mismatch: {recalc_peak} vs {resp.peak_grid_kwh}")

    return issues


def main():
    cases = load_samples()
    full_pass = 0
    for case in cases:
        inp = case["input"]
        req = OptimizeRequest(**inp)
        interpretations = interpret_notes(req)
        result = optimize(req, interpretations)
        issues = verify_plan(req, result)

        ok = not issues
        status = "✓" if ok else "✗"
        print(f"{status} {case['id']}: cost={result.total_cost_bdt:.0f} BDT, grid={result.total_grid_kwh:.0f} kWh, peak={result.peak_grid_kwh:.0f} kWh")
        if not ok:
            for i in issues[:5]:
                print(f"    - {i}")
            if len(issues) > 5:
                print(f"    ... and {len(issues) - 5} more")
        else:
            full_pass += 1
    print(f"\n{full_pass}/{len(cases)} passed constraint validation")


if __name__ == "__main__":
    main()
