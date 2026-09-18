# GridWise — Collaborator Log

> Live change log for the team.
> Auto-refresh: `bash scripts/refresh_log.sh`
> Source of truth: `git log --name-only` over the last 50 commits.

---

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
| Backup LLM | Gemini `gemini-flash-lite-latest` (not currently used) |
| Framework | FastAPI |
| Optimizer | scipy.optimize.linprog (LP-optimal, matches reference) |
| Solver variables | grid_kwh[h], solar_used[h], charge[h], discharge[h], E[h] |
| Test results | 10/10 sample cases pass (interpretation + end-to-end) |
| Deploy target | TBD — Docker builds clean, needs public URL |
| Time budget | 4 hours (7 PM – 11 PM) |

## Current Status (~8:17 PM)

**Done:**
- ✅ `/health` endpoint live
- ✅ `/optimize-energy` end-to-end (LLM interp + LP solver)
- ✅ LLM interpretation 10/10 on public samples
- ✅ Optimizer matches reference optimal costs on 10/10 samples
- ✅ Dockerfile builds, container runs (with numpy/scipy deps)

**TODO before submission:**
- ⏳ Deploy to public URL (Render/ngrok)
- ⏳ Smoke test deployed endpoint
- ⏳ 3-minute video (tie-break only, lower priority)

