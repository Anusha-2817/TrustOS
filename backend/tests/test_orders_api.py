"""Phase 4: POST /orders and the order-aware /initiate-payment, /verify, /settle, against a real PostgreSQL."""

import asyncio
import hashlib

import pytest

from cases import TRANSACTIONS
from pg_fixtures import fetch

# cases.TRANSACTIONS fixtures are named by the tier they score.
TIER_FIXTURE = {"LOW": "low_risk", "MEDIUM": "medium_risk", "HIGH": "high_risk"}
ML_HIGH = "B0BYYPTLHX"  # catalogue product whose anomaly score is HIGH (Phase 3 fixture)


@pytest.fixture
async def api(api, key):
    """Everything here drives the legacy order-mode routes, which since Phase 5a need an X-API-Key."""
    api.headers["X-API-Key"] = key
    return api


def order_body(tier="MEDIUM", **overrides):
    return {"buyer_id": "buyer-1", "seller_id": "seller-9", **TRANSACTIONS[TIER_FIXTURE[tier]], **overrides}


async def create(api, tier="MEDIUM", **overrides):
    r = await api.post("/orders", json=order_body(tier, **overrides))
    assert r.status_code == 201, r.text
    return r.json()


async def count(table):
    return (await fetch(f"select count(*) as n from {table}"))[0]["n"]


# ─── POST /orders ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tier", ["LOW", "MEDIUM", "HIGH"])
async def test_create_order_writes_order_and_decision_together(api, tier):
    body = await create(api, tier)
    assert body["status"] == "CREATED" and body["evaluation"]["decision"]["risk_classification"] == tier
    assert (body["buyer_id"], body["seller_id"], body["currency"]) == ("buyer-1", "seller-9", "INR")

    [order] = await fetch("select * from orders")
    [log] = await fetch("select * from risk_decision_log")
    assert str(order["order_id"]) == body["order_id"] and log["order_id"] == order["order_id"]
    assert (order["status"], order["risk_tier"], float(order["amount"])) == ("CREATED", tier, order_body(tier)["order_value"])
    # the order's denormalised risk fields are the log row's (which is authoritative)
    assert (order["risk_score"], order["risk_tier"]) == (log["risk_score"], log["final_tier"])
    assert float(log["risk_score"]) == body["evaluation"]["risk_score"]
    assert (log["source"], log["formula"], log["buyer_id"], log["seller_id"]) == ("orders_create", "static_v1", "buyer-1", "seller-9")
    assert log["escalated_from"] is None and log["product_risk_applicable"] is None and log["llm_is_fallback"] is None
    assert log["request_payload"]["buyer_id"] == "buyer-1"


async def test_the_order_is_evaluated_exactly_like_decision_evaluate(api):
    """POST /orders adds persistence; it must not change the decision."""
    order = await create(api, "MEDIUM")
    plain = await api.post("/decision/evaluate", json=TRANSACTIONS[TIER_FIXTURE["MEDIUM"]])
    assert order["evaluation"] == plain.json()


async def test_product_escalation_is_recorded_with_its_provenance(api):
    body = await create(api, "LOW", product_id=ML_HIGH)
    assert body["evaluation"]["decision"]["risk_classification"] == "MEDIUM"
    assert body["evaluation"]["decision"]["escalated_from"] == "LOW"

    [order] = await fetch("select * from orders")
    [log] = await fetch("select * from risk_decision_log")
    assert (order["risk_tier"], order["product_id"]) == ("MEDIUM", ML_HIGH)
    assert (log["final_tier"], log["escalated_from"]) == ("MEDIUM", "LOW")
    assert log["risk_score"] == order["risk_score"] and float(log["risk_score"]) == 25.0  # the score is never changed by ML
    assert (log["product_risk_applicable"], log["product_risk_level"]) == (True, "HIGH")
    assert float(log["product_risk_score"]) == 100.0 and log["product_risk_imputed"] == []
    assert log["product_risk_top_features"] and "feature" in log["product_risk_top_features"][0]
    import services.product_risk as pr

    assert log["ml_model_version"] == hashlib.sha256(pr.CATALOGUE_PATH.read_bytes()).hexdigest()


async def test_unknown_product_id_is_recorded_as_not_applicable(api):
    await create(api, "LOW", product_id="NOT-IN-CATALOGUE")
    [log] = await fetch("select * from risk_decision_log")
    assert log["product_risk_applicable"] is False
    assert log["product_risk_score"] is None and log["ml_model_version"] is None and log["escalated_from"] is None


async def test_order_creation_is_atomic_when_the_log_row_is_rejected(api, monkeypatch):
    """Fail closed: if the decision can't be recorded, there is no order either."""
    import services.risk_log as risk_log

    real = risk_log.pipeline_record
    monkeypatch.setattr(risk_log, "pipeline_record", lambda *a, **k: {**real(*a, **k), "risk_score": 999})  # violates the CHECK
    r = await api.post("/orders", json=order_body("MEDIUM"))
    assert r.status_code == 503
    assert (await count("orders"), await count("risk_decision_log")) == (0, 0)


async def test_order_creation_is_atomic_when_the_order_row_is_rejected(api):
    # 1e-9 passes request validation (> 0) but rounds to 0.00, which violates orders.amount > 0
    r = await api.post("/orders", json=order_body("MEDIUM", order_value=1e-9))
    assert r.status_code == 503
    assert (await count("orders"), await count("risk_decision_log")) == (0, 0)


@pytest.mark.parametrize(
    "patch",
    [{"buyer_id": ""}, {"seller_id": ""}, {"buyer_id": None}, {"order_value": 0}, {"order_value": 1e11}, {"buyer_id": "x" * 201}],
    ids=["empty-buyer", "empty-seller", "null-buyer", "zero-value", "value-overflows-numeric", "buyer-too-long"],
)
async def test_invalid_order_is_a_422_and_writes_nothing(api, patch):
    r = await api.post("/orders", json=order_body("MEDIUM", **patch))
    assert r.status_code == 422
    assert (await count("orders"), await count("risk_decision_log")) == (0, 0)


async def test_missing_ids_are_a_422(api):
    r = await api.post("/orders", json=TRANSACTIONS["low_risk"])
    assert r.status_code == 422


async def test_amounts_are_stored_as_exact_decimals(api):
    await create(api, "MEDIUM", order_value=1234.5)
    [order] = await fetch("select amount from orders")
    assert str(order["amount"]) == "1234.50"


# ─── POST /initiate-payment with order_id ────────────────────────────────────────────────────────

EXPECTED_PAYMENT = {
    #        response status, payment route,      order status, verification type
    "LOW": ("CAPTURED", "DIRECT_CAPTURE", "COMPLETED", "PASSIVE"),
    "MEDIUM": ("AUTHORIZED", "AUTHORIZE_ONLY", "ACTIVE", "USER_CONFIRMATION"),
    "HIGH": ("HELD", "WALLET_HOLD", "ACTIVE", "MANDATORY_VIDEO"),
}


@pytest.mark.parametrize("tier", ["LOW", "MEDIUM", "HIGH"])
async def test_initiate_payment_for_an_order(api, tier):
    order = await create(api, tier)
    # scenario is ignored in order mode: the tier is the order's own, however the caller labels it
    r = await api.post("/initiate-payment", json={"order_id": order["order_id"], "scenario": "low_risk" if tier == "HIGH" else "high_risk"})
    assert r.status_code == 200, r.text
    status, route, order_status, vtype = EXPECTED_PAYMENT[tier]
    body = r.json()
    assert body["status"] == status and body["lifecycle"]["risk_classification"] == tier
    assert body["order_id"] == order["order_id"]

    [payment] = await fetch("select * from payments")
    assert str(payment["payment_id"]) == body["payment_id"]
    assert (payment["status"], payment["route"], payment["triggered_by"]) == (status, route, "AUTO")
    assert payment["authorized_at"] is not None and (payment["settled_at"] is not None) == (status == "CAPTURED")
    assert (float(payment["amount"]), payment["currency"], payment["provider"]) == (order_body(tier)["order_value"], "INR", "razorpay_simulation")
    [verification] = await fetch("select * from verifications")
    assert (str(verification["verification_id"]), verification["type"], verification["result"], verification["completed_at"]) == (
        body["verification_id"], vtype, "PENDING", None)
    assert (await fetch("select status from orders"))[0]["status"] == order_status
    assert await count("risk_decision_log") == 1  # no re-evaluation: the order's decision governs the payment


async def test_the_order_mode_status_matches_the_stateless_route(api):
    """Same tier, same answer: an order and the built-in scenario of that tier get the same status and lifecycle."""
    for tier in ("LOW", "MEDIUM", "HIGH"):
        order = await create(api, tier)
        stateless = await api.post("/initiate-payment", json={"scenario": f"{tier.lower()}_risk"})
        r = await api.post("/initiate-payment", json={"order_id": order["order_id"]})
        assert r.json()["status"] == stateless.json()["status"]
        assert r.json()["lifecycle"] == stateless.json()["lifecycle"]


async def test_initiate_payment_unknown_order_is_404(api):
    r = await api.post("/initiate-payment", json={"order_id": "11111111-1111-1111-1111-111111111111"})
    assert r.status_code == 404 and await count("payments") == 0


async def test_initiate_payment_twice_is_a_409_and_writes_nothing_more(api):
    order = await create(api, "MEDIUM")
    assert (await api.post("/initiate-payment", json={"order_id": order["order_id"]})).status_code == 200
    r = await api.post("/initiate-payment", json={"order_id": order["order_id"]})
    assert r.status_code == 409
    assert (await count("payments"), await count("verifications")) == (1, 1)


async def test_concurrent_initiations_produce_one_payment(api):
    """The order row is locked FOR UPDATE, so of two simultaneous calls exactly one wins."""
    order = await create(api, "HIGH")
    rs = await asyncio.gather(*[api.post("/initiate-payment", json={"order_id": order["order_id"]}) for _ in range(4)])
    assert sorted(r.status_code for r in rs) == [200, 409, 409, 409]
    assert (await count("payments"), await count("verifications")) == (1, 1)


async def test_malformed_order_id_is_a_422(api):
    for route in ("/initiate-payment", "/verify", "/settle"):
        assert (await api.post(route, json={"order_id": "not-a-uuid"})).status_code == 422


# ─── POST /verify with order_id ──────────────────────────────────────────────────────────────────


async def started(api, tier="MEDIUM"):
    order = await create(api, tier)
    assert (await api.post("/initiate-payment", json={"order_id": order["order_id"]})).status_code == 200
    return order["order_id"]


@pytest.mark.parametrize(
    "toggles,expected",
    [({}, "SUCCESS"), ({"passed": True}, "SUCCESS"), ({"passed": False}, "FRAUD"), ({"inconsistent": True}, "INCONSISTENT"),
     ({"passed": False, "inconsistent": True}, "INCONSISTENT")],
)
async def test_verify_completes_the_pending_verification(api, toggles, expected):
    order_id = await started(api, "HIGH")
    r = await api.post("/verify", json={"order_id": order_id, **toggles})
    assert r.status_code == 200 and r.json()["result"] == expected and r.json()["order_id"] == order_id
    [v] = await fetch("select * from verifications")  # the PENDING row was completed, not joined by a second one
    assert (v["result"], v["type"]) == (expected, "MANDATORY_VIDEO") and v["completed_at"] is not None
    assert str(v["verification_id"]) == r.json()["verification_id"]


async def test_a_second_verify_is_a_retry_and_adds_a_row(api):
    order_id = await started(api, "HIGH")
    await api.post("/verify", json={"order_id": order_id, "inconsistent": True})
    await api.post("/verify", json={"order_id": order_id, "passed": True})
    rows = await fetch("select result, type from verifications order by created_at, requested_at")
    assert sorted(r["result"] for r in rows) == ["INCONSISTENT", "SUCCESS"] and {r["type"] for r in rows} == {"MANDATORY_VIDEO"}


async def test_verify_low_order_after_instant_capture(api):
    order_id = await started(api, "LOW")  # COMPLETED already; its passive verification is still PENDING
    r = await api.post("/verify", json={"order_id": order_id})
    assert r.status_code == 200 and (await fetch("select type, result from verifications")) == [{"type": "PASSIVE", "result": "SUCCESS"}]


async def test_verify_guards(api):
    assert (await api.post("/verify", json={"order_id": "11111111-1111-1111-1111-111111111111"})).status_code == 404
    order = await create(api, "MEDIUM")
    assert (await api.post("/verify", json={"order_id": order["order_id"]})).status_code == 409  # no payment yet
    await api.post("/initiate-payment", json={"order_id": order["order_id"]})
    await api.post("/settle", json={"order_id": order["order_id"], "action": "cancel"})
    assert (await api.post("/verify", json={"order_id": order["order_id"]})).status_code == 409  # cancelled
    assert await count("verifications") == 1


# ─── POST /settle with order_id ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tier,action,payment_status,order_status",
    [("MEDIUM", "capture", "CAPTURED", "COMPLETED"), ("MEDIUM", "cancel", "CANCELLED", "CANCELLED"),
     ("HIGH", "release", "RELEASED", "COMPLETED"), ("HIGH", "cancel", "CANCELLED", "CANCELLED")],
)
async def test_settle_moves_the_payment_and_the_order(api, tier, action, payment_status, order_status):
    order_id = await started(api, tier)
    if action != "cancel":  # capture / release pay the seller, so they need a SUCCESS verification (cancel does not)
        assert (await api.post("/verify", json={"order_id": order_id})).status_code == 200
    r = await api.post("/settle", json={"order_id": order_id, "action": action})
    assert r.status_code == 200 and r.json()["status"] == payment_status and r.json()["order_id"] == order_id
    [p] = await fetch("select * from payments")
    assert (p["status"], p["triggered_by"]) == (payment_status, "MANUAL") and p["settled_at"] is not None
    assert str(p["payment_id"]) == r.json()["payment_id"]
    assert (await fetch("select status from orders"))[0]["status"] == order_status


@pytest.mark.parametrize(
    "tier,action",
    [("MEDIUM", "release"), ("HIGH", "capture"), ("LOW", "capture"), ("LOW", "cancel")],
    ids=["release-an-authorization", "capture-a-wallet-hold", "capture-an-instant-capture", "cancel-a-captured-payment"],
)
async def test_illegal_settlements_are_409_and_change_nothing(api, tier, action):
    order_id = await started(api, tier)
    before = await fetch("select status, triggered_by, settled_at from payments")
    assert (await api.post("/settle", json={"order_id": order_id, "action": action})).status_code == 409
    assert await fetch("select status, triggered_by, settled_at from payments") == before


async def test_settling_twice_is_a_409(api):
    order_id = await started(api, "MEDIUM")
    await api.post("/verify", json={"order_id": order_id})
    assert (await api.post("/settle", json={"order_id": order_id, "action": "capture"})).status_code == 200
    assert (await api.post("/settle", json={"order_id": order_id, "action": "cancel"})).status_code == 409
    assert (await fetch("select status from payments"))[0]["status"] == "CAPTURED"


# ─── /settle with order_id enforces verification-before-capture/release, exactly like /v1 ────────


@pytest.mark.parametrize("tier,action", [("MEDIUM", "capture"), ("HIGH", "release")])
@pytest.mark.parametrize("latest", [None, "FRAUD", "INCONSISTENT"], ids=["never-verified", "fraud", "inconsistent"])
async def test_legacy_settle_refuses_to_pay_out_without_a_successful_verification(api, tier, action, latest):
    order_id = await started(api, tier)
    if latest:
        toggles = {"FRAUD": {"passed": False}, "INCONSISTENT": {"inconsistent": True}}[latest]
        await api.post("/verify", json={"order_id": order_id, **toggles})
    before = await fetch("select status, triggered_by, settled_at from payments")
    r = await api.post("/settle", json={"order_id": order_id, "action": action})
    assert r.status_code == 409
    assert r.json() == {"detail": f"cannot {action}: the latest verification is {latest or 'PENDING'}; SUCCESS is required"}
    assert await fetch("select status, triggered_by, settled_at from payments") == before  # nothing moved
    assert (await fetch("select status from orders")) == [{"status": "ACTIVE"}]


@pytest.mark.parametrize("tier", ["MEDIUM", "HIGH"])
async def test_legacy_settle_cancel_is_never_gated(api, tier):
    order_id = await started(api, tier)
    await api.post("/verify", json={"order_id": order_id, "passed": False})  # FRAUD
    r = await api.post("/settle", json={"order_id": order_id, "action": "cancel"})
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"


async def test_a_later_verification_lifts_or_reinstates_the_block(api):
    order_id = await started(api, "MEDIUM")
    await api.post("/verify", json={"order_id": order_id, "passed": False})
    assert (await api.post("/settle", json={"order_id": order_id, "action": "capture"})).status_code == 409
    await api.post("/verify", json={"order_id": order_id})  # a retry that passed
    assert (await api.post("/settle", json={"order_id": order_id, "action": "capture"})).status_code == 200


async def test_the_state_rule_is_still_reported_before_the_verification_rule(api):
    order_id = await started(api, "MEDIUM")  # AUTHORIZED, verification PENDING
    r = await api.post("/settle", json={"order_id": order_id, "action": "release"})
    assert r.status_code == 409 and r.json() == {"detail": "cannot release a payment that is AUTHORIZED"}


async def test_the_stateless_settle_is_unaffected(api):
    """No order_id: still the demo toggle. There is no verification to consult."""
    assert (await api.post("/settle", json={"action": "capture"})).json() == {"status": "CAPTURED"}
    assert (await api.post("/settle", json={"action": "release"})).json() == {"status": "RELEASED"}


async def test_settle_guards(api):
    assert (await api.post("/settle", json={"order_id": "11111111-1111-1111-1111-111111111111"})).status_code == 404
    order = await create(api, "MEDIUM")
    assert (await api.post("/settle", json={"order_id": order["order_id"]})).status_code == 409  # no payment yet
    # an invalid action is rejected before the database is consulted, with the stateless route's message
    r = await api.post("/settle", json={"order_id": order["order_id"], "action": "refund"})
    assert r.status_code == 400 and r.json() == {"detail": "action must be capture | release | cancel"}


async def test_full_lifecycle_of_a_high_risk_order(api):
    order = await create(api, "HIGH")
    oid = order["order_id"]
    await api.post("/initiate-payment", json={"order_id": oid})
    await api.post("/verify", json={"order_id": oid, "passed": True})
    await api.post("/settle", json={"order_id": oid, "action": "release"})
    [o] = await fetch("select status, risk_tier from orders")
    [p] = await fetch("select status, route, triggered_by from payments")
    [v] = await fetch("select type, result from verifications")
    assert (o["status"], o["risk_tier"]) == ("COMPLETED", "HIGH")
    assert (p["status"], p["route"], p["triggered_by"]) == ("RELEASED", "WALLET_HOLD", "MANUAL")
    assert (v["type"], v["result"]) == ("MANDATORY_VIDEO", "SUCCESS")
    assert await count("risk_decision_log") == 1
