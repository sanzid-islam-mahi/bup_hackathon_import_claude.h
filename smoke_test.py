"""
Smoke test against a live deployment.

Usage:
    GRIDWISE_URL=https://gridwise-wppp.onrender.com venv/bin/python smoke_test.py

Tests:
  1. /health       → 200 {"status":"ok"}
  2. /readyz       → 200 with groq_key_present=True
  3. /version      → 200 with version info
  4. /optimize-energy with SAMPLE-01 → 200, total_cost matches reference
  5. POST malformed body → 400
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError, URLError


URL = os.getenv("GRIDWISE_URL", "https://gridwise-wppp.onrender.com").rstrip("/")
SAMPLES_PATH = Path("/home/sanzid/competitions/bup-hackathon/samples.json")
EXPECTED_COSTS = {
    "SAMPLE-01": 38365.0,
    # Others verified separately
}


def _http(method: str, path: str, body=None, headers=None) -> tuple[int, float, str]:
    url = URL + path
    data = None
    hdr = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        hdr["Content-Type"] = "application/json"
    if headers:
        hdr.update(headers)
    req = urlreq.Request(url, data=data, method=method, headers=hdr)
    t0 = time.monotonic()
    try:
        with urlreq.urlopen(req, timeout=30) as resp:
            return resp.status, time.monotonic() - t0, resp.read().decode()
    except HTTPError as e:
        return e.code, time.monotonic() - t0, e.read().decode()


def _check(name: str, ok: bool, detail: str = ""):
    sym = "PASS" if ok else "FAIL"
    print(f"  [{sym}] {name}{(' — ' + detail) if detail else ''}")
    return ok


def main() -> int:
    print(f"Smoke testing {URL}")
    print()
    failures = 0

    # 1. /health
    print("[1] /health")
    code, dt, body = _http("GET", "/health")
    if not _check("status 200", code == 200, f"HTTP {code} in {dt:.2f}s"):
        failures += 1
    if not _check('returns {"status":"ok"}', '"status":"ok"' in body, f"body={body[:120]}"):
        failures += 1

    # 2. /readyz
    print("[2] /readyz")
    code, dt, body = _http("GET", "/readyz")
    if not _check("status 200", code == 200, f"HTTP {code} in {dt:.2f}s"):
        failures += 1
    try:
        readyz = json.loads(body)
        if not _check("groq_key_present=true", readyz.get("groq_key_present") is True,
                       f"readyz={readyz}"):
            failures += 1
    except Exception as e:
        if not _check("readyz parses as JSON", False, str(e)):
            failures += 1

    # 3. /version
    print("[3] /version")
    code, dt, body = _http("GET", "/version")
    if not _check("status 200", code == 200, f"HTTP {code} in {dt:.2f}s"):
        failures += 1
    try:
        v = json.loads(body)
        if not _check("version field present", "version" in v, f"body={body[:120]}"):
            failures += 1
    except Exception:
        if not _check("version parses as JSON", False, f"body={body[:120]}"):
            failures += 1

    # 4. /optimize-energy with SAMPLE-01
    print("[4] /optimize-energy (SAMPLE-01)")
    if not SAMPLES_PATH.exists():
        if not _check("samples.json present", False, f"missing {SAMPLES_PATH}"):
            failures += 1
    else:
        cases = json.loads(SAMPLES_PATH.read_text())["cases"]
        s1 = next(c for c in cases if c["id"] == "SAMPLE-01")
        code, dt, body = _http("POST", "/optimize-energy", body=s1["input"])
        if not _check("status 200", code == 200, f"HTTP {code} in {dt:.2f}s"):
            failures += 1
            print(f"  body: {body[:300]}")
        else:
            try:
                resp = json.loads(body)
                cost = resp.get("total_cost_bdt")
                expected = EXPECTED_COSTS.get("SAMPLE-01")
                if not _check(f"total_cost_bdt == {expected}", cost == expected,
                              f"got {cost}"):
                    failures += 1
                if not _check("hourly_plan has 24 entries",
                              len(resp.get("hourly_plan", [])) == 24,
                              f"got {len(resp.get('hourly_plan', []))}"):
                    failures += 1
                if not _check("2 directive interpretations",
                              len(resp.get("directive_interpretation", [])) == 2,
                              f"got {len(resp.get('directive_interpretation', []))}"):
                    failures += 1
            except Exception as e:
                if not _check("response parses", False, str(e)):
                    failures += 1

    # 5. Malformed body → 400
    print("[5] POST malformed body (expect HTTP 400)")
    code, dt, body = _http("POST", "/optimize-energy", body={"this": "is invalid"})
    if not _check("status 400", code == 400, f"HTTP {code} in {dt:.2f}s"):
        failures += 1

    print()
    if failures == 0:
        print("ALL CHECKS PASSED")
        return 0
    print(f"{failures} CHECK(S) FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())