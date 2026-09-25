"""Follow-up to Phase 5a: the legacy /initiate-payment, /verify and /settle need an X-API-Key WHEN they are given an
order_id. Without one (the stateless demo the frontend uses) they stay fully open. POST /orders is not order_id-
bearing and stays open too."""

import pytest

from cases import TRANSACTIONS
from pg_fixtures import fetch
from test_api_v1 import order_body

GHOST = "11111111-1111-1111-1111-111111111111"
ROUTES = ["/initiate-payment", "/verify", "/settle"]
MISSING = {"detail": "Missing X-API-Key header"}
INVALID = {"detail": "Invalid or revoked API key"}


async def make_order(api, tier="MEDIUM"):
    """/orders is open, so this needs no key."""
    r = await api.post("/orders", json=order_body(tier))
    assert r.status_code == 201
    return r.json()["order_id"]


@pytest.mark.parametrize("path", ROUTES)
async def test_order_mode_without_a_key_is_a_401(api, path):
    r = await api.post(path, json={"order_id": GHOST})
    assert r.status_code == 401 and r.json() == MISSING and r.headers["www-authenticate"] == "ApiKey"


@pytest.mark.parametrize("path", ROUTES)
async def test_order_mode_with_a_bad_key_is_a_401(api, path):
    r = await api.post(path, json={"order_id": GHOST}, headers={"X-API-Key": "tos_nope"})
    assert r.status_code == 401 and r.json() == INVALID


@pytest.mark.parametrize("path", ROUTES)
async def test_a_revoked_key_is_refused_on_legacy_order_mode(api, key, path, monkeypatch):
    monkeypatch.setenv("API_KEY_CACHE_TTL", "0")
    headers = {"X-API-Key": key}
    assert (await api.post(path, json={"order_id": GHOST}, headers=headers)).status_code == 404  # authenticated: reaches the order lookup
    import db
    import sqlalchemy as sa

    async with db.transaction() as conn:
        await conn.execute(sa.text("update api_keys set revoked_at = now()"))
    assert (await api.post(path, json={"order_id": GHOST}, headers=headers)).status_code == 401


async def test_an_unauthenticated_caller_cannot_move_an_existing_order(api, key):
    """The point of the follow-up: the order exists (created openly), but nothing can be done to it anonymously."""
    order_id = await make_order(api, "MEDIUM")
    for path, body in (("/initiate-payment", {}), ("/verify", {}), ("/settle", {"action": "capture"})):
        assert (await api.post(path, json={"order_id": order_id, **body})).status_code == 401
    assert await fetch("select count(*) as n from payments") == [{"n": 0}]
    assert await fetch("select count(*) as n from verifications") == [{"n": 0}]
    assert (await fetch("select status from orders")) == [{"status": "CREATED"}]
    # with the key the very same calls work
    headers = {"X-API-Key": key}
    assert (await api.post("/initiate-payment", json={"order_id": order_id}, headers=headers)).status_code == 200
    assert (await api.post("/verify", json={"order_id": order_id}, headers=headers)).status_code == 200
    assert (await api.post("/settle", json={"order_id": order_id, "action": "capture"}, headers=headers)).status_code == 200


async def test_authentication_comes_before_request_checks_that_would_leak_anything(api):
    # an invalid action with an order_id is a 401 for an anonymous caller, not the 400 the stateless route gives
    r = await api.post("/settle", json={"order_id": GHOST, "action": "refund"})
    assert r.status_code == 401
    assert (await api.post("/settle", json={"action": "refund"})).status_code == 400  # stateless: unchanged


async def test_a_malformed_order_id_is_still_a_422_before_authentication(api):
    """Request validation runs before the handler (and so before the key check); it reveals nothing about any order."""
    for path in ROUTES:
        assert (await api.post(path, json={"order_id": "not-a-uuid"})).status_code == 422


# ─── the stateless demo stays open ───────────────────────────────────────────────────────────────


async def test_the_stateless_demo_needs_no_key(api):
    assert (await api.post("/initiate-payment", json={"scenario": "high_risk"})).json()["status"] == "HELD"
    assert (await api.post("/verify", json={"passed": False})).json() == {"result": "FRAUD"}
    assert (await api.post("/settle", json={"action": "release"})).json() == {"status": "RELEASED"}
    assert (await api.post("/initiate-payment", json={})).status_code == 200  # no body fields at all


@pytest.mark.parametrize("path", ROUTES)
async def test_an_explicit_null_order_id_is_the_stateless_demo(api, path):
    assert (await api.post(path, json={"order_id": None})).status_code == 200


@pytest.mark.parametrize("path", ROUTES)
async def test_the_stateless_demo_ignores_a_key_it_does_not_need(api, path):
    """A stale or wrong key must not break the demo frontend."""
    r = await api.post(path, json={}, headers={"X-API-Key": "tos_whatever"})
    assert r.status_code == 200


def test_the_stateless_demo_needs_no_key_or_database(client):
    """(No DATABASE_URL at all, as the frontend demo runs.)"""
    assert client.post("/initiate-payment", json={"scenario": "low_risk"}).json()["status"] == "CAPTURED"
    assert client.post("/verify", json={}).json() == {"result": "SUCCESS"}
    assert client.post("/settle", json={}).json() == {"status": "CAPTURED"}


async def test_the_stateless_demo_does_not_touch_the_key_table(api, monkeypatch):
    from services import auth

    async def boom(*a, **k):
        raise AssertionError("authentication ran for a stateless call")

    monkeypatch.setattr(auth, "require_api_key", boom)
    assert (await api.post("/settle", json={})).status_code == 200
    assert (await api.post("/decision/evaluate", json=TRANSACTIONS["low_risk"])).status_code == 200


# ─── POST /orders is not order_id-bearing ────────────────────────────────────────────────────────


async def test_creating_an_order_through_the_legacy_route_is_still_open(api):
    r = await api.post("/orders", json=order_body())
    assert r.status_code == 201 and (await fetch("select count(*) as n from orders")) == [{"n": 1}]
