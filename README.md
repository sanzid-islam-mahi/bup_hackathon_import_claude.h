# GridWise

LLM-Assisted Campus Energy Optimization API for **BUP CSE Fest 2026 Hackathon Preliminary**.

Receives a 24-hour energy scenario plus 1-3 natural-language operator notes, interprets the notes into structured directives using a language model, optimizes the energy schedule, and returns both the interpretation and the 24-hour plan.

## Endpoints

- `GET  /health` → `{"status": "ok"}`
- `POST /optimize-energy` → interpretation + 24-hour schedule

## Quick Start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # add GROQ_API_KEY
python -m app.main
```

Server runs at `http://localhost:8000`.

## Stack

- Python 3.11+
- FastAPI
- Groq LLM (openai/gpt-oss-120b) for operator-note interpretation
- (Optimizer TBD — scipy.linprog or greedy)

## Repository Visibility

Private during the event, made public after the submission deadline per rulebook.
