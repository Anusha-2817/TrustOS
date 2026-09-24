"""Shared test setup. Run from ``backend/``:  ``../.venv/Scripts/python -m pytest tests``."""

import os
import sys
from pathlib import Path

# main.py and services/payment_engine.py build OpenAI clients at import time. Force a dummy key so
# the import works without a real one and nothing in the test run can reach the real API; the only
# LLM call on a tested route (call_llm in /evaluate-product) is replaced by ``fake_llm`` below.
os.environ["OPENAI_API_KEY"] = "sk-test-not-a-real-key"

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Deterministic stand-in for the OpenAI call, keyed by product_name so the demo payloads exercise
# 0-3 signals and a spread of confidences. Unknown names get the real function's error fallback.
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
}
_LLM_FALLBACK = {"signals": [], "risk_modifier": 0, "confidence": 0.5}


def fake_llm(data):
    return dict(_LLM_OUTPUTS.get(data.get("product_name"), _LLM_FALLBACK))


@pytest.fixture
def client(monkeypatch):
    import main

    monkeypatch.setattr(main, "call_llm", fake_llm)
    return TestClient(main.app)
