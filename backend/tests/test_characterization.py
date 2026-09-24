"""Characterization tests: pin the API's pre-Phase-3 responses so wiring the product risk model in
cannot silently change behaviour for requests that don't use it.

``golden/pre_phase3_responses.json`` was recorded from the code *before* any Phase 3 change
(commit 76d4711). Do not regenerate it to make a failing test pass; a diff here means existing
callers would see different output. (Regenerate only for a deliberate, reviewed behaviour change:
``TRUSTOS_UPDATE_GOLDEN=1 python -m pytest tests/test_characterization.py``.)
"""

import copy
import json
import os
from pathlib import Path

import pytest

from cases import PRODUCT_EVALUATIONS, TRANSACTIONS, all_cases

GOLDEN_PATH = Path(__file__).parent / "golden" / "pre_phase3_responses.json"
UPDATE = os.environ.get("TRUSTOS_UPDATE_GOLDEN") == "1"

CASES = all_cases()


def _call(client, method, path, kwargs):
    r = client.request(method, path, **kwargs)
    return {"status": r.status_code, "body": r.json()}


def _golden():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_record_golden(client):
    if not UPDATE:
        pytest.skip("set TRUSTOS_UPDATE_GOLDEN=1 to re-record")
    out = {name: _call(client, m, p, kw) for name, m, p, kw in CASES}
    GOLDEN_PATH.parent.mkdir(exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@pytest.mark.parametrize("name,method,path,kwargs", CASES, ids=[c[0] for c in CASES])
def test_response_unchanged(client, name, method, path, kwargs):
    assert _call(client, method, path, kwargs) == _golden()[name]


def test_golden_covers_every_tier():
    """Guard against the golden set only exercising one branch of the decision engine."""
    g = _golden()
    tiers = {g[f"decision_evaluate.{s}"]["body"]["decision"]["risk_classification"] for s in TRANSACTIONS}
    assert tiers == {"LOW", "MEDIUM", "HIGH"}
    assert {g[f"evaluate_product.{s}"]["body"]["decision"] for s in PRODUCT_EVALUATIONS} == {"LOW", "MEDIUM", "HIGH"}


# ─── product_id absent / null / unknown must not change anything ─────────────


def _strip_product_risk(body):
    """Remove the only additions an unknown id may cause: the Phase 3 ``product_risk`` sub-object,
    and /evaluate-product's echo of the request's own ``product_id``."""
    body = copy.deepcopy(body)
    body.pop("product_id", None)
    for container in ("risk_components", "components", "risk_breakdown"):
        if isinstance(body.get(container), dict):
            body[container].pop("product_risk", None)
    return body


PRODUCT_ID_ROUTES = [
    *[(f"decision_evaluate.{s}", "/decision/evaluate", TRANSACTIONS[s]) for s in TRANSACTIONS],
    *[(f"risk_score.{s}", "/risk/score", TRANSACTIONS[s]) for s in TRANSACTIONS],
    *[(f"evaluate_product.{s}", "/evaluate-product", PRODUCT_EVALUATIONS[s]) for s in PRODUCT_EVALUATIONS],
]


@pytest.mark.parametrize("name,path,body", PRODUCT_ID_ROUTES, ids=[r[0] for r in PRODUCT_ID_ROUTES])
def test_null_product_id_is_identical(client, name, path, body):
    """An explicit ``"product_id": null`` is byte-for-byte the pre-Phase-3 response."""
    r = client.post(path, json={**body, "product_id": None})
    assert {"status": r.status_code, "body": r.json()} == _golden()[name]


@pytest.mark.parametrize("name,path,body", PRODUCT_ID_ROUTES, ids=[r[0] for r in PRODUCT_ID_ROUTES])
def test_unknown_product_id_is_identical(client, name, path, body):
    """An id that isn't in the catalogue changes no score, tier or decision. The only addition is
    ``product_risk`` with ``applicable: false`` so the caller can tell the lookup failed (and
    /evaluate-product echoing the id back, as it echoes every request field)."""
    r = client.post(path, json={**body, "product_id": "NOT-A-CATALOGUE-ID"})
    got = r.json()
    assert r.status_code == _golden()[name]["status"]
    assert _strip_product_risk(got) == _golden()[name]["body"]
