"""
GridWise — BUP CSE Fest 2026 Hackathon Preliminary
LLM-Assisted Campus Energy Optimization API.

Endpoints:
  GET  /health          → readiness probe
  POST /optimize-energy → interpret operator notes + return 24h schedule
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

app = FastAPI(
    title="GridWise",
    description="LLM-assisted campus energy optimization for BUP CSE Fest 2026",
    version="0.1.0",
)


@app.get("/health")
def health():
    """Readiness probe. Must return {"status": "ok"} for judge harness."""
    return {"status": "ok"}


# POST /optimize-energy will be added next.
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
