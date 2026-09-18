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


def _effective_solar(hours: List[HourEntry], reductions: Dict[int, float]) -> List[float]:
    return [h.solar_kwh * reductions.get(h.hour, 1.0) for h in hours]


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
                max_grid[h] = float(adj["max_grid_kwh"])

    return reductions, min_reserve, no_charge, no_discharge, max_grid


def _solve_lp(
    hours: List[HourEntry],
    battery: BatterySpec,
    eff_solar: List[float],
    min_reserve: Dict[int, float],
    no_charge: Set[int],
    no_discharge: Set[int],
    max_grid: Dict[int, float],
) -> Tuple[List[HourlyPlanEntry], bool, str]:
    """Solve via scipy.optimize.linprog. Returns (plan, success, message)."""
    b = battery
    H = 24
    # Variables: g[0..23], s[0..23], c[0..23], d[0..23], E[0..23]
    # That's 5*24 = 120 variables.
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
        obj[idx_g(h)] = float(hours[h].tariff_bdt_per_kwh)

    # Equality constraints (A_eq @ x = b_eq)
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
        b_eq_vals.append(float(hours[h].demand_kwh))

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

    # Extract plan
    plan: List[HourlyPlanEntry] = []
    for h in range(H):
        g = max(0.0, float(x[idx_g(h)]))
        s = max(0.0, float(x[idx_s(h)]))
        c = max(0.0, float(x[idx_c(h)]))
        d = max(0.0, float(x[idx_d(h)]))
        E_after = max(0.0, float(x[idx_E(h)]))

        # Determine action
        if c > TOL and d > TOL:
            # LP returned both — pick the larger as primary action
            if c >= d:
                c = c - d
                d = 0.0
            else:
                d = d - c
                c = 0.0
        if c > TOL:
            action = "charge"
            battery_kwh = c
        elif d > TOL:
            action = "discharge"
            battery_kwh = d
        else:
            action = "idle"
            battery_kwh = 0.0

        plan.append(HourlyPlanEntry(
            hour=h,
            grid_kwh=round(g, 4),
            solar_used_kwh=round(s, 4),
            battery_action=action,
            battery_kwh=round(battery_kwh, 4),
            battery_energy_after_kwh=round(E_after, 4),
        ))

    return plan, True, "ok"


def optimize(req: OptimizeRequest, interpretations: List[DirectiveInterpretation]) -> OptimizeResponse:
    """Build a 24-hour schedule honoring all directives via LP."""
    reductions, min_reserve, no_charge, no_discharge, max_grid = _build_directive_maps(interpretations)
    eff_solar = _effective_solar(req.hours, reductions)

    plan, success, msg = _solve_lp(
        req.hours, req.battery, eff_solar, min_reserve, no_charge, no_discharge, max_grid,
    )

    if not success:
        # Fall back: empty plan with safe defaults
        plan = []
        for h in range(24):
            hour = req.hours[h]
            plan.append(HourlyPlanEntry(
                hour=h,
                grid_kwh=hour.demand_kwh,
                solar_used_kwh=0.0,
                battery_action="idle",
                battery_kwh=0.0,
                battery_energy_after_kwh=req.battery.initial_energy_kwh,
            ))

    # Compute totals
    total_grid = sum(p.grid_kwh for p in plan)
    total_cost = sum(p.grid_kwh * req.hours[p.hour].tariff_bdt_per_kwh for p in plan)
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
