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
| LLM | Groq `openai/gpt-oss-120b` |
| Backup LLM | Gemini `gemini-flash-lite-latest` (failover on Groq errors) |
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
| `/health` | GET | Process liveness; always cheap. Returns `{"status":"ok"}`. |
| `/readyz` | GET | Verifies `GROQ_API_KEY` env present; reports rate-limit config. 503 if not ready. |
| `/version` | GET | Build / Python / rate-limit info for audits. |
| `/optimize-energy` | POST | Interpret operator notes + return 24h LP-optimal schedule. |
| `/optimize-energy` (rate-limited) | POST | When `RATE_LIMIT_PER_MIN > 0` env is set, caps requests per IP per 60s; returns 429. Default off. |
| Malformed `POST` body | — | Returns HTTP 400 (not 422) via `RequestValidationError` handler. |
| Internal error | — | Returns sanitized 500 `Internal optimization error` (no class-name leak). |

## Current Status (~8:46 PM)

**Done:**
- ✅ `/health`, `/optimize-energy` live on Render (`https://gridwise-wppp.onrender.com`)
- ✅ Live `SAMPLE-01` test returns `total_cost_bdt: 38365` (matches reference) in 2.2s end-to-end
- ✅ LLM interpretation 10/10 on public samples
- ✅ Optimizer matches reference optimal costs on 10/10 samples
- ✅ All 15 EVALUATION.md audit issues applied (P1, P2, P3)
- ✅ `/readyz`, `/version` added (verified locally — pending Render redeploy)
- ✅ Rate limiter added (opt-in via `RATE_LIMIT_PER_MIN`), locally verified (3 reqs → 429s)
- ✅ `smoke_test.py` written (env-configurable URL, verifies health + readyz + version + optimize + 400)

**TODO before submission:**
- ⏳ Commit + push (you said you'll do this manually)
- ⏳ Wait for Render auto-redeploy (~3-5 min), then run `venv/bin/python smoke_test.py`
- ⏳ Set up UptimeRobot monitor on `/health` (5-min interval) to dodge Render free-tier cold starts
- ⏳ 3-minute video (tie-break only, lower priority)

## Active Deployment

- **Live URL**: `https://gridwise-wppp.onrender.com`
- **Repo**: `https://github.com/sanzid-islam-mahi/bup_hackathon_import_claude.h` (private)
- **Render service name**: `gridwise-wppp`
- **Render env vars configured**: `GROQ_API_KEY`, `GEMINI_API_KEY`, `PYTHONUNBUFFERED=1`
- **Plan**: Free tier (sleeps after 15 min idle without keep-alive)

