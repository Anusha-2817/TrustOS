"""Shared test setup. Run from ``backend/``:  ``../.venv/Scripts/python -m pytest tests``."""

import os
import sys
from pathlib import Path

# main.py and services/payment_engine.py build OpenAI clients at import time. Force a dummy key so
# the import works without a real one and nothing in the test run can reach the real API; the only
# LLM call on a tested route (call_llm in /evaluate-product) is replaced by ``fake_llm`` below.
os.environ["OPENAI_API_KEY"] = "sk-test-not-a-real-key"
# The default suite is hermetic: persistence stays OFF, so it can never touch a developer's real database.
# Tests that need Postgres get their own scratch one (tests/test_db_*.py, see conftest_db.py).
os.environ.pop("DATABASE_URL", None)
# Rate limits are OFF for the suite: many tests hit the same routes from the same client address, and the
# golden replays alone would trip /evaluate-product's 10/minute. tests/test_rate_limit.py turns them back on.
os.environ["RATE_LIMIT_ENABLED"] = "false"

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pg_fixtures import api, key, pg, pg_url, v1  # noqa: E402,F401  (fixtures for the database tests)

# Deterministic stand-in for the OpenAI call, keyed by product_name so the demo payloads exercise
# 0-3 signals and a spread of confidences. Unknown names get the real function's error fallback.
# Like the real call_llm, every output says whether it is the error fallback (``is_fallback``).
_LLM_OUTPUTS = {
    "Ergonomic desk lamp": {"signals": [], "risk_modifier": -5, "confidence": 0.8},
    "Wireless mechanical keyboard": {"signals": ["packaging complaints"], "risk_modifier": 5, "confidence": 0.6},
    "Imported camera lens kit": {
        "signals": ["non-delivery reports", "wrong item reports", "sparse reviews"],
        "risk_modifier": 20,
        "confidence": 0.9,
    },
    "Phone case bundle": {"signals": ["new listing", "no verified reviews"], "risk_modifier": 10, "confidence": 0.7},
    "Professional workstation laptop": {"signals": [], "risk_modifier": -10, "confidence": 0.95},
    "Cotton tote bag": {"signals": [], "risk_modifier": 0, "confidence": 0.2},
    # A GENUINE answer whose values equal the error fallback's (no signals, modifier 0, confidence 0.5):
    # the audit log must not confuse the two.
    "Genuinely neutral item": {"signals": [], "risk_modifier": 0, "confidence": 0.5},
}
_LLM_FALLBACK = {"signals": [], "risk_modifier": 0, "confidence": 0.5, "is_fallback": True}


def fake_llm(data):
    out = _LLM_OUTPUTS.get(data.get("product_name"))
    if out is None:
        return dict(_LLM_FALLBACK)
    return {**out, "is_fallback": False}


@pytest.fixture(autouse=True)
def _fresh_auth_and_limits():
    """No test inherits another's verified-key cache or rate-limit counters (both are process-global)."""
    from services import auth, rate_limit

    auth.clear_cache()
    rate_limit.reset()
    yield
    auth.clear_cache()
    rate_limit.reset()


@pytest.fixture
def client(monkeypatch):
    import main

    monkeypatch.setattr(main, "call_llm", fake_llm)
    return TestClient(main.app)
