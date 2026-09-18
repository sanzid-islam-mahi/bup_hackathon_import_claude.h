# GridWise

LLM-Assisted Campus Energy Optimization API for **BUP CSE Fest 2026 Hackathon Preliminary**.

Receives a 24-hour campus energy scenario plus 1-3 natural-language operator notes, interprets the notes into structured directives using a language model, optimizes the energy schedule with linear programming, and returns both the interpretation and the 24-hour plan.

## Endpoints

- `GET  /health` → `{"status": "ok"}`
- `POST /optimize-energy` → interpretation + 24-hour schedule

## Quick Start (Local)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # add GROQ_API_KEY
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

The container exposes port 8000 and uses the same `GROQ_API_KEY` from your `.env` file.

## Stack

- **Python 3.11+**
- **FastAPI** + Uvicorn — HTTP service
- **Groq LLM** (`openai/gpt-oss-120b`) — operator-note interpretation
- **scipy.optimize.linprog** — 24-hour energy schedule optimization
- **Pydantic v2** — request/response validation

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GROQ_API_KEY` | Yes | LLM provider for operator-note interpretation |
| `GEMINI_API_KEY` | No | Backup LLM (not currently used) |
| `PORT` | No | Default `8000` |
| `HOST` | No | Default `0.0.0.0` |

No secrets are baked into the Docker image. Pass them at runtime via `--env-file` or `-e`.

## How It Works

```
POST /optimize-energy
        │
        ▼
  OptimizeRequest (Pydantic validates 24-hour shape, battery spec, 1-3 notes)
        │
        ▼
  interpret_notes() ──→ Groq LLM call (~0.6s)
        │              ↓
        │              Strict JSON parsing + 6 guardrails
        │              (hours 0-23, factor ∈ [0,1], reserve ≤ capacity, etc.)
        ▼
  optimize() ──→ scipy.optimize.linprog (linear program)
        │        Variables: grid_kwh[h], solar_used[h], charge[h], discharge[h], E[h]
        │        Objective: minimize Σ grid_kwh × tariff
        │        Constraints: energy balance, battery bounds, directives, end-of-day neutrality
        ▼
  OptimizeResponse (validated, totals recalculated)
```

## Verification

The 10 public sample cases from `samples.json` (provided by organizers) all pass:

```bash
venv/bin/python test_interpreter.py    # LLM interpretation: 10/10
venv/bin/python test_e2e.py            # End-to-end pipeline: 10/10
```

Optimizer costs match the reference optimal values (e.g., `SAMPLE-01` = **38365 BDT**).

## Supported Directives

The LLM maps operator notes to one of six directive types:

| Type | Example note | Effect |
|------|--------------|--------|
| `solar_reduction` | "Solar drops 80% from 1 PM to 3 PM" | Reduces usable solar in listed hours by `(1 - factor)` |
| `minimum_battery_reserve` | "Keep 100 kWh reserve 6-9 PM" | Raises battery floor in listed hours |
| `no_charge_window` | "No battery charging 2-4 PM" | Forces `battery_kwh = 0` in listed hours |
| `no_discharge_window` | "Don't discharge 6-8 PM" | Forces `battery_kwh = 0` in listed hours |
| `max_grid_window` | "Grid max 150 kWh 6-9 PM" | Caps `grid_kwh` in listed hours |
| `no_op` | "Cafeteria menu changes" | Note is irrelevant |

## Project Structure

```
gridwise/
├── app/
│   ├── main.py          ← FastAPI app, /health, /optimize-energy
│   ├── schemas.py       ← Pydantic models (request/response contract)
│   ├── llm.py           ← Groq client wrapper (lazy-init)
│   ├── llm_gemini.py    ← Gemini backup
│   ├── interpreter.py   ← LLM-driven note interpretation + guardrails
│   └── optimizer.py     ← LP-based 24-hour scheduler
├── test_interpreter.py  ← 10/10 sample cases (interpretation only)
├── test_e2e.py          ← 10/10 sample cases (full pipeline)
├── Dockerfile
├── .dockerignore
├── requirements.txt
├── .env.example
└── README.md
```

## Known Limitations

- **Greedy fallback:** The LP solver always succeeds (organizers guarantee feasible scenarios), so the greedy fallback in early iterations was removed.
- **Single LLM call per request:** No retry on transient failures. If Groq is down, all notes fall back to `no_op` (safe failure).
- **LLM dependency:** Requires network access to Groq at request time. No local model fallback implemented.

## Repository Visibility

Private during the event, made public after the submission deadline per the official rulebook.

## License

MIT — open source for educational purposes.
