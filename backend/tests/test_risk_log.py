"""Phase 4: what lands in risk_decision_log — and, as importantly, what must not."""

import hashlib

import pytest

from cases import PRODUCT_EVALUATIONS, SIMULATOR_INPUTS, TRANSACTIONS
from pg_fixtures import fetch

ML_HIGH = "B0BYYPTLHX"


async def rows():
    return await fetch("select * from risk_decision_log order by id")


def catalogue_hash():
    import services.product_risk as pr

    return hashlib.sha256(pr.CATALOGUE_PATH.read_bytes()).hexdigest()


# ─── /decision/evaluate ──────────────────────────────────────────────────────────────────────────


async def test_decision_evaluate_writes_a_row(api):
    body = TRANSACTIONS["high_risk"]
    resp = (await api.post("/decision/evaluate", json=body)).json()
    [log] = await rows()
    assert (log["source"], log["formula"], log["order_id"], log["buyer_id"], log["seller_id"]) == (
        "decision_evaluate", "static_v1", None, None, None)
    assert (log["final_tier"], float(log["risk_score"]), log["escalated_from"]) == ("HIGH", resp["risk_score"], None)
    assert (float(log["buyer_trust"]), float(log["seller_trust"])) == (resp["buyer_trust"], resp["seller_trust"])
    # flat inputs mirror the request (these are the training features)
    assert (log["buyer_successful_orders"], log["buyer_total_orders"], log["buyer_disputes"], log["buyer_fraud_flags"]) == (1, 2, 1, 0)
    assert (log["seller_successful_orders"], log["seller_total_orders"], log["seller_complaints"], log["seller_fraud_flags"]) == (5, 8, 2, 0)
    assert (float(log["order_value"]), log["currency"], log["is_new_pair"], log["is_new_device"]) == (12000.0, "INR", True, True)
    assert log["request_payload"]["order_value"] == 12000 and log["code_version"]
    # the dynamic parts of the breakdown are kept whole
    assert log["components"]["risk_components"]["value_risk"] == resp["risk_components"]["value_risk"]
    assert log["components"]["buyer_breakdown"] == resp["buyer_breakdown"]
    assert log["components"]["seller_breakdown"] == resp["seller_breakdown"]
    assert "product_risk" not in log["components"]["risk_components"]  # it has its own columns


async def test_the_stored_score_and_tier_agree_at_a_boundary_score(api):
    """The Phase 2 rounding lesson: the tier is stored, not recomputed from the (rounded) score."""
    await api.post("/decision/evaluate", json=TRANSACTIONS["low_risk"])  # scores exactly 25.0 → LOW
    [log] = await rows()
    assert (str(log["risk_score"]), log["final_tier"]) == ("25.00", "LOW")


async def test_escalation_via_decision_evaluate_is_logged(api):
    await api.post("/decision/evaluate", json={**TRANSACTIONS["low_risk"], "product_id": ML_HIGH})
    [log] = await rows()
    assert (log["final_tier"], log["escalated_from"], log["product_id"]) == ("MEDIUM", "LOW", ML_HIGH)
    assert log["ml_model_version"] == catalogue_hash()


# ─── /evaluate-product and the LLM fallback flag ─────────────────────────────────────────────────


async def test_evaluate_product_writes_a_row_with_the_llm_capture(api):
    body = PRODUCT_EVALUATIONS["high_risk"]
    resp = (await api.post("/evaluate-product", json=body)).json()
    [log] = await rows()
    assert (log["source"], log["formula"], log["final_tier"], float(log["risk_score"])) == (
        "evaluate_product", "product_v1", "HIGH", resp["final_risk"])
    # the request's *_orders land in *_total_orders; fields the request doesn't have stay NULL (see services/risk_log.py)
    assert (log["buyer_total_orders"], log["buyer_disputes"], log["seller_total_orders"], log["seller_complaints"]) == (2, 5, 3, 6)
    assert (log["buyer_successful_orders"], log["buyer_fraud_flags"], log["seller_successful_orders"], log["seller_fraud_flags"]) == (None,) * 4
    assert (float(log["order_value"]), log["is_new_pair"], log["is_new_device"]) == (16500.0, True, True)
    assert (log["llm_is_fallback"], log["llm_model"], log["llm_signals"]) == (False, "gpt-4o-mini", resp["signals"])
    assert (float(log["llm_confidence"]), float(log["llm_risk_modifier"]), float(log["behavior_risk"])) == (0.9, 20.0, resp["behavior_risk"])
    assert log["components"]["risk_breakdown"]["value_risk"] == resp["risk_breakdown"]["value_risk"]
    assert log["request_payload"]["product_name"] == body["product_name"]


async def test_a_real_half_confidence_answer_is_distinct_from_the_error_fallback(api):
    """The reason for llm_is_fallback: 'no signals, modifier 0, confidence 0.5' is what the error fallback returns
    AND something a model can genuinely answer. Both must be storable and distinguishable."""
    base = PRODUCT_EVALUATIONS["medium_risk"]
    real = await api.post("/evaluate-product", json={**base, "product_name": "Genuinely neutral item"})
    fallback = await api.post("/evaluate-product", json={**base, "product_name": "Name the fake LLM has never heard of"})
    a, b = await rows()
    assert (a["llm_is_fallback"], b["llm_is_fallback"]) == (False, True)
    same = ("llm_signals", "llm_confidence", "llm_risk_modifier", "behavior_risk", "risk_score", "final_tier")
    assert {k: a[k] for k in same} == {k: b[k] for k in same}  # identical numbers ...
    assert real.json() == {**fallback.json(), "product_name": "Genuinely neutral item"}  # ... and identical API responses
    assert float(a["llm_confidence"]) == 0.5


async def test_is_fallback_is_never_exposed_in_the_api_response(api):
    r = await api.post("/evaluate-product", json=PRODUCT_EVALUATIONS["medium_risk"])
    assert "is_fallback" not in r.text


async def test_evaluate_product_escalation_and_product_columns(api):
    await api.post("/evaluate-product", json={**PRODUCT_EVALUATIONS["low_risk"], "product_id": ML_HIGH})
    [log] = await rows()
    assert (log["final_tier"], log["escalated_from"], log["product_risk_level"]) == ("MEDIUM", "LOW", "HIGH")
    assert log["product_id"] == ML_HIGH and log["llm_is_fallback"] is False


# ─── /initiate-payment (stateless) ───────────────────────────────────────────────────────────────


async def test_stateless_initiate_payment_logs_its_decision_without_an_order(api):
    r = await api.post("/initiate-payment", json={"scenario": "high_risk"})
    assert r.status_code == 200 and set(r.json()) == {"status", "lifecycle"}  # response unchanged: no ids leak in
    [log] = await rows()
    assert (log["source"], log["order_id"], log["final_tier"], float(log["order_value"])) == ("initiate_payment", None, "HIGH", 12000.0)


# ─── the routes that must NOT log ────────────────────────────────────────────────────────────────

UNLOGGED = [
    ("POST", "/simulator/evaluate", {"json": SIMULATOR_INPUTS["risky"]}),
    ("POST", "/simulator/evaluate", {"json": {}}),
    ("GET", "/simulate/high_risk", {}),
    ("GET", "/evaluate-risk", {"params": {"scenario": "high_risk"}}),
    ("GET", "/demo/payment-lifecycle", {"params": {"scenario": "high_risk"}}),
    ("POST", "/risk/score", {"json": TRANSACTIONS["high_risk"]}),
    ("POST", "/risk/score", {"json": {**TRANSACTIONS["low_risk"], "product_id": ML_HIGH}}),
    ("POST", "/trust/buyer", {"json": TRANSACTIONS["low_risk"]["buyer"]}),
    ("POST", "/trust/seller", {"json": TRANSACTIONS["low_risk"]["seller"]}),
    ("POST", "/verify", {"json": {}}),
    ("POST", "/settle", {"json": {}}),
    ("GET", "/health", {}),
]


@pytest.mark.parametrize("method,path,kwargs", UNLOGGED, ids=[f"{m} {p}" for m, p, _ in UNLOGGED])
async def test_route_writes_no_log_row(api, method, path, kwargs):
    r = await api.request(method, path, **kwargs)
    assert r.status_code == 200
    assert await rows() == []


@pytest.mark.parametrize(
    "method,path,kwargs",
    [("POST", "/decision/evaluate", {"json": {"order_value": 5}}), ("POST", "/evaluate-product", {"json": {}}),
     ("POST", "/initiate-payment", {"json": {"scenario": "nope"}})],
    ids=["invalid-decision-evaluate", "invalid-evaluate-product", "bad-scenario"],
)
async def test_rejected_requests_write_nothing(api, method, path, kwargs):
    assert (await api.request(method, path, **kwargs)).status_code in (400, 422)
    assert await rows() == []


async def test_order_mode_initiate_verify_settle_write_no_extra_log_rows(api):
    order = (await api.post("/orders", json={"buyer_id": "b", "seller_id": "s", **TRANSACTIONS["high_risk"]})).json()
    for route, body in (("/initiate-payment", {}), ("/verify", {}), ("/settle", {"action": "release"})):
        assert (await api.post(route, json={"order_id": order["order_id"], **body})).status_code == 200
    assert [r["source"] for r in await rows()] == ["orders_create"]


async def test_every_logged_call_adds_exactly_one_row(api):
    calls = [("/decision/evaluate", TRANSACTIONS["low_risk"]), ("/decision/evaluate", TRANSACTIONS["high_risk"]),
             ("/evaluate-product", PRODUCT_EVALUATIONS["medium_risk"]), ("/initiate-payment", {"scenario": "low_risk"})]
    for path, body in calls:
        await api.post(path, json=body)
    assert [r["source"] for r in await rows()] == ["decision_evaluate", "decision_evaluate", "evaluate_product", "initiate_payment"]


# ─── a rejected row is not an outage ─────────────────────────────────────────────────────────────


async def test_a_rejected_row_is_reported_but_does_not_trip_the_breaker(pg, caplog):
    import logging

    import db
    from services import risk_log

    caplog.set_level(logging.ERROR, logger="trustos.risk_log")
    bad = {"source": "unit", "formula": "static_v1", "code_version": "t", "request_payload": {}, "risk_score": 999, "final_tier": "LOW"}
    good = {**bad, "risk_score": 10}
    assert await risk_log.log_decision_fail_open(lambda: bad, source="unit") is None
    assert "FAILED" in caplog.records[-1].getMessage() and not db.circuit_is_open()  # a CHECK violation isn't "database down"
    assert isinstance(await risk_log.log_decision_fail_open(lambda: good, source="unit"), int)  # the next write goes straight through
    assert len(await rows()) == 1
