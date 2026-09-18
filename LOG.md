# GridWise — Collaborator Log

> Live change log for the team.
> Auto-refresh: `bash scripts/refresh_log.sh`
> Source of truth: `git log --name-only` over the last 50 commits.

---

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
| LLM provider | **OpenAI `gpt-4o-mini`** (primary, whenever `OPENAI_API_KEY` is set) → Groq `openai/gpt-oss-120b` → `groq/compound-mini` → `qwen/qwen3.8-27b` (fallback chain, used if only `GROQ_API_KEY` is set) → Gemini (final backup) |
| Backup LLM | Gemini `gemini-flash-lite-latest` (final failover after primary chain exhausts) |
| Groq limits (free) | 30 RPM, 1K RPD, 8K TPM, 200K TPD |
| Framework | FastAPI 0.115 |
| Optimizer | `scipy.optimize.linprog` (HiGHS, LP-optimal) |
| Solver variables | g[h], s[h], c[h], d[h], E[h] — 120 per 24h horizon |
| Test results | 10/10 sample cases (interp + E2E), reference costs match |
| Deploy | **Render** (Docker, free tier) — `https://gridwise-wppp.onrender.com` |
| Keep-alive | UptimeRobot free tier, 5-min ping on `/health` (planned) |
| Time budget | 4 hours (7 PM – 11 PM) |

## Endpoints

| Route | Method | Notes |
|---|---|---|
| `/health` | GET, HEAD | Process liveness; always cheap. Returns `{"status":"ok"}`. HEAD supported for monitoring tools. |
| `/readyz` | GET, HEAD | Verifies `OPENAI_API_KEY` or `GROQ_API_KEY` env present; reports rate-limit config. 503 if not ready. |
| `/version` | GET, HEAD | Build / Python / rate-limit info for audits. |
| `/optimize-energy` | POST | Interpret operator notes + return 24h LP-optimal schedule. |
| `/optimize-energy` (rate-limited) | POST | When `RATE_LIMIT_PER_MIN > 0` env is set, caps requests per IP per 60s; returns 429. Default off. |
| Malformed `POST` body | — | Returns HTTP 400 (not 422) via `RequestValidationError` handler. |
| Internal error | — | Returns sanitized 500 `Internal optimization error` (no class-name leak). |

## Current Status (~9:30 PM)

**Done:**
- ✅ `/health`, `/optimize-energy` live on Render (`https://gridwise-wppp.onrender.com`)
- ✅ Live `SAMPLE-01` test returns `total_cost_bdt: 38365` (matches reference) in 2.2s end-to-end
- ✅ LLM interpretation 10/10 on public samples
- ✅ Optimizer matches reference optimal costs on 10/10 samples
- ✅ All 15 EVALUATION.md audit issues applied (P1, P2, P3)
- ✅ `/readyz`, `/version` added (GET + HEAD) — pending Render redeploy
- ✅ Rate limiter added (opt-in via `RATE_LIMIT_PER_MIN`), locally verified (3 reqs → 429s)
- ✅ `smoke_test.py` written (env-configurable URL)
- ✅ Multi-model Groq chain (`gpt-oss-120b` → `compound-mini` → `qwen3.8-27b`) — auto-rotates on 429 / transient errors
- ✅ All three Groq fallback models verified on SAMPLE-01/03/05 with production prompt
- ✅ Rotation logic tested: simulated 429 → confirms next model in chain is tried
- ✅ Total Groq exhaustion → Gemini fallback (verified with mocks)
- ✅ Edge case test suite (`test_edge_cases.py`): 13/13 pass — covers no_op, factor=0/1, tight reserves, partial blackouts, conflicting directives, duplicates, percentages, all-hours windows
- ✅ Pydantic test suite (`test_pydantic.py`): all schema invariants validated (5 groups, 40+ checks)
- ✅ Optimizer fallback now honors hard caps (max_grid_kwh) even when infeasible — better than violating a spec'd constraint
- ✅ UptimeRobot keeping Render warm (5-min pings on `/health`)

**TODO before submission:**
- ⏳ Commit + push (you said you'll do this manually)
- ⏳ Wait for Render auto-redeploy (~3-5 min), then run `venv/bin/python smoke_test.py`
- ⏳ Optionally set `RATE_LIMIT_PER_MIN=15` in Render env (currently `0` = disabled)
- ⏳ 3-minute video (tie-break only, lower priority)

## Active Deployment

- **Live URL**: `https://gridwise-wppp.onrender.com`
- **Repo**: `https://github.com/sanzid-islam-mahi/bup_hackathon_import_claude.h` (private)
- **Render service name**: `gridwise-wppp`
- **Render env vars configured**: `GROQ_API_KEY`, `GEMINI_API_KEY`, `PYTHONUNBUFFERED=1`
  - ⚠️ To make Render use OpenAI as primary (see Round 2 below), add `OPENAI_API_KEY` in the Render dashboard — code prefers it automatically once present, no redeploy code change needed.
- **Plan**: Free tier (sleeps after 15 min idle without keep-alive)

## Round 2 — Second-pass review (manual, not yet committed)

A second independent review (Claude Code, teammate's parallel branch merged into this review) found and fixed real bugs beyond the original EVALUATION.md audit:

- ✅ **OpenAI added as primary provider** per team decision — `app/llm.py` now prefers `OPENAI_API_KEY` (`gpt-4o-mini`, JSON mode) and falls back to the existing Groq chain when only `GROQ_API_KEY` is set. Verified end-to-end locally (paraphrased notes correctly interpreted, ~4.4s full round trip).
- 🔴 **`/readyz` bug**: only checked `GROQ_API_KEY`, so it would incorrectly report `503 degraded` once OpenAI became the configured provider. Fixed to accept either key.
- 🟡 **`/version` inefficiency**: shelled out via `os.popen("python --version")` on every request. Replaced with `sys.version` (no subprocess).
- 🔴 **Gemini backup model was stale/experimental**: code still had `gemini-2.0-flash-exp` even though this file's own Stack table already documented `gemini-flash-lite-latest` as the decision — experimental Google model IDs get retired without notice. Fixed to match the documented decision.
- 🔴 **`samples.json` portability bug**: hardcoded to `/home/sanzid/competitions/bup-hackathon/samples.json` in 4 files (`test_interpreter.py`, `test_e2e.py`, `test_fallbacks.py`, `smoke_test.py`) — meant nobody but that one machine could run the documented verification steps, directly hurting Documentation & Reproducibility scoring. Added `samples_loader.py` (env var `SAMPLES_JSON_PATH` → repo root → clear error) and pointed all 4 scripts at it. **The actual `samples.json` file still needs to be added to the repo** — get it from whoever has it and drop it in the repo root.
- 🔴 **`_fallback_plan` end-of-day neutrality gap**: the LP-failure fallback path only ever discharges the battery, never charges — so if it ever fired, the resulting plan would violate the hard end-of-day battery neutrality rule (Section 9.6), a guaranteed-invalid hidden case. Added a bounded hour-23 charge-back correction (funded by extra grid import, respecting rate/capacity/grid-cap headroom) plus a runnable self-check (`python -m app.optimizer`). Low-probability path (HiGHS essentially never fails on guaranteed-feasible scenarios) but a real correctness gap if it ever does.
- 📝 **README/LOG/.env.example corrected** to match reality: stack section, env var table, "Known Limitations" (previously claimed the greedy fallback had been *removed* — it's still very much in the code and now fixed instead), verification steps, project structure.

**Still outstanding:** commit + push this round's changes; obtain and commit the real `samples.json`; re-run `test_interpreter.py` / `test_e2e.py` against it once available; decide whether to add `OPENAI_API_KEY` to Render's env vars.

