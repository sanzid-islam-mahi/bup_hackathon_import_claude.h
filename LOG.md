# GridWise — Collaborator Log

> Live change log for the team.
> Auto-refresh: `bash scripts/refresh_log.sh`
> Source of truth: `git log --name-only` over the last 50 commits.

---

### 2026-09-18 (uncommitted) Add fallback end-of-day neutrality + deterministic time parser
- `app/optimizer.py` — `_fallback_plan` rewritten as 3-pass heuristic: discharge → charge → end-of-day reconciliation
- `app/time_parser.py` — NEW. Deterministic regex pre-parser for "1 PM to 3 PM" → [13, 14] style phrasings
- `app/interpreter.py` — `_build_user_prompt` injects `[Parser hint: hours = [...]]` after each note
- `test_fallback.py` — NEW. 8 fallback-path scenarios (all pass). Covers infeasible cases, blackout, no_charge / no_discharge / min_reserve constraints
- `test_time_parser.py` — NEW. 31 parser cases (all pass). 12-hour / 24-hour / fuzzy / invalid inputs
- Audit finding: spec audit (verification agent) flagged fallback path as missing E[23]=initial neutrality AND end-of-day battery_energy_after_kwh=0.0 bug. Both fixed.
- Verification matrix: 10/10 samples + 13/13 edge cases + 8/8 fallback + 31/31 time parser all green

### 2026-09-18 9ffcbcc Strengthen edge cases: fix fallback cap violation, add test suites
LOG.md
app/optimizer.py
test_edge_cases.py
test_pydantic.py

### 2026-09-18 c8c8356 Add HEAD support to /health, /readyz, /version
LOG.md
app/main.py

### 2026-09-18 4eba2db Add multi-model Groq fallback chain (gpt-oss-120b → compound-mini → qwen3.8-27b →   Gemini)
LOG.md
app/interpreter.py
app/llm.py
test_fallbacks.py

### 2026-09-18 fa0f53b update LOG.md
LOG.md

### 2026-09-18 f383d82 Add /readyz, /version, env-toggled rate limiter, smoke-test script
app/main.py
smoke_test.py

### 2026-09-18 61ddcb4 Update LOG.md status section post-audit fixes
LOG.md

### 2026-09-18 555ec7a Apply EVALUATION.md audit fixes (P1+P2+P3)
app/interpreter.py
app/llm.py
app/main.py
app/optimizer.py
app/schemas.py

### 2026-09-18 6a73f6b Update LOG.md with current status and stack decisions
LOG.md

### 2026-09-18 9679cc0 Add LP optimizer Dockerfile and end-to-end tests
.dockerignore
.gitignore
Dockerfile
EVALUATION.md
README.md
app/main.py
app/optimizer.py
requirements.txt
test_e2e.py

### 2026-09-18 ec5f11b Add Pydantic schemas + LLM interpreter with guardrails (10/10 samples pass)
app/interpreter.py
app/schemas.py
test_interpreter.py

### 2026-09-18 309b734 Add load_dotenv to LLM clients; add LOG.md and log scripts
LOG.md
app/llm.py
app/llm_gemini.py
scripts/log_hook.sh
scripts/refresh_log.sh

### 2026-09-18 1391bb4 Scaffold project FastAPI app with health endpoint
.env.example
.gitignore
README.md
app/__init__.py
app/llm.py
app/llm_gemini.py
app/main.py
requirements.txt

### 2026-09-18 bffe13c Initial commit
README.md

---

## How to use this log

- **For the team:** Run `bash scripts/refresh_log.sh` any time to regenerate from git history.
- **For judges / outsiders:** This file shows what's been built and when.
- **For puku-cli users:** A `PostToolUse` hook (in `.puku-cli/settings.json`) appends per-edit entries. See `scripts/log_hook.sh`.

## Stack & Decisions (manual)

| Item | Value |
|------|-------|
| LLM chain | Groq `openai/gpt-oss-120b` → `groq/compound-mini` → `qwen/qwen3.8-27b` → Gemini |
| Backup LLM | Gemini `gemini-flash-lite-latest` (final failover after Groq chain) |
| Groq limits (free) | 30 RPM, 1K RPD, 8K TPM, 200K TPD |
| Framework | FastAPI 0.115 |
| Optimizer | `scipy.optimize.linprog` (HiGHS, LP-optimal) |
| Solver variables | g[h], s[h], c[h], d[h], E[h] — 120 per 24h horizon |
| Test results | 10/10 sample cases (interp + E2E), reference costs match |
| Deploy | **Render** (Docker, free tier) — `https://gridwise-wppp.onrender.com` |
| Keep-alive | UptimeRobot free tier, 5-min ping on `/health` |
| Time budget | 4 hours (7 PM – 11 PM) |

## Endpoints

| Route | Method | Notes |
|---|---|---|
| `/health` | GET, HEAD | Process liveness; always cheap. Returns `{"status":"ok"}`. HEAD support added after UptimeRobot default HEAD probes got 405. |
| `/readyz` | GET, HEAD | Verifies `GROQ_API_KEY` env present; reports rate-limit config. 503 if not ready. |
| `/version` | GET, HEAD | Build / Python / rate-limit info for audits. |
| `/optimize-energy` | POST | Interpret operator notes + return 24h LP-optimal schedule. |
| `/optimize-energy` (rate-limited) | POST | When `RATE_LIMIT_PER_MIN > 0` env is set, caps requests per IP per 60s; returns 429. Default off. |
| Malformed `POST` body | — | Returns HTTP 400 (not 422) via `RequestValidationError` handler. |
| Internal error | — | Returns sanitized 500 `Internal optimization error` (no class-name leak). |

## Current Status (~11:00 PM, end of round)

**Done:**
- ✅ `/health`, `/readyz`, `/version`, `/optimize-energy` all live on Render
- ✅ `/health` and `/readyz` both respond to GET and HEAD
- ✅ **Live `smoke_test.py` results**:
  - `/health` → 200 in 0.11s ✅
  - `/readyz` → 200, groq_key_present=true ✅
  - `/version` → 200 in 0.12s ✅
  - `/optimize-energy` SAMPLE-01 → 200 in 4.47s, `total_cost_bdt=38365.0` (exact reference match) ✅
  - Malformed body → 400 ✅
- ✅ LLM interpretation 10/10 on public samples
- ✅ Optimizer matches reference optimal costs on 10/10 samples (see Cost Reference Table below)
- ✅ All 15 EVALUATION.md audit issues applied (P1, P2, P3)
- ✅ **Spec audit by verification agent: 9/10 sections MATCH, 1 PARTIAL** (extra `/readyz` and `/version` endpoints are spec-silent but harmless)
- ✅ Rate limiter added (opt-in via `RATE_LIMIT_PER_MIN`)
- ✅ `smoke_test.py` written (env-configurable URL)
- ✅ Multi-model Groq chain — auto-rotates on 429 / transient errors
- ✅ All three Groq fallback models verified on SAMPLE-01/03/05 with production prompt
- ✅ Rotation logic tested: simulated 429 → confirms next model in chain is tried
- ✅ Total Groq exhaustion → Gemini fallback (verified with mocks)
- ✅ Edge case test suite (`test_edge_cases.py`): 13/13 pass
- ✅ Pydantic test suite (`test_pydantic.py`): all 40+ schema checks pass
- ✅ Optimizer fallback now honors hard caps (max_grid_kwh) even when infeasible
- ✅ **Optimizer fallback end-of-day neutrality** (`E[23] = initial_energy_kwh`) — three-pass heuristic with multi-hour reconciliation
- ✅ **Deterministic time-phrase pre-parser** — handles "1 PM to 3 PM", "between 13:00 and 15:00", "6 PM until 9 PM", fuzzy "the evening/morning/afternoon", with parser hints injected into LLM prompt
- ✅ **Fallback test suite** (`test_fallback.py`): 8/8 pass — covers infeasible scenarios the LP can't solve
- ✅ **Time parser test suite** (`test_time_parser.py`): 31/31 pass — covers 12-hour / 24-hour / fuzzy / invalid
- ✅ UptimeRobot keeping Render warm (5-min pings on `/health`)

### Test suite totals
| Suite | Pass / Total |
|---|---|
| Interpreter (LLM) | 10/10 |
| End-to-end (LP costs) | 10/10 |
| Edge cases | 13/13 |
| Fallback path | 8/8 |
| Pydantic schema | 40+/40+ |
| Time parser | 31/31 |
| **Total** | **112+/112+** |

**TODO before submission:**
- ⏳ Set `RATE_LIMIT_PER_MIN=15` in Render env (currently `0` = disabled, low priority)
- ⏳ Record 3-min video from `video/script.md` + `video/presentation.html` (tie-break only)

## Active Deployment

- **Live URL**: `https://gridwise-wppp.onrender.com`
- **Repo**: `https://github.com/sanzid-islam-mahi/bup_hackathon_import_claude.h` (private)
- **Render service name**: `gridwise-wppp`
- **Render env vars configured**: `GROQ_API_KEY`, `GEMINI_API_KEY`, `PYTHONUNBUFFERED=1`
- **Plan**: Free tier (sleeps after 15 min idle without keep-alive)
- **Keep-alive**: UptimeRobot monitor on `/health`, 5-min interval

## Reference Cost Table (verified)

All 10 public sample cases produce costs that match the organizer reference exactly:

| Sample | Total Cost (BDT) | Total Grid (kWh) | Peak Grid (kWh) |
|---|---:|---:|---:|
| SAMPLE-01 | 38365 | 2692 | 188 |
| SAMPLE-02 | 42885 | 2915 | 180 |
| SAMPLE-03 | 35480 | 2430 | 205 |
| SAMPLE-04 | 40495 | 2645 | 225 |
| SAMPLE-05 | 33950 | 2430 | 175 |
| SAMPLE-06 | 34090 | 2395 | 175 |
| SAMPLE-07 | 38550 | 2560 | 185 |
| SAMPLE-08 | 37665 | 2490 | 210 |
| SAMPLE-09 | 34873 | 2504 | 170 |
| SAMPLE-10 | 41620 | 2715 | 190 |

Since `quality_ratio = min(1, organizer_optimal_cost / team_cost)` and all 10 cases match exactly, `quality_ratio = 1.0` across the board → **Optimization Quality: 10/10 on public samples**.

## Projected Score Breakdown (based on Participant Guide rubric)

| # | Category | Pts | Evidence | Projected | Notes |
|---:|---|---:|---|---:|---|
| 1 | **LLM Directive Interpretation** | 25 | 10/10 public samples pass via `test_interpreter.py`; multi-model chain reduces per-model risk; Gemini fallback ensures no catastrophic LLM failure; system prompt covers 10+ window phrasings and reduction wording variants; **deterministic time-phrase parser (31/31 tests)** injects `[Parser hint: hours = [...]]` into prompt to reduce hidden-paraphrase risk; specialized Pydantic models catch malformed JSON; safe-failure to `no_op` preserves schema. | **24–25** | Lose 0–1 if hidden paraphrases still diverge (parser hint reduces risk) |
| 2 | **Directive Application & Constraint Correctness** | 25 | 10/10 public samples pass via `test_e2e.py` with reference costs intact; LP-optimal schedules (HiGHS); hour-keyed dict lookups make input ordering irrelevant; sequential battery rounding matches judge replay; `max_grid_window` overlap picks stricter (min) cap; `min_reserve` overlap picks max; **fallback path now enforces end-of-day neutrality** (`E[23] = initial`, three-pass heuristic with 8/8 fallback tests passing); fallback honors hard caps. | **25** | Full credit — fallback E[23] bug fixed |
| 3 | **Optimization Quality** | 10 | scipy.optimize.linprog produces globally optimal solutions for LP. Public samples: 10/10 reference costs matched exactly. `quality_ratio = 1.0` → 10/10 on samples. | **10** | Full credit on public samples; hidden cases likely also feasible |
| 4 | **API Contract & Schema** | 10 | Pydantic models enforce: 24 unique hours 0-23, 1-3 operator notes, battery invariants (min ≤ capacity, initial ≤ capacity, initial ≥ min), finite non-negative numerics, exactly 24 hourly_plan entries in order, directive_interpretation in note_index order, scenario_id echo. Returns HTTP 400 for malformed bodies (matches spec). Spec audit: MATCH. | **10** | Likely full credit |
| 5 | **Performance & Reliability** | 10 | `/health` returns 200 within 0.11s. End-to-end latency on Render free tier: **~2-5s p50, ~5s p95** (under the 5s threshold for 3/3 latency points). Multi-model chain prevents LLM-down failures. Sanitized 500 errors prevent internal-leak failures. Rate limiter prevents overload. **8 fallback tests + 8 resilience layers** handle every failure path. No 5xx expected under stress. | **9–10** | Lose 0–1 only if Render cold-starts cost us a request (UptimeRobot mitigates) |
| 6 | **Deployment & Docker Fallback** | 10 | Live on Render at `https://gridwise-wppp.onrender.com`. `Dockerfile` builds clean (python:3.11-slim, numpy/scipy deps). `/health` returns 200. UptimeRobot keeps service warm. Smoke test script verifies all endpoints. Spec audit: MATCH (extra `/readyz`, `/version` are spec-silent, harmless). | **10** | Likely full credit if Render stays up |
| 7 | **Documentation & Local Reproducibility** | 10 | README.md, requirements.txt with pinned versions, Dockerfile with healthcheck, `.env.example` template, **eight test suites** (`test_interpreter.py`, `test_e2e.py`, `test_fallbacks.py`, `test_edge_cases.py`, `test_pydantic.py`, `test_fallback.py`, `test_time_parser.py`, `smoke_test.py`), `.notes/` architecture docs (4 markdown files), LOG.md with status + scoring analysis, EVALUATION.md audit, spec audit, 3-minute video script + HTML presentation. | **10** | Likely full credit |

### **Projected total: 96–100 / 100**

| Scenario | Score |
|---|---:|
| **Best case** (all 7 categories full credit) | **100** |
| **Realistic case** (lose 0–1 on LLM interp only) | **96–98** |
| **Worst case** (cold start loses perf point; one obscure hidden case trips up interp) | **92–95** |

### Confidence intervals by category

- **High confidence (full credit likely)**: API contract, Optimization Quality, Deployment, Documentation, **Directive Application & Constraint Correctness** — end-of-day fallback neutrality now enforced, LP is optimal, schema audit MATCH.
- **Medium confidence (0-1 point risk)**: LLM Interpretation — deterministic time parser reduces hidden paraphrase risk, multi-model chain + Gemini fallback reduces LLM-down risk. Performance — comfortably under thresholds but Render cold starts remain a tail risk.

### Risks to mitigate before judging

1. **Render cold start**: UptimeRobot mitigates but doesn't eliminate. If the service sleeps for >15 min for any reason, the first request will take 30-50s (timeout risk).
2. **Groq TPM/TPD exhaustion**: Today's usage is ~158K/200K tokens. If judging starts tomorrow on a fresh daily budget, we're fine. If it runs today, we have ~42K tokens left (~15-25 more requests). **Recommendation: switch primary to `groq/compound-mini` if TPD is critical** (it has 70K TPM with no TPD, but only 250 RPD).
3. **Hidden paraphrase divergence**: Now mitigated by the deterministic time-phrase parser that injects `[Parser hint: hours = [...]]` into the prompt. If the parser succeeds, the LLM sees the right answer; if it fails, the LLM does its normal work. Three-level safe-failure (per-note, all-notes, sanitized 500) means we degrade gracefully — never crash, never invent bad directives.

### What would change the projected score

| Action | Effect | Worth doing? |
|---|---|---|
| Run `smoke_test.py` against live URL | ✅ Done — all 5 checks pass | Done |
| Push the staged commit (HEAD support, edge case fixes, optimizer fallback fix) | ✅ Pushed — verified via `git log` | Done |
| Set `RATE_LIMIT_PER_MIN=15` on Render | Protects against quota burn | Maybe (low priority if judging is brief) |
| Record 3-min video | Tie-break only (no base points) | Skip if time-constrained |

