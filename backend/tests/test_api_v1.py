"""Phase 5a: the versioned public API (/v1) against a real PostgreSQL — auth, the order lifecycle, the
verification-before-capture rule, and how it differs from the legacy demo routes."""

import uuid

import pytest

import db
from cases import TRANSACTIONS
from pg_fixtures import fetch, mint_api_key

TIER_FIXTURE = {"LOW": "low_risk", "MEDIUM": "medium_risk", "HIGH": "high_risk"}
GHOST = "11111111-1111-1111-1111-111111111111"


def order_body(tier="MEDIUM", **overrides):
    return {"buyer_id": "buyer-1", "seller_id": "seller-9", **TRANSACTIONS[TIER_FIXTURE[tier]], **overrides}


def idem(key=None):
    return {"Idempotency-Key": key or f"k-{uuid.uuid4()}"}


async def create(v1, tier="MEDIUM", **overrides):
    r = await v1.post("/v1/orders", json=order_body(tier, **overrides), headers=idem())
    assert r.status_code == 201, r.text
    return r.json()["order_id"]


async def started(v1, tier="MEDIUM"):
    order_id = await create(v1, tier)
    r = await v1.post(f"/v1/orders/{order_id}/payment")
    assert r.status_code == 201, r.text
    return order_id


async def settle(v1, order_id, action, key=None):
    return await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": action}, headers=idem(key))


async def verify(v1, order_id, result, **extra):
    return await v1.post(f"/v1/orders/{order_id}/verification", json={"result": result, **extra})


# ─── authentication ──────────────────────────────────────────────────────────────────────────────

V1_ROUTES = [
    ("POST", "/v1/risk/evaluate", {"json": TRANSACTIONS["low_risk"]}),
    ("POST", "/v1/orders", {"json": order_body(), "headers": idem()}),
    ("GET", f"/v1/orders/{GHOST}", {}),
    ("POST", f"/v1/orders/{GHOST}/payment", {}),
    ("POST", f"/v1/orders/{GHOST}/verification", {"json": {"result": "SUCCESS"}}),
    ("POST", f"/v1/orders/{GHOST}/settlement", {"json": {"action": "capture"}, "headers": idem()}),
]


@pytest.mark.parametrize("method,path,kwargs", V1_ROUTES, ids=[f"{m} {p}" for m, p, _ in V1_ROUTES])
async def test_every_v1_route_requires_a_key(api, method, path, kwargs):
    r = await api.request(method, path, **kwargs)
    assert r.status_code == 401 and r.json() == {"detail": "Missing X-API-Key header"}
    assert r.headers["www-authenticate"] == "ApiKey"
    assert await fetch("select count(*) as n from orders") == [{"n": 0}]


async def test_an_unknown_key_is_a_401(api):
    r = await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers={"X-API-Key": "tos_not-a-real-key"})
    assert r.status_code == 401 and r.json() == {"detail": "Invalid or revoked API key"}


async def test_a_valid_key_is_accepted(v1):
    assert (await v1.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"])).status_code == 200


async def test_a_revoked_key_is_refused_and_says_the_same_as_an_unknown_one(api, key, monkeypatch):
    monkeypatch.setenv("API_KEY_CACHE_TTL", "0")
    headers = {"X-API-Key": key}
    assert (await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers=headers)).status_code == 200
    await fetch_exec("update api_keys set revoked_at = now()")
    r = await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers=headers)
    assert r.status_code == 401 and r.json() == {"detail": "Invalid or revoked API key"}


async def test_a_verified_key_is_cached_so_revocation_takes_up_to_the_ttl(api, key):
    """Documented trade-off: API_KEY_CACHE_TTL (30 s by default) of revocation lag buys DB-outage tolerance."""
    from services import auth

    headers = {"X-API-Key": key}
    assert (await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers=headers)).status_code == 200
    await fetch_exec("update api_keys set revoked_at = now()")
    assert (await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers=headers)).status_code == 200  # still cached
    auth.clear_cache()
    assert (await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers=headers)).status_code == 401


async def test_a_database_outage_fails_closed_for_unknown_keys_but_not_for_cached_ones(api, key):
    await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers={"X-API-Key": key})  # now cached
    await db.dispose()
    db.configure("postgresql://postgres@127.0.0.1:9/trustos_dead")  # nothing listens there
    ok = await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers={"X-API-Key": key})
    assert ok.status_code == 200
    unknown = await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers={"X-API-Key": "tos_other"})
    assert unknown.status_code == 503


def test_v1_without_persistence_is_a_503_not_an_open_door(client):
    """Keys live in the database, so with DATABASE_URL unset a keyed request cannot be verified."""
    r = client.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers={"X-API-Key": "tos_anything"})
    assert r.status_code == 503 and "DATABASE_URL" in r.json()["detail"]
    assert client.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"]).status_code == 401  # no key: rejected before that


async def test_legacy_routes_still_need_no_key(api):
    assert (await api.post("/decision/evaluate", json=TRANSACTIONS["low_risk"])).status_code == 200
    r = await api.post("/orders", json=order_body())
    assert r.status_code == 201


async def fetch_exec(sql):
    import sqlalchemy as sa

    async with db.transaction() as conn:
        await conn.execute(sa.text(sql))


# ─── POST /v1/risk/evaluate ──────────────────────────────────────────────────────────────────────


async def test_risk_evaluate_is_the_decision_evaluate_handler(v1):
    for fixture in ("low_risk", "medium_risk", "high_risk"):
        legacy = await v1.post("/decision/evaluate", json=TRANSACTIONS[fixture])
        new = await v1.post("/v1/risk/evaluate", json=TRANSACTIONS[fixture])
        assert new.status_code == 200 and new.text == legacy.text
    rows = await fetch("select source, order_id from risk_decision_log")
    assert len(rows) == 6 and {r["source"] for r in rows} == {"decision_evaluate"} and {r["order_id"] for r in rows} == {None}


async def test_risk_evaluate_validates_its_body(v1):
    assert (await v1.post("/v1/risk/evaluate", json={"order_value": -1})).status_code == 422


# ─── POST /v1/orders ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tier", ["LOW", "MEDIUM", "HIGH"])
async def test_create_order_matches_the_legacy_response(v1, tier):
    r = await v1.post("/v1/orders", json=order_body(tier), headers=idem())
    assert r.status_code == 201
    legacy = await v1.post("/orders", json=order_body(tier))
    strip = lambda b: {k: v for k, v in b.items() if k not in ("order_id", "created_at")}  # noqa: E731
    assert strip(r.json()) == strip(legacy.json())
    assert r.json()["status"] == "CREATED" and r.json()["evaluation"]["decision"]["risk_classification"] == tier
    [log] = await fetch("select source, order_id from risk_decision_log where source = 'orders_create' order by id limit 1")
    assert str(log["order_id"]) == r.json()["order_id"]


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": ""}, {"Idempotency-Key": "has space"}, {"Idempotency-Key": "x" * 256}])
async def test_a_missing_or_malformed_idempotency_key_is_a_400_and_writes_nothing(v1, headers):
    r = await v1.post("/v1/orders", json=order_body(), headers=headers)
    assert r.status_code == 400 and "Idempotency-Key" in r.json()["detail"]
    assert await fetch("select count(*) as n from orders") == [{"n": 0}]


async def test_a_255_character_key_is_accepted(v1):
    assert (await v1.post("/v1/orders", json=order_body(), headers=idem("k" * 255))).status_code == 201


async def test_invalid_orders_are_422(v1):
    for patch in ({"buyer_id": ""}, {"order_value": 0}, {"order_value": 1e11}):
        assert (await v1.post("/v1/orders", json=order_body(**patch), headers=idem())).status_code == 422
    assert await fetch("select count(*) as n from orders") == [{"n": 0}]


# ─── GET /v1/orders/{id} ─────────────────────────────────────────────────────────────────────────


async def test_get_order_follows_the_lifecycle(v1):
    order_id = await create(v1, "MEDIUM")
    r = await v1.get(f"/v1/orders/{order_id}")
    body = r.json()
    assert r.status_code == 200 and (body["status"], body["risk_tier"], body["amount"], body["currency"]) == ("CREATED", "MEDIUM", 1500.0, "INR")
    assert body["payment"] is None and body["verifications"] == [] and body["buyer_id"] == "buyer-1"

    await v1.post(f"/v1/orders/{order_id}/payment")
    body = (await v1.get(f"/v1/orders/{order_id}")).json()
    assert body["status"] == "ACTIVE" and body["payment"]["status"] == "AUTHORIZED" and body["payment"]["route"] == "AUTHORIZE_ONLY"
    assert [(v["type"], v["result"]) for v in body["verifications"]] == [("USER_CONFIRMATION", "PENDING")]

    await verify(v1, order_id, "INCONSISTENT")
    await verify(v1, order_id, "SUCCESS")  # a retry is a further row
    body = (await v1.get(f"/v1/orders/{order_id}")).json()
    assert [v["result"] for v in body["verifications"]] == ["INCONSISTENT", "SUCCESS"]


async def test_get_unknown_or_malformed_order(v1):
    assert (await v1.get(f"/v1/orders/{GHOST}")).status_code == 404
    assert (await v1.get("/v1/orders/not-a-uuid")).status_code == 422


# ─── payment ─────────────────────────────────────────────────────────────────────────────────────

EXPECTED = {  # tier: (payment status, route, order status, verification type)
    "LOW": ("CAPTURED", "DIRECT_CAPTURE", "COMPLETED", "PASSIVE"),
    "MEDIUM": ("AUTHORIZED", "AUTHORIZE_ONLY", "ACTIVE", "USER_CONFIRMATION"),
    "HIGH": ("HELD", "WALLET_HOLD", "ACTIVE", "MANDATORY_VIDEO"),
}


@pytest.mark.parametrize("tier", ["LOW", "MEDIUM", "HIGH"])
async def test_start_payment(v1, tier):
    order_id = await create(v1, tier)
    r = await v1.post(f"/v1/orders/{order_id}/payment")
    status, route, order_status, vtype = EXPECTED[tier]
    body = r.json()
    assert r.status_code == 201 and body["order_id"] == order_id and body["order_status"] == order_status
    assert (body["payment"]["status"], body["payment"]["route"], body["payment"]["triggered_by"]) == (status, route, "AUTO")
    assert (body["verification"]["type"], body["verification"]["result"], body["verification"]["completed_at"]) == (vtype, "PENDING", None)
    assert (body["payment"]["settled_at"] is not None) == (status == "CAPTURED")
    assert body["payment"]["amount"] == TRANSACTIONS[TIER_FIXTURE[tier]]["order_value"]
    assert (await fetch("select count(*) as n from risk_decision_log where order_id is not null"))[0]["n"] == 1  # no re-evaluation


async def test_start_payment_guards(v1):
    assert (await v1.post(f"/v1/orders/{GHOST}/payment")).status_code == 404
    order_id = await create(v1)
    assert (await v1.post(f"/v1/orders/{order_id}/payment")).status_code == 201
    assert (await v1.post(f"/v1/orders/{order_id}/payment")).status_code == 409
    assert (await fetch("select count(*) as n from payments")) == [{"n": 1}]


# ─── verification ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("result", ["SUCCESS", "FRAUD", "INCONSISTENT"])
async def test_verification_completes_the_pending_row(v1, result):
    order_id = await started(v1, "HIGH")
    r = await verify(v1, order_id, result, details={"video": "s3://bucket/clip.mp4", "score": 0.93})
    body = r.json()
    assert r.status_code == 200 and body["order_id"] == order_id and body["order_status"] == "ACTIVE"
    assert (body["verification"]["result"], body["verification"]["type"]) == (result, "MANDATORY_VIDEO")
    assert body["verification"]["details"] == {"video": "s3://bucket/clip.mp4", "score": 0.93}
    assert body["verification"]["completed_at"] is not None
    assert (await fetch("select count(*) as n from verifications")) == [{"n": 1}]


@pytest.mark.parametrize("payload", [{"result": "PENDING"}, {"result": "ISSUE"}, {"result": "success"}, {}, {"result": "SUCCESS", "details": "x"}])
async def test_verification_rejects_bad_bodies(v1, payload):
    order_id = await started(v1)
    assert (await v1.post(f"/v1/orders/{order_id}/verification", json=payload)).status_code == 422


async def test_verification_details_are_size_limited(v1):
    order_id = await started(v1)
    assert (await verify(v1, order_id, "SUCCESS", details={"blob": "x" * 20_000})).status_code == 422


async def test_verification_guards(v1):
    assert (await verify(v1, GHOST, "SUCCESS")).status_code == 404
    order_id = await create(v1)
    assert (await verify(v1, order_id, "SUCCESS")).status_code == 409  # no payment yet
    await v1.post(f"/v1/orders/{order_id}/payment")
    assert (await settle(v1, order_id, "cancel")).status_code == 200
    assert (await verify(v1, order_id, "SUCCESS")).status_code == 409  # cancelled


# ─── settlement, and the verification-before-capture rule ────────────────────────────────────────


async def test_capture_after_a_successful_verification(v1):
    order_id = await started(v1, "MEDIUM")
    await verify(v1, order_id, "SUCCESS")
    r = await settle(v1, order_id, "capture")
    body = r.json()
    assert r.status_code == 200 and body["order_status"] == "COMPLETED"
    assert (body["payment"]["status"], body["payment"]["triggered_by"]) == ("CAPTURED", "MANUAL") and body["payment"]["settled_at"]
    assert (await v1.get(f"/v1/orders/{order_id}")).json()["status"] == "COMPLETED"


@pytest.mark.parametrize("latest", [None, "FRAUD", "INCONSISTENT"], ids=["never-verified", "fraud", "inconsistent"])
async def test_capture_is_refused_unless_the_latest_verification_succeeded(v1, latest):
    order_id = await started(v1, "MEDIUM")
    if latest:
        await verify(v1, order_id, latest)
    r = await settle(v1, order_id, "capture")
    seen = latest or "PENDING"
    assert r.status_code == 409
    assert r.json() == {"detail": f"cannot capture: the latest verification is {seen}; SUCCESS is required"}
    [p] = await fetch("select status, triggered_by, settled_at from payments")
    assert (p["status"], p["triggered_by"], p["settled_at"]) == ("AUTHORIZED", "AUTO", None)  # untouched
    assert (await fetch("select status from orders")) == [{"status": "ACTIVE"}]


async def test_the_LATEST_verification_decides(v1):
    a = await started(v1, "MEDIUM")
    await verify(v1, a, "INCONSISTENT")
    await verify(v1, a, "SUCCESS")  # a retry that passed
    assert (await settle(v1, a, "capture")).status_code == 200

    b = await started(v1, "MEDIUM")
    await verify(v1, b, "SUCCESS")
    await verify(v1, b, "FRAUD")  # ... and one that later failed
    assert (await settle(v1, b, "capture")).status_code == 409


@pytest.mark.parametrize("tier,action", [("MEDIUM", "capture"), ("HIGH", "release"), ("MEDIUM", "cancel"), ("HIGH", "cancel")])
@pytest.mark.parametrize("latest", [None, "SUCCESS", "FRAUD", "INCONSISTENT"], ids=["pending", "success", "fraud", "inconsistent"])
async def test_legacy_settle_and_v1_settlement_give_the_same_answer(v1, tier, action, latest):
    """Verification-before-capture used to be a /v1-only rule (legacy /settle would pay out a FRAUD order). Both routes
    now share order_service.settle_payment: for the same order state they answer alike."""
    async def prepared():
        order_id = await started(v1, tier)
        if latest:
            await verify(v1, order_id, latest)
        return order_id

    legacy_order, new_order = await prepared(), await prepared()
    legacy = await v1.post("/settle", json={"order_id": legacy_order, "action": action})
    new = await settle(v1, new_order, action)
    assert legacy.status_code == new.status_code
    if new.status_code == 409:
        assert legacy.json() == new.json()
    else:
        assert legacy.json()["status"] == new.json()["payment"]["status"]


@pytest.mark.parametrize("latest", [None, "FRAUD", "INCONSISTENT"], ids=["never-verified", "fraud", "inconsistent"])
async def test_release_of_a_wallet_hold_is_gated_like_a_capture(v1, latest):
    """Releasing a HIGH hold pays the seller just as a capture does, so it needs the same SUCCESS."""
    order_id = await started(v1, "HIGH")
    if latest:
        await verify(v1, order_id, latest)
    r = await settle(v1, order_id, "release")
    seen = latest or "PENDING"
    assert r.status_code == 409
    assert r.json() == {"detail": f"cannot release: the latest verification is {seen}; SUCCESS is required"}
    [p] = await fetch("select status, triggered_by, settled_at from payments")
    assert (p["status"], p["triggered_by"], p["settled_at"]) == ("HELD", "AUTO", None)  # still held
    assert (await fetch("select status from orders")) == [{"status": "ACTIVE"}]


async def test_release_after_a_successful_verification(v1):
    order_id = await started(v1, "HIGH")
    await verify(v1, order_id, "SUCCESS")
    r = await settle(v1, order_id, "release")
    assert r.status_code == 200 and r.json()["payment"]["status"] == "RELEASED" and r.json()["order_status"] == "COMPLETED"


async def test_the_latest_verification_decides_for_release_too(v1):
    order_id = await started(v1, "HIGH")
    await verify(v1, order_id, "SUCCESS")
    await verify(v1, order_id, "FRAUD")  # a later check failed
    assert (await settle(v1, order_id, "release")).status_code == 409


async def test_cancel_is_never_gated_on_the_verification(v1):
    """Only the settlements that pay the seller (capture, release) are gated: cancelling returns the money, so
    it must work whatever the verification says, including for a wallet hold that failed verification."""
    for tier in ("MEDIUM", "HIGH"):
        pending = await started(v1, tier)
        assert (await settle(v1, pending, "cancel")).status_code == 200
        failed = await started(v1, tier)
        await verify(v1, failed, "FRAUD")
        r = await settle(v1, failed, "cancel")
        assert r.status_code == 200 and r.json()["payment"]["status"] == "CANCELLED" and r.json()["order_status"] == "CANCELLED"


def test_the_gated_settlements_are_exactly_capture_and_release():
    from services import order_flow

    assert order_flow.SETTLEMENT_REQUIRES_VERIFIED == frozenset({"CAPTURED", "RELEASED"})


@pytest.mark.parametrize(
    "tier,action,message",
    [("MEDIUM", "release", "cannot release a payment that is AUTHORIZED"), ("HIGH", "capture", "cannot capture a payment that is HELD"),
     ("LOW", "capture", "cannot capture a payment that is CAPTURED"), ("LOW", "cancel", "cannot cancel a payment that is CAPTURED")],
)
async def test_illegal_settlements_are_409_with_the_legacy_messages(v1, tier, action, message):
    order_id = await started(v1, tier)
    r = await settle(v1, order_id, action)
    assert r.status_code == 409 and r.json() == {"detail": message}  # the state rule is reported before the verification rule


async def test_settlement_guards(v1):
    assert (await settle(v1, GHOST, "capture")).status_code == 404
    order_id = await create(v1)
    assert (await settle(v1, order_id, "capture")).status_code == 409  # no payment yet
    await v1.post(f"/v1/orders/{order_id}/payment")
    for bad in ({"action": "refund"}, {"action": "Capture"}, {}):
        assert (await v1.post(f"/v1/orders/{order_id}/settlement", json=bad, headers=idem())).status_code == 422


async def test_settling_twice_is_a_409_without_an_idempotency_replay(v1):
    order_id = await started(v1)
    await verify(v1, order_id, "SUCCESS")
    assert (await settle(v1, order_id, "capture")).status_code == 200
    assert (await settle(v1, order_id, "capture")).status_code == 409  # a NEW key: this is a second, different attempt


async def test_full_lifecycle(v1):
    order_id = await create(v1, "HIGH")
    assert (await v1.post(f"/v1/orders/{order_id}/payment")).json()["payment"]["status"] == "HELD"
    await verify(v1, order_id, "SUCCESS")
    assert (await settle(v1, order_id, "release")).json()["order_status"] == "COMPLETED"
    body = (await v1.get(f"/v1/orders/{order_id}")).json()
    assert (body["status"], body["payment"]["status"], body["verifications"][0]["result"]) == ("COMPLETED", "RELEASED", "SUCCESS")


# ─── the api_keys / idempotency_keys tables carry their own rules ────────────────────────────────


async def test_key_and_idempotency_table_constraints(pg):
    import sqlalchemy as sa
    from sqlalchemy.exc import IntegrityError

    good_hash = "a" * 64
    ok_row = dict(scope="s", key="k", request_hash="h", response_status=201, response_body="{}")
    bad_api_keys = [dict(key_hash="short", label="x"), dict(key_hash="A" * 64, label="x"), dict(key_hash=good_hash, label="")]
    for row in bad_api_keys:
        with pytest.raises(IntegrityError):
            async with db.transaction() as conn:
                await conn.execute(sa.text("insert into api_keys (key_hash, label) values (:key_hash, :label)"), row)

    async def insert_idem(**over):
        row = {**ok_row, **over}
        async with db.transaction() as conn:
            await conn.execute(
                sa.text(
                    "insert into idempotency_keys (scope, key, request_hash, response_status, response_body, expires_at)"
                    " values (:scope, :key, :request_hash, :response_status, cast(:response_body as json), now() + interval '1 hour')"
                ),
                row,
            )

    for bad in ({"response_status": 409}, {"response_status": 199}, {"key": ""}, {"key": "x" * 256}):
        with pytest.raises(IntegrityError):
            await insert_idem(**bad)
    await insert_idem()
    with pytest.raises(IntegrityError):  # (scope, key) is the primary key
        await insert_idem()
    async with db.transaction() as conn:
        await conn.execute(sa.text("insert into api_keys (key_hash, label) values (:h, 'a'), (:h2, 'a')"), {"h": good_hash, "h2": "b" * 64})  # labels may repeat
    with pytest.raises(IntegrityError):  # expires_at must be after created_at
        async with db.transaction() as conn:
            await conn.execute(sa.text(
                "insert into idempotency_keys (scope, key, request_hash, response_status, response_body, expires_at)"
                " values ('s2', 'k', 'h', 200, '{}', now() - interval '1 second')"))


async def test_two_callers_are_two_scopes(v1, pg):
    other = await mint_api_key("someone-else")
    a = await v1.post("/v1/orders", json=order_body(), headers=idem("shared-key"))
    b = await v1.post("/v1/orders", json=order_body(), headers={**idem("shared-key"), "X-API-Key": other})
    assert (a.status_code, b.status_code) == (201, 201) and a.json()["order_id"] != b.json()["order_id"]
    assert "idempotent-replayed" not in b.headers
