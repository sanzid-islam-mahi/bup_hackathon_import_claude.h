"""
GridWise — BUP CSE Fest 2026 Hackathon Preliminary
LLM-Assisted Campus Energy Optimization API.

Endpoints:
  GET  /health          → process liveness probe (always cheap)
  GET  /readyz          → readiness probe (verifies LLM API keys present)
  GET  /version         → build / version info
  POST /optimize-energy → interpret operator notes + return 24h schedule

Rate limiting (opt-in):
  Set env var RATE_LIMIT_PER_MIN to a positive integer to cap requests per
  IP per rolling 60-second window on /optimize-energy. Set to 0 or unset to
  disable (default). When triggered, returns HTTP 429 with a retry hint.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import OptimizeRequest, OptimizeResponse
from app.interpreter import interpret_notes
from app.optimizer import optimize

load_dotenv()

logger = logging.getLogger("gridwise")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

APP_VERSION = "0.1.0"

app = FastAPI(
    title="GridWise",
    description="LLM-assisted campus energy optimization for BUP CSE Fest 2026",
    version=APP_VERSION,
)


# ===================== Rate limiter =====================
# Simple in-memory sliding-window limiter, opt-in via env.
# Lock-protected dict {client_ip: deque[timestamp_seconds]}.
_RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "0") or "0")
_ip_log: Dict[str, Deque[float]] = defaultdict(deque)
_ip_log_lock = Lock()
_WINDOW_SEC = 60.0


def _check_rate_limit(client_ip: str) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    if _RATE_LIMIT_PER_MIN <= 0:
        return True
    now = time.monotonic()
    cutoff = now - _WINDOW_SEC
    with _ip_log_lock:
        bucket = _ip_log[client_ip]
        # Drop expired entries
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_PER_MIN:
            return False
        bucket.append(now)
        # Soft cap on tracked IPs to prevent memory growth
        if len(_ip_log) > 10000:
            # Drop the coldest IP entries (lazy cleanup)
            for k in list(_ip_log.keys())[:1000]:
                _ip_log.pop(k, None)
        return True


# ===================== Endpoints =====================

@app.get("/health")
@app.head("/health")
def health():
    """Process liveness probe. Must return {"status": "ok"} for judge harness.

    Supports HEAD for compatibility with monitoring tools (UptimeRobot, etc.)
    that probe via HEAD by default.
    """
    return {"status": "ok"}


@app.get("/readyz")
@app.head("/readyz")
def readyz():
    """Readiness probe — verifies env is configured correctly.

    Returns 200 only when required API keys are present (does NOT consume
    any quota). Use this in orchestrators that need to wait until the
    service is truly ready to handle requests.
    """
    groq_ok = bool(os.getenv("GROQ_API_KEY"))
    gemini_ok = bool(os.getenv("GEMINI_API_KEY"))
    rate_limit = _RATE_LIMIT_PER_MIN
    ready = groq_ok  # Groq is the primary; Gemini is a backup
    payload = {
        "status": "ready" if ready else "degraded",
        "groq_key_present": groq_ok,
        "gemini_key_present": gemini_ok,
        "rate_limit_per_min": rate_limit,
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.get("/version")
@app.head("/version")
def version():
    """Build / version info for debugging and judge audits."""
    return {
        "name": "GridWise",
        "version": APP_VERSION,
        "python": os.popen("python --version 2>&1").read().strip() or "unknown",
        "rate_limit_per_min": _RATE_LIMIT_PER_MIN,
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return HTTP 400 (per problem statement) for malformed JSON / validation errors."""
    return JSONResponse(
        status_code=400,
        content={"detail": "Malformed request body"},
    )


@app.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_endpoint(req: OptimizeRequest, request: Request):
    """Interpret operator notes + return 24-hour schedule."""
    # Rate limit (opt-in via RATE_LIMIT_PER_MIN env)
    client_ip = (request.headers.get("x-forwarded-for") or request.client.host or "unknown").split(",")[0].strip()
    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded; retry after a minute.",
        )

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
