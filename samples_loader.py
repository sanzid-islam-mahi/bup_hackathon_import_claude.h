"""
Portable locator for the organizer-provided samples.json, used by every
test/smoke script. Previously hardcoded to one teammate's home directory
(/home/sanzid/...), which meant nobody else — including judges following
the README's reproduction steps — could run these tests.

Resolution order: SAMPLES_JSON_PATH env var -> repo root -> current directory.
"""
import json
import os
from pathlib import Path


def samples_path() -> Path:
    env = os.getenv("SAMPLES_JSON_PATH")
    if env:
        p = Path(env)
        if p.exists():
            return p
        raise FileNotFoundError(f"SAMPLES_JSON_PATH is set but does not exist: {p}")

    repo_root = Path(__file__).parent
    for candidate in (repo_root / "samples.json", Path("samples.json")):
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "samples.json not found. Set SAMPLES_JSON_PATH to its location, or "
        "place samples.json in the repo root (see README Quick Start)."
    )


def load_samples() -> list:
    return json.loads(samples_path().read_text())["cases"]
