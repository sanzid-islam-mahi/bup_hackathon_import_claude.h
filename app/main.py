"""
GridWise — BUP CSE Fest 2026 Hackathon Preliminary
LLM-Assisted Campus Energy Optimization API.

Endpoints:
  GET  /health          → readiness probe
  POST /optimize-energy → interpret operator notes + return 24h schedule
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import OptimizeRequest, OptimizeResponse
from app.interpreter import interpret_notes
from app.optimizer import optimize

load_dotenv()

logger = logging.getLogger("gridwise")

app = FastAPI(
    title="GridWise",
    description="LLM-assisted campus energy optimization for BUP CSE Fest 2026",
    version="0.1.0",
)


@app.get("/health")
def health():
    """Readiness probe. Must return {"status": "ok"} for judge harness."""
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return HTTP 400 (per problem statement) for malformed JSON / validation errors."""
    # Do not leak internals; provide a generic message and request id.
    return JSONResponse(
        status_code=400,
        content={"detail": "Malformed request body"},
    )


@app.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_endpoint(req: OptimizeRequest):
    """Interpret operator notes + return 24-hour schedule."""
    try:
        interpretations = interpret_notes(req)
        result = optimize(req, interpretations)
        return result
    except Exception as e:
        # Log internally, return a sanitized message so we don't leak
        # internal class names / stack traces to callers.
        logger.exception("optimization failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Internal optimization error")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)