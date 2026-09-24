"""Phase 3: the product-risk adapter and the escalate-only rule."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cases import PRODUCT_EVALUATIONS, TRANSACTIONS
from models import ProductRiskModel
from services.decision_engine import escalate_tier
from services.product_risk import assess_product

# Catalogue products with a known ML level (seed model, random_state 42). The level is re-asserted
# in test_fixture_levels so a retrained model can't silently turn these tests into no-ops.
ML_HIGH = "B0BYYPTLHX"    # 1000pcs rubber hair ties — score 100.0
ML_MEDIUM = "B0014LE00U"  # ZonePerfect protein bars — score 56.3
ML_LOW = "B07FSDFF75"     # titanium dangle earrings — score 0.0
UNKNOWN = "NOT-A-CATALOGUE-ID"

GOLDEN = json.loads((Path(__file__).parent / "golden" / "pre_phase3_responses.json").read_text(encoding="utf-8"))


def _pr(level, applicable=True):
    return ProductRiskModel(product_id="x", applicable=applicable, score=0.0 if applicable else None, level=level if applicable else None)


# ─── the rule itself ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "base,ml,expected",
    [
        ("LOW", "LOW", "LOW"),
        ("LOW", "MEDIUM", "MEDIUM"),
        ("LOW", "HIGH", "MEDIUM"),       # ML alone never triggers the wallet hold
        ("MEDIUM", "LOW", "MEDIUM"),     # never downgrades
        ("MEDIUM", "MEDIUM", "MEDIUM"),
        ("MEDIUM", "HIGH", "MEDIUM"),
        ("HIGH", "LOW", "HIGH"),         # never downgrades
        ("HIGH", "MEDIUM", "HIGH"),
        ("HIGH", "HIGH", "HIGH"),
    ],
)
def test_escalate_tier_matrix(base, ml, expected):
    assert escalate_tier(base, _pr(ml)) == expected


@pytest.mark.parametrize("base", ["LOW", "MEDIUM", "HIGH"])
def test_not_applicable_or_absent_is_a_no_op(base):
    assert escalate_tier(base, None) == base
    assert escalate_tier(base, _pr(None, applicable=False)) == base


# ─── the adapter ─────────────────────────────────────────────────────────────


def test_fixture_levels():
    for pid, level in ((ML_HIGH, "HIGH"), (ML_MEDIUM, "MEDIUM"), (ML_LOW, "LOW")):
        pr = assess_product(pid)
        assert pr.applicable and pr.level == level, pid


def test_catalogue_product_uses_all_8_features():
    pr = assess_product(ML_HIGH)
    assert pr.applicable and pr.imputed_features == []
    assert pr.score == 100.0 and pr.top_features  # a HIGH product always has a "why"


def test_boundary_product_level_matches_displayed_score():
    """Regression: B00MN8X5RM's unrounded score is 30.0128. It used to be returned as score 30.0
    with level MEDIUM, although 30.0 is LOW. The tier now comes from the displayed score."""
    pr = assess_product("B00MN8X5RM")
    assert pr.score == 30.0
    assert pr.level == "LOW"


def test_displayed_score_and_level_never_disagree():
    from services.product_risk import _catalogue
    from services.risk_engine import RiskEngine

    for pid in _catalogue():
        pr = assess_product(pid)
        assert pr.level == RiskEngine.classify(pr.score), pid


def test_unknown_and_absent_ids():
    assert assess_product(None) is None
    pr = assess_product(UNKNOWN)
    assert pr.applicable is False and pr.level is None and pr.score is None and pr.reason


def test_sklearn_is_imported_lazily():
    """Requests without a catalogue product_id must never import numpy/sklearn or fit the model."""
    code = (
        "import os, sys; os.environ['OPENAI_API_KEY'] = 'sk-test-not-a-real-key'\n"
        "from fastapi.testclient import TestClient\n"
        "import main\n"
        "c = TestClient(main.app)\n"
        f"body = {TRANSACTIONS['medium_risk']!r}\n"
        "assert c.post('/decision/evaluate', json=body).status_code == 200\n"
        f"assert c.post('/decision/evaluate', json={{**body, 'product_id': {UNKNOWN!r}}}).status_code == 200\n"
        "assert 'sklearn' not in sys.modules, 'sklearn imported without a catalogue product'\n"
        f"assert c.post('/decision/evaluate', json={{**body, 'product_id': {ML_HIGH!r}}}).status_code == 200\n"
        "assert 'sklearn' in sys.modules\n"
    )
    backend = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-c", code], cwd=backend, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr


# ─── end to end through the routes ───────────────────────────────────────────


def _decision(client, txn, product_id):
    return client.post("/decision/evaluate", json={**TRANSACTIONS[txn], "product_id": product_id}).json()


def test_low_transaction_escalated_by_high_product(client):
    base = GOLDEN["decision_evaluate.low_risk"]["body"]
    assert base["decision"]["risk_classification"] == "LOW"
    got = _decision(client, "low_risk", ML_HIGH)
    assert got["decision"]["risk_classification"] == "MEDIUM"
    assert got["decision"]["escalated_from"] == "LOW"
    assert got["risk_score"] == base["risk_score"]  # the score itself is untouched
    assert got["risk_components"]["product_risk"]["level"] == "HIGH"
    # Apart from escalated_from, the decision is exactly the regular MEDIUM decision.
    medium = GOLDEN["decision_evaluate.medium_risk"]["body"]["decision"]  # a recorded MEDIUM decision
    assert {k: v for k, v in got["decision"].items() if k != "escalated_from"} == medium


def test_low_transaction_escalated_by_medium_product(client):
    got = _decision(client, "low_risk", ML_MEDIUM)
    assert got["decision"]["risk_classification"] == "MEDIUM"
    assert got["decision"]["escalated_from"] == "LOW"


def test_low_product_changes_nothing_but_reports_itself(client):
    got = _decision(client, "low_risk", ML_LOW)
    assert "escalated_from" not in got["decision"]
    assert got["risk_components"]["product_risk"]["level"] == "LOW"
    got["risk_components"].pop("product_risk")
    assert got == GOLDEN["decision_evaluate.low_risk"]["body"]


@pytest.mark.parametrize("product_id", [ML_LOW, ML_MEDIUM, ML_HIGH])
def test_high_transaction_stays_high(client, product_id):
    got = _decision(client, "high_risk", product_id)
    assert got["decision"]["risk_classification"] == "HIGH"
    assert "escalated_from" not in got["decision"]


def test_medium_transaction_is_not_raised_to_high(client):
    got = _decision(client, "medium_risk", ML_HIGH)  # a MEDIUM (44.02) transaction
    assert got["decision"]["risk_classification"] == "MEDIUM"
    assert "escalated_from" not in got["decision"]


def test_evaluate_product_escalation(client):
    base = GOLDEN["evaluate_product.low_risk"]["body"]
    assert base["decision"] == "LOW"
    r = client.post("/evaluate-product", json={**PRODUCT_EVALUATIONS["low_risk"], "product_id": ML_HIGH})
    got = r.json()
    assert got["decision"] == "MEDIUM" and got["escalated_from"] == "LOW"
    assert got["final_risk"] == base["final_risk"]
    assert got["product_id"] == ML_HIGH
    assert got["risk_breakdown"]["product_risk"]["level"] == "HIGH"


def test_evaluate_product_high_stays_high(client):
    r = client.post("/evaluate-product", json={**PRODUCT_EVALUATIONS["high_risk"], "product_id": ML_LOW})
    got = r.json()
    assert got["decision"] == "HIGH" and "escalated_from" not in got


def test_risk_score_reports_product_risk_without_changing_score(client):
    r = client.post("/risk/score", json={**TRANSACTIONS["low_risk"], "product_id": ML_HIGH})
    got = r.json()
    assert got["risk_score"] == GOLDEN["risk_score.low_risk"]["body"]["risk_score"]
    assert got["components"]["product_risk"]["level"] == "HIGH"
