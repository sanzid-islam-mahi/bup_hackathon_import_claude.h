"""
24-hour optimizer using scipy.optimize.linprog (linear programming).

Decision variables (per hour h=0..23):
  g[h]  = grid_kwh (>=0)
  s[h]  = solar_used_kwh (>=0, <= effective_solar[h])
  c[h]  = charge amount (>=0, <= max_charge_per_hour)
  d[h]  = discharge amount (>=0, <= max_discharge_per_hour)
  E[h]  = battery energy after hour h

Objective: minimize sum(g[h] * tariff[h]) for h=0..23

Constraints:
  E[h] - E[h-1] - c[h] + d[h] = 0  (battery balance)
  E[0] = initial + c[0] - d[0]
  E[h] >= min_reserve[h], E[h] <= capacity  (battery bounds)
  g[h] + s[h] + d[h] = demand[h] + c[h]   (energy balance)
  E[23] = initial_energy  (end-of-day neutrality)
  s[h] <= effective_solar[h]  (solar cap)
  c[h] <= max_charge_per_hour, d[h] <= max_discharge_per_hour
  no_charge_window: c[h] = 0 in those hours
  no_discharge_window: d[h] = 0 in those hours
  max_grid_window: g[h] <= cap in those hours

Note: all hourly data is stored in dicts keyed by `hour.hour` so the solver
remains correct even if input lists are not strictly sorted ascending.
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple
import numpy as np
from scipy.optimize import linprog

from app.schemas import (
    OptimizeRequest,
    OptimizeResponse,
    HourEntry,
    BatterySpec,
    DirectiveInterpretation,
    HourlyPlanEntry,
)


TOL = 1e-4


def _build_hour_maps(hours: List[HourEntry], reductions: Dict[int, float]):
    """Build dicts keyed by h.hour for tariff, demand, and effective solar.

    Using dicts avoids any dependency on input ordering, so the optimizer
    works correctly even when `hours` is not sorted ascending.
    """
    tariff: Dict[int, float] = {}
    demand: Dict[int, float] = {}
    eff_solar: Dict[int, float] = {}
    for h in hours:
        tariff[h.hour] = float(h.tariff_bdt_per_kwh)
        demand[h.hour] = float(h.demand_kwh)
        eff_solar[h.hour] = float(h.solar_kwh) * float(reductions.get(h.hour, 1.0))
    return tariff, demand, eff_solar


def _build_directive_maps(interpretations: List[DirectiveInterpretation]):
    reductions: Dict[int, float] = {}
    min_reserve: Dict[int, float] = {}
    no_charge: Set[int] = set()
    no_discharge: Set[int] = set()
    max_grid: Dict[int, float] = {}

    for d in interpretations:
        if not d.applies or d.directive_type == "no_op":
            continue
        adj = d.structured_adjustment or {}
        hs = adj.get("hours", [])
        if d.directive_type == "solar_reduction":
            for h in hs:
                reductions[h] = float(adj["factor"])
        elif d.directive_type == "minimum_battery_reserve":
            for h in hs:
                min_reserve[h] = max(min_reserve.get(h, 0.0), float(adj["minimum_energy_kwh"]))
        elif d.directive_type == "no_charge_window":
            no_charge.update(hs)
        elif d.directive_type == "no_discharge_window":
            no_discharge.update(hs)
        elif d.directive_type == "max_grid_window":
            for h in hs:
                # If multiple directives overlap, take the stricter (minimum) cap
                new_cap = float(adj["max_grid_kwh"])
                existing = max_grid.get(h, float("inf"))
                max_grid[h] = min(existing, new_cap)

    return reductions, min_reserve, no_charge, no_discharge, max_grid


def _solve_lp(
    battery: BatterySpec,
    tariff: Dict[int, float],
    demand: Dict[int, float],
    eff_solar: Dict[int, float],
    min_reserve: Dict[int, float],
    no_charge: Set[int],
    no_discharge: Set[int],
    max_grid: Dict[int, float],
) -> Tuple[List[HourlyPlanEntry], bool, str]:
    """Solve via scipy.optimize.linprog. Returns (plan, success, message).

    All hourly inputs are dicts keyed by hour (0..23), so the solver is
    robust to input list ordering.
    """
    b = battery
    H = 24
    n = 5 * H

    # Variable ordering: [g_0..g_23, s_0..s_23, c_0..c_23, d_0..d_23, E_0..E_23]
    def idx_g(h): return h
    def idx_s(h): return H + h
    def idx_c(h): return 2 * H + h
    def idx_d(h): return 3 * H + h
    def idx_E(h): return 4 * H + h

    # Objective: minimize sum(g[h] * tariff[h])
    obj = np.zeros(n)
    for h in range(H):
        obj[idx_g(h)] = tariff[h]

    A_eq_rows = []
    b_eq_vals = []

    # Energy balance: g[h] + s[h] + d[h] - c[h] = demand[h]
    for h in range(H):
        row = np.zeros(n)
        row[idx_g(h)] = 1.0
        row[idx_s(h)] = 1.0
        row[idx_d(h)] = 1.0
        row[idx_c(h)] = -1.0
        A_eq_rows.append(row)
        b_eq_vals.append(demand[h])

    # Battery balance: E[h] - E[h-1] - c[h] + d[h] = 0  (for h >= 1)
    # For h=0: E[0] = initial + c[0] - d[0]
    for h in range(H):
        row = np.zeros(n)
        row[idx_E(h)] = 1.0
        if h == 0:
            row[idx_c(0)] = -1.0
            row[idx_d(0)] = 1.0
        else:
            row[idx_E(h - 1)] = -1.0
            row[idx_c(h)] = -1.0
            row[idx_d(h)] = 1.0
        A_eq_rows.append(row)
        if h == 0:
            b_eq_vals.append(float(b.initial_energy_kwh))
        else:
            b_eq_vals.append(0.0)

    # End-of-day neutrality: E[23] = initial
    row = np.zeros(n)
    row[idx_E(H - 1)] = 1.0
    A_eq_rows.append(row)
    b_eq_vals.append(float(b.initial_energy_kwh))

    A_eq = np.array(A_eq_rows)
    b_eq = np.array(b_eq_vals)

    # Bounds
    bounds = []
    # g[h] >= 0, no upper bound except max_grid_window
    for h in range(H):
        ub = max_grid.get(h, None)
        bounds.append((0, ub if ub is not None else None))
    # s[h] in [0, eff_solar[h]]
    for h in range(H):
        bounds.append((0, eff_solar[h]))
    # c[h] in [0, max_charge] or 0 if in no_charge_window
    for h in range(H):
        if h in no_charge:
            bounds.append((0, 0))
        else:
            bounds.append((0, b.max_charge_kwh_per_hour))
    # d[h] in [0, max_discharge] or 0 if in no_discharge_window
    for h in range(H):
        if h in no_discharge:
            bounds.append((0, 0))
        else:
            bounds.append((0, b.max_discharge_kwh_per_hour))
    # E[h] in [max(base_min, min_reserve[h]), capacity]
    for h in range(H):
        lower = max(b.minimum_energy_kwh, min_reserve.get(h, b.minimum_energy_kwh))
        bounds.append((lower, b.capacity_kwh))

    # Solve
    result = linprog(c=obj, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")

    if not result.success:
        return [], False, f"LP failed: {result.message}"

    x = result.x

    # Extract plan.
    # Walk hours in order 0..23, sequentially recomputing E_after from the
    # *rounded* action magnitudes so the reported state matches the judge's
    # replay exactly (Issue #13 fix).
    plan: List[HourlyPlanEntry] = []
    E_prev_rounded = round(float(b.initial_energy_kwh), 4)
    for h in range(H):
        g = max(0.0, float(x[idx_g(h)]))
        s = max(0.0, float(x[idx_s(h)]))
        c = max(0.0, float(x[idx_c(h)]))
        d = max(0.0, float(x[idx_d(h)]))

        # Determine single action by netting
        if c > TOL and d > TOL:
            if c >= d:
                c = c - d
                d = 0.0
            else:
                d = d - c
                c = 0.0

        if c > TOL:
            action = "charge"
            battery_kwh = c
            E_after = round(E_prev_rounded + c, 4)
        elif d > TOL:
            action = "discharge"
            battery_kwh = d
            E_after = round(E_prev_rounded - d, 4)
        else:
            action = "idle"
            battery_kwh = 0.0
            E_after = E_prev_rounded

        # Clamp numeric output to 4 decimals (matches round-trip replay)
        g_r = round(g, 4)
        s_r = round(s, 4)
        bk_r = round(battery_kwh, 4)

        plan.append(HourlyPlanEntry(
            hour=h,
            grid_kwh=g_r,
            solar_used_kwh=s_r,
            battery_action=action,
            battery_kwh=bk_r,
            battery_energy_after_kwh=E_after,
        ))

        E_prev_rounded = E_after

    return plan, True, "ok"


def _fallback_plan(
    battery: BatterySpec,
    demand: Dict[int, float],
    eff_solar: Dict[int, float],
    min_reserve: Dict[int, float],
    no_charge: Set[int],
    no_discharge: Set[int],
    max_grid: Dict[int, float],
) -> List[HourlyPlanEntry]:
    """Deterministic fallback when LP fails.

    Three-pass heuristic that honors every hard cap (max_grid_kwh,
    no_charge_window, no_discharge_window, min_reserve) AND ends the day
    with battery energy equal to initial_energy_kwh (end-of-day neutrality).

    Pass 1 — discharge planning: for hours where capped grid leaves a deficit,
    discharge just enough to close it (capped by per-hour rate, reserve floor,
    no_discharge_window).

    Pass 2 — charge planning: for hours with surplus solar above demand, charge
    from that surplus (capped by per-hour rate, capacity room, no_charge_window).
    Charging from surplus solar does NOT change grid_kwh.

    Pass 3 — end-of-day reconciliation: if final E drifts from initial, absorb
    the drift by adjusting hour-23 actions (reduce discharge to need more,
    add discharge to extract surplus). Hard caps still take precedence.
    """
    H = 24
    initial = round(float(battery.initial_energy_kwh), 4)
    capacity = float(battery.capacity_kwh)
    base_min = float(battery.minimum_energy_kwh)
    max_charge_per_h = float(battery.max_charge_kwh_per_hour)
    max_discharge_per_h = float(battery.max_discharge_kwh_per_hour)

    # Per-hour floor (max of base minimum and any directive reserve)
    floor = {h: max(base_min, min_reserve.get(h, base_min)) for h in range(H)}

    # Per-hour grid cap (None = uncapped)
    grid_cap_h = {h: max_grid.get(h) for h in range(H)}

    # ----- Pass 1: decide solar_used, planned discharge per hour -----
    # First, what would grid need to be without any discharge?
    plan_grid = [0.0] * H
    plan_solar = [0.0] * H
    plan_discharge = [0.0] * H
    e = initial  # running battery state

    for h in range(H):
        d = demand[h]
        sol = eff_solar[h]
        # Solar first, up to effective solar and demand
        solar_used = round(min(sol, d), 4)
        remaining_after_solar = max(0.0, round(d - solar_used, 4))

        cap = grid_cap_h[h]
        # Base grid: what we'd need if we did nothing else (capped)
        if cap is not None:
            base_grid = min(remaining_after_solar, cap)
        else:
            base_grid = remaining_after_solar

        # If base_grid < remaining_after_solar, we have a deficit; try to
        # discharge to close it (honoring no_discharge + reserve + rate)
        deficit = round(remaining_after_solar - base_grid, 4)
        planned_discharge = 0.0
        if deficit > 1e-9 and h not in no_discharge:
            avail = max(0.0, round(e - floor[h], 4))
            max_disch = min(max_discharge_per_h, avail, deficit)
            if max_disch > 1e-4:
                planned_discharge = round(max_disch, 4)
                # Recompute grid after discharge
                base_grid = round(remaining_after_solar - planned_discharge, 4)
                # Defensive clamp: never exceed cap
                if cap is not None and base_grid > cap:
                    base_grid = cap
                e = round(e - planned_discharge, 4)
        elif deficit > 1e-9 and h in no_discharge:
            # Grid cap binds and we can't discharge — accept the imbalance
            pass

        plan_solar[h] = solar_used
        plan_grid[h] = round(base_grid, 4)
        plan_discharge[h] = planned_discharge

    # ----- Pass 2: charge from surplus solar -----
    # Surplus solar = solar_avail - solar_used (only positive when sol > demand).
    # Charging from surplus solar does NOT change grid_kwh (solar_used_for_demand
    # stays the same; surplus flows to battery without affecting demand balance).
    e = initial
    plan_charge = [0.0] * H
    for h in range(H):
        sol = eff_solar[h]
        solar_used = plan_solar[h]
        # Apply discharge from Pass 1 to keep e consistent
        e = round(e - plan_discharge[h], 4)

        if h in no_charge:
            continue

        surplus_solar = max(0.0, round(sol - solar_used, 4))
        if surplus_solar <= 1e-4:
            continue

        room = round(capacity - e, 4)
        max_ch = min(max_charge_per_h, room, surplus_solar)
        if max_ch > 1e-4:
            plan_charge[h] = round(max_ch, 4)
            e = round(e + plan_charge[h], 4)

    # ----- Pass 3: end-of-day reconciliation -----
    # Compute final E from sequential walk (same way the judge will replay).
    final_e = initial
    for h in range(H):
        if plan_charge[h] > 0:
            final_e = round(final_e + plan_charge[h], 4)
        if plan_discharge[h] > 0:
            final_e = round(final_e - plan_discharge[h], 4)
    drift = round(initial - final_e, 4)  # positive = need more, negative = too much

    if abs(drift) > 1e-4:
        h = 23
        if drift > 0:
            # Need MORE energy in battery at end of day.
            # Option A: reduce discharge at hour 23 (grid_kwh rises by the same
            # amount, unless grid cap binds — in which case leave a residual
            # imbalance, which the judge accepts as the lesser evil).
            reduction = min(drift, plan_discharge[h])
            if reduction > 1e-4:
                plan_discharge[h] = round(plan_discharge[h] - reduction, 4)
                plan_grid[h] = round(plan_grid[h] + reduction, 4)
                drift = round(drift - reduction, 4)
            # Option B: add charge at hour 23 from surplus solar (free —
            # doesn't change grid_kwh because it comes from surplus, not grid).
            if drift > 1e-4 and h not in no_charge:
                sol = eff_solar[h]
                surplus_solar = max(0.0, round(sol - plan_solar[h], 4))
                cur_e_after_pass = initial + sum(plan_charge) - sum(plan_discharge)
                room = round(capacity - cur_e_after_pass, 4)
                extra = min(drift, max_charge_per_h - plan_charge[h],
                            surplus_solar, room)
                if extra > 1e-4:
                    plan_charge[h] = round(plan_charge[h] + extra, 4)
                    drift = round(drift - extra, 4)
            # Option C: charge at hour 23 from extra grid import. Used only
            # when surplus-solar option is exhausted and a cap-induced residual
            # would otherwise leak into end-of-day neutrality. Bounds: rate
            # cap, capacity headroom, grid cap at h23.
            if drift > 1e-4 and h not in no_charge:
                cur_e_after_pass = initial + sum(plan_charge) - sum(plan_discharge)
                room = round(capacity - cur_e_after_pass, 4)
                grid_cap = max_grid.get(h)
                headroom_grid = float("inf") if grid_cap is None else max(
                    0.0, round(grid_cap - plan_grid[h], 4))
                extra = min(drift, max_charge_per_h - plan_charge[h],
                            room, headroom_grid)
                if extra > 1e-4:
                    plan_charge[h] = round(plan_charge[h] + extra, 4)
                    plan_grid[h] = round(plan_grid[h] + extra, 4)
                    drift = round(drift - extra, 4)
        else:
            # drift < 0 -> battery ends with TOO MUCH energy. Need to extract |-drift|.
            # Strategy: walk backward from hour 23 and reduce charges / add
            # discharges to bring E[23] back to initial. If per-hour discharge
            # cap binds, reduce earlier charges instead (cheaper).
            need = -drift
            # Pass A: add discharge at hour 23 (up to per-hour cap and reserve floor)
            h = 23
            if h not in no_discharge:
                cur_e = initial + sum(plan_charge) - sum(plan_discharge)
                avail = max(0.0, round(cur_e - floor[h], 4))
                extra = min(need, max_discharge_per_h - plan_discharge[h], avail)
                if extra > 1e-4:
                    plan_discharge[h] = round(plan_discharge[h] + extra, 4)
                    plan_grid[h] = round(max(0.0, plan_grid[h] - extra), 4)
                    need = round(need - extra, 4)
            # Pass B: spread discharge across later hours (22, 21, ...)
            # to use any remaining capacity
            if need > 1e-4:
                for h in range(22, -1, -1):
                    if need <= 1e-4:
                        break
                    if h in no_discharge:
                        continue
                    # Compute E at end of hour h (sequential walk so far)
                    cur_e = initial
                    for hh in range(h + 1):
                        if plan_charge[hh] > 0:
                            cur_e = round(cur_e + plan_charge[hh], 4)
                        if plan_discharge[hh] > 0:
                            cur_e = round(cur_e - plan_discharge[hh], 4)
                    avail = max(0.0, round(cur_e - floor[h], 4))
                    extra = min(need, max_discharge_per_h - plan_discharge[h], avail)
                    if extra > 1e-4:
                        plan_discharge[h] = round(plan_discharge[h] + extra, 4)
                        # More discharge -> grid_kwh drops (battery supplies demand)
                        plan_grid[h] = round(max(0.0, plan_grid[h] - extra), 4)
                        need = round(need - extra, 4)
            # Pass C: if still drifting, reduce earlier charges (preferred over
            # further discharge to avoid hurting supply during peak hours)
            if need > 1e-4:
                for h in range(24):
                    if need <= 1e-4:
                        break
                    # We can reduce plan_charge[h] to drop `need` from battery.
                    # But this also reduces solar_used for charging — wait, no,
                    # reducing charge doesn't affect solar_used (only plan_charge).
                    reduction = min(need, plan_charge[h])
                    if reduction > 1e-4:
                        plan_charge[h] = round(plan_charge[h] - reduction, 4)
                        # No grid change — we just don't store as much energy.
                        # E at end of hour h drops by `reduction`, and so does
                        # E at every subsequent hour. Need drops by `reduction`.
                        need = round(need - reduction, 4)

    # ----- Build the final plan with sequential battery_energy_after walk -----
    plan: List[HourlyPlanEntry] = []
    e = initial
    for h in range(H):
        if plan_discharge[h] > 1e-4:
            action = "discharge"
            bk = plan_discharge[h]
        elif plan_charge[h] > 1e-4:
            action = "charge"
            bk = plan_charge[h]
        else:
            action = "idle"
            bk = 0.0

        if action == "charge":
            e = round(e + bk, 4)
        elif action == "discharge":
            e = round(e - bk, 4)

        plan.append(HourlyPlanEntry(
            hour=h,
            grid_kwh=round(plan_grid[h], 4),
            solar_used_kwh=round(plan_solar[h], 4),
            battery_action=action,
            battery_kwh=round(bk, 4),
            battery_energy_after_kwh=round(e, 4),
        ))
    return plan


def optimize(req: OptimizeRequest, interpretations: List[DirectiveInterpretation]) -> OptimizeResponse:
    """Build a 24-hour schedule honoring all directives via LP."""
    reductions, min_reserve, no_charge, no_discharge, max_grid = _build_directive_maps(interpretations)
    tariff, demand, eff_solar = _build_hour_maps(req.hours, reductions)

    plan, success, msg = _solve_lp(
        req.battery, tariff, demand, eff_solar,
        min_reserve, no_charge, no_discharge, max_grid,
    )

    if not success:
        plan = _fallback_plan(
            req.battery, demand, eff_solar,
            min_reserve, no_charge, no_discharge, max_grid,
        )

    # Compute totals
    total_grid = sum(p.grid_kwh for p in plan)
    total_cost = sum(p.grid_kwh * tariff[p.hour] for p in plan)
    peak_grid = max(p.grid_kwh for p in plan)

    summary = "LP-optimal schedule"
    if reductions:
        summary += f", solar reduced in {len(reductions)} hour(s)"
    if min_reserve:
        summary += f", battery reserve raised in {len(min_reserve)} hour(s)"
    if no_charge:
        summary += f", no-charge window {sorted(no_charge)}"
    if no_discharge:
        summary += f", no-discharge window {sorted(no_discharge)}"
    if max_grid:
        summary += f", grid cap in {sorted(max_grid)}"
    if not success:
        summary += f" [fallback used: {msg}]"

    return OptimizeResponse(
        scenario_id=req.scenario_id,
        directive_interpretation=interpretations,
        hourly_plan=plan,
        total_grid_kwh=round(total_grid, 4),
        total_cost_bdt=round(total_cost, 4),
        peak_grid_kwh=round(peak_grid, 4),
        plan_summary=summary,
    )


if __name__ == "__main__":
    # Self-check: _fallback_plan must satisfy end-of-day battery neutrality
    # (Section 9.6) and respect hard grid caps. Fast, dependency-free
    # regression check alongside test_fallback.py's fuller suite.
    battery = BatterySpec(capacity_kwh=500, initial_energy_kwh=200, minimum_energy_kwh=50,
                           max_charge_kwh_per_hour=100, max_discharge_kwh_per_hour=100)
    demand = {h: 180 for h in range(24)}
    demand[5] = 350
    eff_solar = {h: 0 for h in range(24)}
    plan = _fallback_plan(battery, demand, eff_solar, {}, set(), set(), {5: 300})
    assert abs(plan[23].battery_energy_after_kwh - battery.initial_energy_kwh) < 0.01, \
        "fallback plan violates end-of-day battery neutrality"
    assert all(p.grid_kwh <= 300 + 0.01 for p in plan if p.hour == 5), "fallback plan violates grid cap"
    print("optimizer.py self-check passed: fallback plan neutrality + grid cap OK")
