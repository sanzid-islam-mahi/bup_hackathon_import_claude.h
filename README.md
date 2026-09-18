# GridWise

LLM-Assisted Campus Energy Optimization API for **BUP CSE Fest 2026 Hackathon Preliminary**.

Receives a 24-hour campus energy scenario plus 1-3 natural-language operator notes, interprets the notes into structured directives using a language model, optimizes the energy schedule with linear programming, and returns both the interpretation and the 24-hour plan.

**Live deployment:** `https://gridwise-wppp.onrender.com`

## Endpoints

- `GET  /health` → `{"status": "ok"}` — process liveness, always cheap
- `GET  /readyz` → 200 once a primary LLM provider key is configured, 503 otherwise
- `GET  /version` → build/version info for judge audits
- `POST /optimize-energy` → interpretation + 24-hour schedule (main endpoint)

## Quick Start (Local)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # add OPENAI_API_KEY (or GROQ_API_KEY — see below)
python -m app.main
```

Server runs at `http://localhost:8000`.

Test it:
```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```

## Quick Start (Docker)

```bash
docker build -t gridwise:latest .
docker run --rm -p 8000:8000 --env-file .env gridwise:latest
```

The container exposes port 8000 and reads whichever provider key is present in your `.env` file (see Environment Variables below). No secrets are baked into the image.

## Stack

- **Python 3.12** (also runs on 3.11+)
- **FastAPI** + Uvicorn — HTTP service
- **LLM provider (auto-selected):**
  - **OpenAI** (`gpt-4.1-mini` → `gpt-4o-mini` fallback) — primary, used whenever `OPENAI_API_KEY` is set. `gpt-4.1-mini` was chosen over `gpt-4o-mini` after head-to-head testing on this task showed it more accurate (e.g. `gpt-4o-mini` repeatedly confused "no grid import" with "no battery charging", and mishandled inclusive "X through Y" hour ranges) and ~40% faster.
  - **Groq** (`openai/gpt-oss-120b` → `groq/compound-mini` → `qwen/qwen3.8-27b`) — used when only `GROQ_API_KEY` is set; rotates models automatically on rate limits (429) or transient errors
  - **Gemini** (`gemini-flash-lite-latest`) — final backup if the primary chain is fully exhausted
- **scipy.optimize.linprog** (HiGHS) — 24-hour energy schedule optimization, exact LP (not a heuristic)
- **Pydantic v2** — request/response validation

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | One of these two | Primary LLM provider for operator-note interpretation |
| `GROQ_API_KEY` | One of these two | Used automatically if `OPENAI_API_KEY` is not set (free-tier, multi-model fallback chain) |
| `GEMINI_API_KEY` | No | Final backup if the primary provider's whole chain fails |
| `RATE_LIMIT_PER_MIN` | No | Positive integer to cap `/optimize-energy` requests per IP per 60s. Unset/`0` = disabled (default) |
| `SAMPLES_JSON_PATH` | No | Path to `samples.json` for the test scripts, if not placed in the repo root (see Verification) |
| `PORT` | No | Default `8000` |
| `HOST` | No | Default `0.0.0.0` |

Provider selection in `app/llm.py` is automatic: OpenAI is used if `OPENAI_API_KEY` is set, otherwise Groq if `GROQ_API_KEY` is set. No code changes needed to switch.

## How It Works

```
POST /optimize-energy
        │
        ▼
  OptimizeRequest (Pydantic validates 24-hour shape, battery spec, 1-3 notes)
        │
        ▼
  interpret_notes() ──→ LLM call (OpenAI primary, or Groq model chain, or Gemini backup)
        │              ↓
        │              Strict JSON parsing + guardrails per directive type
        │              (hours 0-23 unique ascending, factor ∈ [0,1], reserve ≤ capacity,
        │               applies/no_op semantics, unsupported types rejected)
        │              Any failure at any stage → safe no_op for that note
        ▼
  optimize() ──→ scipy.optimize.linprog (exact LP, HiGHS solver)
        │        Variables: grid_kwh[h], solar_used[h], charge[h], discharge[h], E[h]
        │        Objective: minimize Σ grid_kwh × tariff
        │        Constraints: energy balance, battery bounds/rate limits, all applied
        │        directives, end-of-day neutrality
        │        If the LP is ever infeasible: deterministic fallback plan (solar →
        │        grid → battery discharge, with a bounded hour-23 charge-back so
        │        end-of-day neutrality still holds)
        ▼
  OptimizeResponse (validated, totals recalculated from hourly_plan)
```

The LLM's output is never trusted directly — every directive it proposes passes through `app/interpreter.py`'s guardrails (type check, hour dedup/range, numeric range, capacity check) and a second Pydantic-level validation before it can affect the optimizer.

## Verification

`samples.json` (the organizer-provided public sample cases) is **not committed to this repo** — get it from the team/organizer channel and either place it at the repo root or point `SAMPLES_JSON_PATH` at it:

```bash
export SAMPLES_JSON_PATH=/path/to/samples.json   # or just: cp /path/to/samples.json .

venv/bin/python test_interpreter.py    # LLM interpretation against all sample cases
venv/bin/python test_e2e.py            # Full pipeline against all sample cases
venv/bin/python test_fallbacks.py      # Verifies each Groq fallback model individually
GRIDWISE_URL=https://gridwise-wppp.onrender.com venv/bin/python smoke_test.py  # live deployment smoke test
```

`app/optimizer.py` also has a standalone self-check that needs no API key or sample data:

```bash
venv/bin/python -m app.optimizer   # verifies the fallback plan's end-of-day neutrality fix
```

## Supported Directives

The LLM maps operator notes to one of six directive types:

| Type | Example note | Effect |
|------|--------------|--------|
| `solar_reduction` | "Solar drops 80% from 1 PM to 3 PM" | Reduces usable solar in listed hours by `(1 - factor)` |
| `minimum_battery_reserve` | "Keep 100 kWh reserve 6-9 PM" | Raises battery floor in listed hours |
| `no_charge_window` | "No battery charging 2-4 PM" | Forces `battery_kwh = 0` (charge) in listed hours |
| `no_discharge_window` | "Don't discharge 6-8 PM" | Forces `battery_kwh = 0` (discharge) in listed hours |
| `max_grid_window` | "Grid max 150 kWh 6-9 PM" | Caps `grid_kwh` in listed hours (0 = absolute blackout allowed) |
| `no_op` | "Cafeteria menu changes" | Note is irrelevant to the energy schedule |

## Project Structure

```
gridwise/
├── app/
│   ├── main.py            ← FastAPI app: /health, /readyz, /version, /optimize-energy
│   ├── schemas.py         ← Pydantic models (request/response contract)
│   ├── llm.py             ← OpenAI/Groq client wrapper, auto-selected by key, model fallback chain
│   ├── llm_gemini.py      ← Gemini final-backup client
│   ├── interpreter.py     ← LLM-driven note interpretation + guardrails
│   └── optimizer.py       ← LP-based 24-hour scheduler + deterministic fallback
├── samples_loader.py       ← Portable samples.json locator (env var or repo root)
├── test_interpreter.py     ← Sample cases (interpretation only)
├── test_e2e.py              ← Sample cases (full pipeline)
├── test_fallbacks.py        ← Verifies each Groq fallback model individually
├── smoke_test.py             ← Live-deployment smoke test
├── Dockerfile / .dockerignore
├── requirements.txt
├── .env.example
├── LOG.md                   ← Running team change log
├── EVALUATION.md             ← Dated architecture audit (issues found + fixes applied)
└── README.md
```

## Known Limitations

- **Fallback plan is a last resort, not primary logic:** the LP (HiGHS) is expected to succeed on every organizer-guaranteed-feasible scenario; the deterministic fallback in `_fallback_plan` only activates if the LP genuinely fails, and even then can only guarantee end-of-day neutrality when the residual fits within hour 23's remaining charge/grid headroom.
- **Batch LLM call:** all operator notes for a scenario are interpreted in a single LLM call (not one call per note), which is faster but means one malformed model response can affect multiple notes at once — mitigated by per-note guardrails and safe no_op fallback.
- **In-memory rate limiter:** `RATE_LIMIT_PER_MIN` tracks per-IP request counts in a single process's memory; it will not share state across multiple worker processes or instances if the deployment scales horizontally.
- **No response caching:** identical repeated requests re-invoke the LLM each time.

## Repository Visibility

Private during the event, made public after the submission deadline per the official rulebook.

## License

MIT — open source for educational purposes.
