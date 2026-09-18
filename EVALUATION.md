# GridWise — Comprehensive Codebase Evaluation & Audit Report

**Event:** BUP CSE Fest 2026 Hackathon · Online Preliminary Round  
**Project:** GridWise (Smart Campus Energy Optimization API)  
**Date & Time:** September 18, 2026 · 20:15 UTC+6  
**Document Scope:** Detailed audit of schemas, LLM interpretation, guardrails, API contract, and the HiGHS Linear Programming (LP) optimizer.

---

## Executive Summary

The GridWise solution has a solid architectural core:
1. **Pydantic schemas** enforcing strict hourly ranges, types, and directive invariants.
2. **Groq-driven LLM extraction (`gpt-oss-120b`)** with low temperature (0.1) passing 10/10 public test cases in ~1.5s per request.
3. **Deterministic guardrails** validating numbers, arrays, and formatting before solver entry.
4. **HiGHS LP formulation (`scipy.optimize.linprog`)** providing globally optimal cost in milliseconds.

However, critical edge-case bugs and resilience gaps were identified across the pipeline. If unpatched, these vulnerabilities could cause catastrophic point losses on hidden evaluation cases (e.g., zero-grid blackout directives, solver fallbacks, rate limits, or rounding drift).

---

## Part 1: Audit of Schemas, LLM Interpreter, Guardrails & API Contract

### 1.1 `app/schemas.py`

* **🟡 Issue 1 — Dead Union Code / Raw Dict `structured_adjustment` (Line 158)**
  * **Observation:** `DirectiveInterpretation.structured_adjustment` is typed as `Optional[dict] = None`. Five specialized Pydantic models (`SolarReduction`, `MinimumBatteryReserve`, `NoChargeWindow`, `NoDischargeWindow`, `MaxGridWindow`) and the `StructuredAdjustment` union were defined but never used for runtime model validation.
  * **Impact:** Low functional risk since `interpreter.py` manually validates shapes, but creates misleading type annotations.
  * **Fix:** Keep models or wire them cleanly into the validation pipeline.

* **🟡 Issue 2 — `hours_asc` Accepts Empty Lists (Lines 82–87, repeated across directive models)**
  * **Observation:** The validation check `sorted(set(v)) != v` passes when `v = []` because `sorted(set([])) == []`.
  * **Impact:** Low because `interpreter.py` checks `if not h: return None`, but direct model usage could permit empty hour lists.
  * **Fix:** Add `min_length=1` to the `hours` field: `Field(min_length=1)`.

* **✅ Verified Correct:**
  * `check_applies`: Strict enforcement that `no_op` has `applies=False` and `structured_adjustment=None`, while all active directives require `applies=True` and non-null adjustment.
  * `check_idle_zero`: Forces `battery_kwh == 0` when `battery_action == "idle"`.
  * `plan_24_unique` and `interpretations_in_order`: Guarantees exactly 24 unique hours (0..23) and strictly ordered `note_index` (0..N-1).

---

### 1.2 `app/interpreter.py` & Guardrails

* **🔴 Issue 3 (CRITICAL) — `max_grid_window` Rejects Zero Grid Cap (Line 208)**
  * **Observation:** Guardrail checks:
    ```python
    if cap <= 0:
        return None
    ```
  * **Canonical Spec:** Problem Statement Section 8: *"Grid cap max_grid_kwh must be finite and non-negative"* ($\ge 0$).
  * **Impact:** Any hidden scenario specifying an absolute grid blackout / zero feeder import during a time window (e.g., "no power purchase from the grid between 6 PM and 8 PM") is rejected and converted to `no_op`. This results in zero points for directive interpretation and downstream constraint application on that case.
  * **Fix:** Change `if cap <= 0:` to `if cap < 0:`.

* **🔴 Issue 4 (CRITICAL) — System Prompt Instructs LLM that `max_grid_kwh must be > 0` (Line 92)**
  * **Observation:** The prompt tells the LLM: `- max_grid_kwh must be > 0`.
  * **Impact:** Compounds Issue 3. The LLM may hallucinate a non-zero value or refuse extraction for zero-grid constraints.
  * **Fix:** Update prompt to: `- max_grid_kwh must be >= 0`.

* **🟡 Issue 5 — Duplicate Hours Cause Immediate Rejection (Lines 169–170)**
  * **Observation:**
    ```python
    if len(set(hs)) != len(hs):
        return None
    ```
  * **Impact:** If the LLM repeats an hour (e.g. `[13, 13, 14]`), the entire directive is discarded. Guardrails should sanitize and repair LLM output when deterministic.
  * **Fix:** Automatically deduplicate and sort: `hs = sorted(list(set(hs)))`.

* **🟡 Issue 6 — Missing LLM Failover to Gemini (Lines 234–241)**
  * **Observation:** Only `groq_chat` is called. If Groq encounters HTTP 429 (rate limit) or transient downtime, the code immediately falls back to `no_op` for all notes without trying Gemini.
  * **Impact:** Complete failure on repeated judging stress tests.
  * **Fix:** Add a try/except failover to `app/llm_gemini.py` before returning fallback.

* **🟡 Issue 7 — Non-Greedy Regex Fragility in Markdown JSON Extraction (Line 125)**
  * **Observation:** `re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)` uses non-greedy matching `.*?`, which can terminate prematurely on nested closing braces inside JSON objects.
  * **Impact:** Fallback greedy regex on Line 136 catches most cases, but early failure wastes time.
  * **Fix:** Use greedy pattern `r"```(?:json)?\s*(\{.*\})\s*```"`.

* **🟡 Issue 8 — Ambiguous "Through" Semantics in Prompt (Line 65)**
  * **Observation:** Prompt states `- "hours 13 through 15" → [13, 14]`.
  * **Impact:** In standard English, "through" is inclusive of both boundaries (13, 14, 15), unlike "from X to Y" which is end-exclusive.
  * **Fix:** Clarify prompt: `"hours 13 through 15" → [13, 14, 15] (inclusive)`.

---

### 1.3 `app/llm.py` & `app/llm_gemini.py`

* **🟡 Issue 9 — Dead Agricultural Boilerplate (Lines 74–119 in `app/llm.py`)**
  * **Observation:** Unused helper functions (`extract_intent`, `recommend_treatment`) remaining from the hackathon starter template.
  * **Fix:** Remove dead code to keep the repository clean for judge inspection.

---

### 1.4 `app/main.py` & API Contract

* **🟡 Issue 10 — Error Detail Leaks Internal Class Name (Line 41)**
  * **Observation:** `detail=f"optimization failed: {type(e).__name__}"`.
  * **Canonical Spec:** Section 6.1: *"Controlled internal error. Do not expose secrets or raw stack traces."*
  * **Fix:** Replace with generic message: `detail="Internal optimization error"`.

* **🟡 Issue 11 — HTTP 422 vs 400 for Malformed Requests**
  * **Observation:** FastAPI returns HTTP 422 for Pydantic validation errors by default. The problem statement lists HTTP 400 for malformed/invalid JSON requests.
  * **Fix:** Add a custom `RequestValidationError` exception handler returning status code 400.

---

## Part 2: Audit of `app/optimizer.py` (HiGHS Linear Programming Solver)

### 2.1 Formulation Overview
* **Variables:** 120 continuous decision variables across 24 hours:
  * $g_h \ge 0$: Grid electricity import (kWh)
  * $s_h \ge 0$: Usable solar consumed (kWh)
  * $c_h \ge 0$: Battery charge amount (kWh)
  * $d_h \ge 0$: Battery discharge amount (kWh)
  * $E_h \ge 0$: Battery state of charge after hour $h$ (kWh)
* **Objective:** Minimize $\sum_{h=0}^{23} g_h \cdot \text{tariff}_h$
* **Constraints:**
  * Energy balance: $g_h + s_h + d_h - c_h = \text{demand}_h$
  * Battery continuity: $E_h - E_{h-1} - c_h + d_h = 0$ (with $E_{-1} = \text{initial\_energy}$)
  * Neutrality: $E_{23} = \text{initial\_energy}$
  * Bounds: active reserves $\le E_h \le \text{capacity}$, rate limits on $c_h, d_h$, solar cap $s_h \le \text{effective\_solar}_h$, grid caps $g_h \le \text{max\_grid}_h$.

---

### 2.2 Optimizer Vulnerabilities & Edge Cases

* **🔴 Issue 12 (CRITICAL) — Fallback Plan Wastes Solar & Breaks Grid Caps (Lines 229–241)**
  * **Observation:** If LP solving ever fails, the fallback builds an idle schedule setting `grid = demand` and `solar_used_kwh = 0.0`.
  * **Impact:** 
    1. If a `max_grid_window` directive exists, setting `grid = demand` directly violates the hard cap.
    2. Zero solar usage results in an exorbitant total cost, dropping the optimization score to near zero.
  * **Fix:** In fallback, utilize available solar (`solar_used = min(eff_solar[h], demand)`), compute `grid = demand - solar_used`, and attempt battery discharge to honor any grid cap.

* **🟡 Issue 13 — Rounding Drift in Battery Energy State (Lines 210–214)**
  * **Observation:** `grid_kwh`, `solar_used_kwh`, `battery_kwh`, and `battery_energy_after_kwh` are all independently rounded to 4 decimal places directly from raw LP floating point values.
  * **Impact:** The judge independently replays:
    $$E_h = E_{h-1} \pm \text{battery\_kwh}_h$$
    Cumulative rounding differences over 24 transitions can cause the reported `battery_energy_after_kwh` to diverge from the judge's recalculated step-by-step value by more than tolerance.
  * **Fix:** After rounding `c` and `d`, sequentially recompute `battery_energy_after_kwh` from `initial_energy` so the reported state transitions match step-by-step arithmetic exactly.

* **🟡 Issue 14 — Assumption of Sorted Input Lists (Lines 44–45, 103, 117, 245)**
  * **Observation:** Code accesses `req.hours[h]` by loop index `h` instead of matching `hour.hour == h`.
  * **Impact:** If an input scenario supplies hours in non-ascending order (e.g. `[23, 0, 1, ...]`), tariff, solar, and demand values map to the wrong time slots.
  * **Fix:** Build explicit lookups indexed by hour:
    ```python
    demand = {h.hour: h.demand_kwh for h in req.hours}
    solar = {h.hour: h.solar_kwh * reductions.get(h.hour, 1.0) for h in req.hours}
    tariff = {h.hour: h.tariff_bdt_per_kwh for h in req.hours}
    ```

* **🟡 Issue 15 — Overlapping `max_grid_window` Directives (Line 72)**
  * **Observation:**
    ```python
    elif d.directive_type == "max_grid_window":
        for h in hs:
            max_grid[h] = float(adj["max_grid_kwh"])
    ```
  * **Impact:** If two directives specify grid caps for the same hour, the last one overwrites the former rather than choosing the stricter (minimum) bound.
  * **Fix:** `max_grid[h] = min(max_grid.get(h, float("inf")), float(adj["max_grid_kwh"]))`.

* **✅ Verified Correct — Simultaneous Charge & Discharge Netting (Lines 190–197)**
  * The netting logic `c_net = c - d` preserves energy balance equality ($g + s + d = \text{demand} + c \iff g + s - \text{demand} = c - d = c_{\text{net}} - d_{\text{net}}$) and ensures `battery_action` satisfies the single-action enum requirement.

---

## Part 3: Complete Action Plan & Priority Matrix

| Priority | Component | Issue | Corrective Action |
| :---: | :--- | :--- | :--- |
| 🔴 **P1** | `interpreter.py:208` | `max_grid_kwh = 0` rejected | Change `cap <= 0` to `cap < 0`. |
| 🔴 **P1** | `interpreter.py:92` | Prompt says `max_grid_kwh > 0` | Change to `max_grid_kwh >= 0`. |
| 🔴 **P1** | `optimizer.py:229` | Fallback plan breaks grid caps & solar | Use available solar and enforce grid limits in fallback. |
| 🟡 **P2** | `interpreter.py:234` | No LLM failover on Groq rate limits | Add automatic fallback to `app/llm_gemini.py`. |
| 🟡 **P2** | `optimizer.py:210` | Battery transition rounding accumulation | Recompute `E_after` sequentially using rounded action kWh. |
| 🟡 **P2** | `optimizer.py:44` | List order dependency for hourly data | Use dictionary lookups keyed by `h.hour`. |
| 🟡 **P2** | `interpreter.py:169` | Rejection of duplicate hours | Deduplicate with `sorted(set(hs))`. |
| 🟡 **P2** | `optimizer.py:72` | Overlapping `max_grid_window` | Use `min(existing, new)` for caps. |
| 🟡 **P3** | `main.py:41` | Exception type leaking | Return sanitized `detail="Internal optimization error"`. |
| 🟡 **P3** | `main.py` | HTTP 422 vs 400 | Add exception handler for `RequestValidationError` -> 400. |
| 🟡 **P3** | `llm.py:74` | Dead agricultural helper functions | Remove unused boilerplate. |

---

*Report prepared for team implementation and validation before the preliminary round submission deadline.*
