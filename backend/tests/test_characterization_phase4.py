"""Phase 4 characterization: pin the API's responses for requests WITHOUT ``order_id`` so adding
persistence cannot change what existing callers see.

``golden/pre_phase4_responses.json`` was recorded from the code at commit b403fe6, before any Phase 4
source change (only these tests and ``cases.phase4_baseline_cases`` existed). It complements
``test_characterization.py`` (the Phase 3 set, which also has to keep passing) by covering what that
set never pinned: /verify, /settle, /initiate-payment's edge cases and the 400/404/422 error paths.
This file runs with no DATABASE_URL, so it also proves the routes work with persistence off.
Do not regenerate it to make a failing test pass (``TRUSTOS_UPDATE_GOLDEN_P4=1`` is for deliberate,
reviewed behaviour changes only).
"""

import json
import os
from pathlib import Path

import pytest

from cases import TRANSACTIONS, phase4_baseline_cases

GOLDEN_PATH = Path(__file__).parent / "golden" / "pre_phase4_responses.json"
UPDATE = os.environ.get("TRUSTOS_UPDATE_GOLDEN_P4") == "1"
CASES = phase4_baseline_cases()


def _call(client, method, path, kwargs):
    r = client.request(method, path, **kwargs)
    return {"status": r.status_code, "body": r.json()}


def _golden():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_record_golden(client):
    if not UPDATE:
        pytest.skip("set TRUSTOS_UPDATE_GOLDEN_P4=1 to re-record")
    out = {name: _call(client, m, p, kw) for name, m, p, kw in CASES}
    GOLDEN_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@pytest.mark.parametrize("name,method,path,kwargs", CASES, ids=[c[0] for c in CASES])
def test_response_unchanged(client, name, method, path, kwargs):
    assert _call(client, method, path, kwargs) == _golden()[name]


def test_golden_has_a_case_per_name():
    assert set(_golden()) == {c[0] for c in CASES}


# ─── an explicit order_id: null is the stateless demo, byte for byte ─────────────────────────────

NULL_ORDER_ID_ROUTES = [
    (n, m, p, kw) for n, m, p, kw in CASES
    if p in ("/verify", "/settle", "/initiate-payment") and isinstance(kw.get("json"), dict)
    and n.split(".")[1] not in ("bad_type", "null_action", "bad_scenario", "invalid_action")
]


@pytest.mark.parametrize("name,method,path,kwargs", NULL_ORDER_ID_ROUTES, ids=[c[0] for c in NULL_ORDER_ID_ROUTES])
def test_null_order_id_is_identical(client, name, method, path, kwargs):
    body = {**kwargs["json"], "order_id": None}
    assert _call(client, method, path, {"json": body}) == _golden()[name]


def test_golden_covers_the_stateful_routes():
    g = _golden()
    assert {g[n]["body"]["result"] for n in g if n.startswith("verify.") and g[n]["status"] == 200} == {
        "SUCCESS", "FRAUD", "INCONSISTENT"}
    assert {g[n]["body"]["status"] for n in g if n.startswith("settle.") and g[n]["status"] == 200} == {
        "CAPTURED", "RELEASED", "CANCELLED"}
    assert {422, 400, 404} <= {r["status"] for r in g.values()}
    assert TRANSACTIONS  # (fixtures are shared with the Phase 3 tests)
