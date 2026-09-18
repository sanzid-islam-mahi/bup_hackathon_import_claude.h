"""
GridWise — BUP CSE Fest 2026 Hackathon Preliminary
LLM-Assisted Campus Energy Optimization API.

Endpoints:
  GET  /health          → readiness probe
  POST /optimize-energy → interpret operator notes + return 24h schedule
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from app.schemas import OptimizeRequest, OptimizeResponse
from app.interpreter import interpret_notes
from app.optimizer import optimize

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


@app.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_endpoint(req: OptimizeRequest):
    """Interpret operator notes + return 24-hour schedule."""
    try:
        interpretations = interpret_notes(req)
        result = optimize(req, interpretations)
        return result
    except Exception as e:
        # Don't leak internals; log and return 500 with safe message
        raise HTTPException(status_code=500, detail=f"optimization failed: {type(e).__name__}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
