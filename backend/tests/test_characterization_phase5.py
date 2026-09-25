"""Phase 5 characterization: pin what the LEGACY (unversioned) routes do in order mode, and the legacy
OpenAPI contract, so extracting the order logic into shared services (and adding /v1) cannot change it.

``golden/pre_phase5_responses.json`` was recorded from the code at commit e314c78 (HEAD before Phase 5a),
before any source change. It covers what the Phase 3/4 goldens never pinned: the full response BODIES and
error messages of ``POST /orders`` and of ``/initiate-payment``, ``/verify``, ``/settle`` with an
``order_id`` (those tests in test_orders_api.py assert status codes and database rows), the 503 answers
with persistence off, and the OpenAPI shape (operation ids, parameters, request bodies, responses) of every
legacy route. Do not regenerate it to make a failing test pass (``TRUSTOS_UPDATE_GOLDEN_P5=1`` is for
deliberate, reviewed behaviour changes only).

Ids and timestamps vary per run, so they are normalised to ``<uuid-N>`` (by first appearance) and ``<ts>``.
"""

import json
import os
import re
from pathlib import Path

import pytest

from cases import TRANSACTIONS
from pg_fixtures import fetch

GOLDEN_PATH = Path(__file__).parent / "golden" / "pre_phase5_responses.json"
UPDATE = os.environ.get("TRUSTOS_UPDATE_GOLDEN_P5") == "1"
ML_HIGH = "B0BYYPTLHX"
GHOST = "11111111-1111-1111-1111-111111111111"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?")


def normalise(obj):
    text = json.dumps(obj, sort_keys=True, default=str)
    seen = {}
    text = _UUID.sub(lambda m: seen.setdefault(m.group(0), f"<uuid-{len(seen) + 1}>"), text)
    text = _TS.sub("<ts>", text)
    return json.loads(text)


def localise(obj):
    """Renumber the ``<uuid-N>`` placeholders by first appearance WITHIN this one value. ``normalise`` numbers ids
    across the whole walk, so one step's numbers shift whenever an earlier step's body gains or loses an id; comparing
    step by step with local numbering keeps the equality pattern inside a step and drops that spurious coupling."""
    text = json.dumps(obj, sort_keys=True)
    seen = {}
    text = re.sub(r"<uuid-\d+>", lambda m: seen.setdefault(m.group(0), f"<uuid-{len(seen) + 1}>"), text)
    return json.loads(text)


def _golden():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def order_body(fixture, **extra):
    return {"buyer_id": "buyer-1", "seller_id": "seller-9", **TRANSACTIONS[fixture], **extra}


# ─── legacy order mode, persistence live ─────────────────────────────────────────────────────────


async def run_legacy_order_script(api):
    """One deterministic walk through every legacy order-mode route and its guards. Returns
    {step: {"status", "body"}} plus a final dump of what ended up in the tables."""
    steps = {}
    ids = {}

    async def call(name, method, path, **kw):
        r = await api.request(method, path.format(**ids), **kw)
        steps[name] = {"status": r.status_code, "body": r.json()}
        return r

    async def order(name, fixture, **extra):
        r = await call(name, "POST", "/orders", json=order_body(fixture, **extra))
        ids[name] = r.json()["order_id"]

    # creation: one order per tier, plus a product escalation and an unknown catalogue id
    await order("low", "low_risk")
    await order("medium", "medium_risk")
    await order("medium_fraud", "medium_risk")
    await order("medium_cancel", "medium_risk")
    await order("high", "high_risk")
    await order("escalated", "low_risk", product_id=ML_HIGH)
    await order("unknown_product", "low_risk", product_id="NOT-IN-CATALOGUE")

    # unknown order everywhere
    for route in ("/initiate-payment", "/verify", "/settle"):
        await call(f"ghost{route}", "POST", route, json={"order_id": GHOST})

    # MEDIUM: guards before the payment exists, the happy path, then the illegal moves
    await call("medium.verify_before_payment", "POST", "/verify", json={"order_id": ids["medium"]})
    await call("medium.settle_before_payment", "POST", "/settle", json={"order_id": ids["medium"]})
    await call("medium.initiate", "POST", "/initiate-payment", json={"order_id": ids["medium"], "scenario": "high_risk"})
    await call("medium.initiate_again", "POST", "/initiate-payment", json={"order_id": ids["medium"]})
    await call("medium.verify", "POST", "/verify", json={"order_id": ids["medium"]})
    await call("medium.verify_retry_fail", "POST", "/verify", json={"order_id": ids["medium"], "passed": False})
    await call("medium.settle_release_illegal", "POST", "/settle", json={"order_id": ids["medium"], "action": "release"})
    await call("medium.settle_bad_action", "POST", "/settle", json={"order_id": ids["medium"], "action": "refund"})
    await call("medium.settle_capture", "POST", "/settle", json={"order_id": ids["medium"], "action": " Capture "})
    await call("medium.settle_again", "POST", "/settle", json={"order_id": ids["medium"], "action": "cancel"})
    await call("medium.verify_when_completed", "POST", "/verify", json={"order_id": ids["medium"], "inconsistent": True})

    # LEGACY BEHAVIOUR THAT /v1 DELIBERATELY CHANGES: /settle does not look at the verification result,
    # so an order whose verification says FRAUD can still be captured.
    await call("medium_fraud.initiate", "POST", "/initiate-payment", json={"order_id": ids["medium_fraud"]})
    await call("medium_fraud.verify_fraud", "POST", "/verify", json={"order_id": ids["medium_fraud"], "passed": False})
    await call("medium_fraud.settle_capture", "POST", "/settle", json={"order_id": ids["medium_fraud"], "action": "capture"})

    # cancel, then nothing more can be verified
    await call("medium_cancel.initiate", "POST", "/initiate-payment", json={"order_id": ids["medium_cancel"]})
    await call("medium_cancel.settle_cancel", "POST", "/settle", json={"order_id": ids["medium_cancel"], "action": "cancel"})
    await call("medium_cancel.verify", "POST", "/verify", json={"order_id": ids["medium_cancel"]})

    # HIGH: wallet hold, a capture is illegal, release is fine
    await call("high.initiate", "POST", "/initiate-payment", json={"order_id": ids["high"]})
    await call("high.settle_capture_illegal", "POST", "/settle", json={"order_id": ids["high"], "action": "capture"})
    await call("high.verify_inconsistent", "POST", "/verify", json={"order_id": ids["high"], "inconsistent": True})
    await call("high.settle_release", "POST", "/settle", json={"order_id": ids["high"], "action": "release"})

    # LOW: instant capture, nothing left to settle
    await call("low.initiate", "POST", "/initiate-payment", json={"order_id": ids["low"]})
    await call("low.verify", "POST", "/verify", json={"order_id": ids["low"]})
    await call("low.settle_cancel_illegal", "POST", "/settle", json={"order_id": ids["low"], "action": "cancel"})

    await call("escalated.initiate", "POST", "/initiate-payment", json={"order_id": ids["escalated"]})

    # what the walk left in the database
    steps["db.orders"] = await _dump("select status, risk_tier, risk_score, amount, currency, product_id, buyer_id, seller_id from orders order by created_at, order_id")
    steps["db.payments"] = await _dump("select route, status, triggered_by, amount, provider, (authorized_at is not null) as authorized, (settled_at is not null) as settled from payments order by created_at, payment_id")
    steps["db.verifications"] = await _dump("select type, result, (completed_at is not null) as completed from verifications order by created_at, verification_id")
    steps["db.risk_log"] = await _dump("select source, formula, final_tier, escalated_from, (order_id is not null) as has_order from risk_decision_log order by id")
    return steps


async def _dump(sql):
    rows = await fetch(sql)
    return [{k: (str(v) if not isinstance(v, (bool, int, type(None))) else v) for k, v in r.items()} for r in rows]


async def test_record_order_mode_golden(api):
    if not UPDATE:
        pytest.skip("set TRUSTOS_UPDATE_GOLDEN_P5=1 to re-record")
    golden = _golden() if GOLDEN_PATH.exists() else {}
    # "order_mode" is the PRE-Phase-5 record. Overwriting it would destroy the only copy (the file is not in git history
    # of the code it was recorded from), so it is written once. Deliberate behaviour changes go in the overrides instead.
    assert "order_mode" not in golden, "order_mode is the pre-Phase-5 record; add an override instead of re-recording it"
    golden["order_mode"] = normalise(await run_legacy_order_script(api))
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# The steps whose answer changed on purpose when the legacy /settle (with an order_id) started enforcing
# verification-before-capture/release, exactly as /v1 does. The two the change was made for are marked (*); the rest
# follow from the walk itself (it records a FRAUD retry on the 'medium' order before capturing it). Each has a reason
# in the golden's "order_mode_gate_overrides"; every OTHER step must still equal the pre-Phase-5 record.
GATE_CHANGED_STEPS = {
    "medium_fraud.settle_capture",  # (*) capture after FRAUD: was 200
    "high.settle_release",  # (*) release after INCONSISTENT: was 200
    "medium.settle_capture", "medium.settle_again", "medium.verify_when_completed",
    "db.orders", "db.payments", "db.verifications",
}


def expected_order_mode():
    golden = _golden()
    expected = {step: localise(entry) for step, entry in golden["order_mode"].items()}
    for step, override in golden["order_mode_gate_overrides"].items():
        expected[step] = override["entry"]
    return expected


async def test_legacy_order_mode_is_unchanged_except_the_verification_gate(v1):
    """Replays the whole pre-Phase-5 walk, now WITH an API key (the order_id-bearing legacy routes require one).
    Every status, body and database row must equal what was recorded before Phase 5a touched a line, except the
    steps in GATE_CHANGED_STEPS, whose new answers are pinned in the golden's overrides. Compared step by step
    with locally numbered ids, so one step's ids can't perturb another's."""
    got = normalise(await run_legacy_order_script(v1))
    want = expected_order_mode()
    assert set(got) == set(want)
    for step in want:
        assert localise(got[step]) == want[step], step


def test_the_overrides_are_exactly_the_intended_and_each_is_a_real_change():
    golden = _golden()
    overrides = golden["order_mode_gate_overrides"]
    assert set(overrides) == GATE_CHANGED_STEPS
    for step, override in overrides.items():
        assert override["reason"], step
        assert override["entry"] != localise(golden["order_mode"][step]), f"{step}: an override that changes nothing"
    # the two the change was made for
    assert golden["order_mode"]["medium_fraud.settle_capture"]["status"] == 200  # the bypass, as recorded before
    assert overrides["medium_fraud.settle_capture"]["entry"]["status"] == 409
    assert golden["order_mode"]["high.settle_release"]["status"] == 200
    assert overrides["high.settle_release"]["entry"] == {
        "body": {"detail": "cannot release: the latest verification is INCONSISTENT; SUCCESS is required"}, "status": 409}


# ─── legacy order mode, persistence off ──────────────────────────────────────────────────────────

NO_DB_CASES = [
    ("orders", "/orders", order_body("medium_risk")),
    ("initiate", "/initiate-payment", {"order_id": GHOST}),
    ("verify", "/verify", {"order_id": GHOST}),
    ("settle", "/settle", {"order_id": GHOST}),
]


def _call_no_db(client):
    out = {}
    for name, path, body in NO_DB_CASES:
        r = client.post(path, json=body)
        out[name] = {"status": r.status_code, "body": r.json()}
    return out


def test_record_no_db_golden(client):
    if not UPDATE:
        pytest.skip("set TRUSTOS_UPDATE_GOLDEN_P5=1 to re-record")
    golden = _golden() if GOLDEN_PATH.exists() else {}
    golden["no_db"] = _call_no_db(client)
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def test_legacy_order_mode_without_persistence_is_unchanged(client):
    """POST /orders is untouched. The three order_id-bearing routes deliberately changed: with no key they are a
    401 now (test_legacy_order_mode_auth.py) and with a key they are still a 503, but their message says the key
    could not be checked, so the golden entries for them are no longer expected to match."""
    got, want = _call_no_db(client), _golden()["no_db"]
    assert got["orders"] == want["orders"]
    for name in ("initiate", "verify", "settle"):
        assert want[name]["status"] == 503  # what they used to answer
        assert got[name] == {"status": 401, "body": {"detail": "Missing X-API-Key header"}}


# ─── the legacy OpenAPI contract ─────────────────────────────────────────────────────────────────

LEGACY_PATHS = [
    "/trust/buyer", "/trust/seller", "/evaluate-product", "/risk/score", "/simulator/evaluate", "/decision/evaluate",
    "/orders", "/simulate/{scenario}", "/health", "/evaluate-risk", "/demo/payment-lifecycle",
    "/initiate-payment", "/verify", "/settle",
]


def legacy_contract(client):
    """Everything about each legacy operation except its human-readable description/summary, which Phase 5a
    deliberately extends with a "deprecated for external use" note."""
    paths = client.get("/openapi.json").json()["paths"]
    out = {}
    for path in LEGACY_PATHS:
        out[path] = {
            method: {k: v for k, v in op.items() if k not in ("description", "summary")} for method, op in paths[path].items()
        }
    return out


def test_record_openapi_golden(client):
    if not UPDATE:
        pytest.skip("set TRUSTOS_UPDATE_GOLDEN_P5=1 to re-record")
    golden = _golden() if GOLDEN_PATH.exists() else {}
    golden["openapi"] = legacy_contract(client)
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


@pytest.mark.parametrize("path", LEGACY_PATHS)
def test_legacy_openapi_operation_is_unchanged(client, path):
    assert legacy_contract(client)[path] == _golden()["openapi"][path]
