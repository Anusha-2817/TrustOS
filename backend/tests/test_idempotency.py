"""Phase 5a: Idempotency-Key on POST /v1/orders and POST /v1/orders/{id}/settlement, against a real PostgreSQL."""

import asyncio
import json

import pytest
import sqlalchemy as sa

import db
from cases import TRANSACTIONS
from pg_fixtures import fetch, mint_api_key
from test_api_v1 import idem, order_body, started, verify

REPLAYED = "idempotent-replayed"


async def count(table):
    return (await fetch(f"select count(*) as n from {table}"))[0]["n"]


async def post_order(v1, key, body=None, **kw):
    return await v1.post("/v1/orders", json=body or order_body(), headers=idem(key), **kw)


# ─── POST /v1/orders ─────────────────────────────────────────────────────────────────────────────


async def test_a_retry_replays_the_original_response_byte_for_byte(v1):
    first = await post_order(v1, "retry-me")
    again = await post_order(v1, "retry-me")
    assert first.status_code == again.status_code == 201
    assert again.content == first.content  # identical bytes, same order_id and created_at
    assert REPLAYED not in first.headers and again.headers[REPLAYED] == "true"
    assert (await count("orders"), await count("risk_decision_log")) == (1, 1)  # nothing ran or was logged twice
    [row] = await fetch("select order_id, response_status from idempotency_keys")
    assert str(row["order_id"]) == first.json()["order_id"] and row["response_status"] == 201


async def test_formatting_and_key_order_do_not_matter_but_meaning_does(v1):
    body = order_body("MEDIUM")
    first = await post_order(v1, "canon", body)
    reordered = await v1.post(
        "/v1/orders", content=json.dumps(dict(reversed(list(body.items()))), indent=2), headers={**idem("canon"), "content-type": "application/json"}
    )
    explicit_defaults = await post_order(v1, "canon", {**body, "is_new_pair": False, "is_new_device": False})
    assert reordered.content == explicit_defaults.content == first.content
    assert await count("orders") == 1
    changed = await post_order(v1, "canon", {**body, "order_value": body["order_value"] + 1})
    assert changed.status_code == 422 and changed.json() == {"detail": "Idempotency-Key was already used with a different request"}
    assert await count("orders") == 1


async def test_a_key_is_bound_to_the_endpoint_and_the_order(v1):
    await post_order(v1, "one-key")
    order_id = await started(v1)
    r = await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "cancel"}, headers=idem("one-key"))
    assert r.status_code == 422  # used for POST /v1/orders, not this
    await verify(v1, order_id, "SUCCESS")
    assert (await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "capture"}, headers=idem("k-a"))).status_code == 200
    other = await started(v1)
    await verify(v1, other, "SUCCESS")
    assert (await v1.post(f"/v1/orders/{other}/settlement", json={"action": "capture"}, headers=idem("k-a"))).status_code == 422


async def test_callers_cannot_see_or_collide_with_each_others_keys(v1):
    other = await mint_api_key("other")
    mine = await post_order(v1, "same-string")
    theirs = await v1.post("/v1/orders", json=order_body(), headers={**idem("same-string"), "X-API-Key": other})
    assert theirs.status_code == 201 and theirs.json()["order_id"] != mine.json()["order_id"] and REPLAYED not in theirs.headers
    assert await count("orders") == 2 and await count("idempotency_keys") == 2


async def test_simultaneous_duplicates_create_exactly_one_order(v1):
    rs = await asyncio.gather(*[post_order(v1, "race") for _ in range(6)])
    assert [r.status_code for r in rs] == [201] * 6
    assert len({r.content for r in rs}) == 1  # every caller got the same answer
    assert sum(REPLAYED not in r.headers for r in rs) == 1  # one did the work, the rest replayed it
    assert (await count("orders"), await count("risk_decision_log"), await count("idempotency_keys")) == (1, 1, 1)


async def test_different_keys_are_different_orders(v1):
    a, b = await post_order(v1, "a"), await post_order(v1, "b")
    assert a.json()["order_id"] != b.json()["order_id"] and await count("orders") == 2


async def test_a_failed_creation_stores_nothing_so_the_same_key_can_be_retried(v1):
    r = await post_order(v1, "flaky", order_body(order_value=1e-9))  # rounds to 0.00: the database refuses it
    assert r.status_code == 503
    assert (await count("orders"), await count("risk_decision_log"), await count("idempotency_keys")) == (0, 0, 0)
    ok = await post_order(v1, "flaky")
    assert ok.status_code == 201 and REPLAYED not in ok.headers


async def test_a_rejected_request_does_not_consume_the_key(v1):
    assert (await post_order(v1, "typo", order_body(buyer_id=""))).status_code == 422
    assert (await post_order(v1, "typo")).status_code == 201


# ─── expiry ──────────────────────────────────────────────────────────────────────────────────────


async def test_a_key_is_kept_for_24_hours_by_default(v1):
    await post_order(v1, "ttl")
    [row] = await fetch("select extract(epoch from expires_at - created_at) as s from idempotency_keys")
    assert float(row["s"]) == 24 * 3600


async def test_the_ttl_is_configurable(v1, monkeypatch):
    monkeypatch.setenv("IDEMPOTENCY_TTL_SECONDS", "90")
    await post_order(v1, "ttl90")
    [row] = await fetch("select extract(epoch from expires_at - created_at) as s from idempotency_keys")
    assert float(row["s"]) == 90


async def expire(key):
    async with db.transaction() as conn:
        await conn.execute(
            sa.text("update idempotency_keys set created_at = now() - interval '2 hours', expires_at = now() - interval '1 hour' where key = :k"),
            {"k": key},
        )


async def test_an_expired_key_can_be_used_again(v1):
    first = await post_order(v1, "old")
    await expire("old")
    again = await post_order(v1, "old")
    assert again.status_code == 201 and REPLAYED not in again.headers and again.json()["order_id"] != first.json()["order_id"]
    assert await count("orders") == 2
    [row] = await fetch("select order_id, expires_at > now() as live from idempotency_keys")
    assert str(row["order_id"]) == again.json()["order_id"] and row["live"]  # the expired row was replaced, not duplicated
    assert (await post_order(v1, "old")).headers[REPLAYED] == "true"  # and the new one replays


async def test_a_different_request_may_reuse_an_expired_key(v1):
    await post_order(v1, "recycled")
    await expire("recycled")
    assert (await post_order(v1, "recycled", order_body(order_value=777))).status_code == 201


async def test_expired_rows_are_purged_by_the_next_write(v1):
    for i in range(3):
        await post_order(v1, f"stale-{i}")
    for i in range(3):  # (each write purges, so expire them only once all three exist)
        await expire(f"stale-{i}")
    assert await count("idempotency_keys") == 3
    await post_order(v1, "fresh")
    assert [r["key"] for r in await fetch("select key from idempotency_keys")] == ["fresh"]


# ─── POST /v1/orders/{id}/settlement ─────────────────────────────────────────────────────────────


async def test_a_lost_settlement_response_is_replayed_instead_of_a_409(v1):
    order_id = await started(v1)
    await verify(v1, order_id, "SUCCESS")
    first = await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "capture"}, headers=idem("settle-1"))
    again = await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "capture"}, headers=idem("settle-1"))
    assert first.status_code == again.status_code == 200 and again.content == first.content
    assert again.headers[REPLAYED] == "true" and REPLAYED not in first.headers
    assert (await fetch("select status from payments")) == [{"status": "CAPTURED"}]
    # without the key the same call is a different attempt, and a 409
    assert (await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "capture"}, headers=idem("settle-2"))).status_code == 409


async def test_simultaneous_settlements_with_one_key_all_succeed(v1):
    order_id = await started(v1)
    await verify(v1, order_id, "SUCCESS")
    rs = await asyncio.gather(*[v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "capture"}, headers=idem("settle-race")) for _ in range(4)])
    assert [r.status_code for r in rs] == [200] * 4 and len({r.content for r in rs}) == 1
    assert sum(REPLAYED not in r.headers for r in rs) == 1


async def test_a_refused_settlement_is_not_stored_so_it_can_be_retried_once_verified(v1):
    order_id = await started(v1)
    refused = await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "capture"}, headers=idem("later"))
    assert refused.status_code == 409 and await fetch("select 1 from idempotency_keys where key = 'later'") == []
    await verify(v1, order_id, "SUCCESS")
    ok = await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "capture"}, headers=idem("later"))
    assert ok.status_code == 200 and REPLAYED not in ok.headers  # a real capture, not a replay of the 409


async def test_settlement_requires_the_header(v1):
    order_id = await started(v1)
    r = await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "cancel"})
    assert r.status_code == 400 and "Idempotency-Key" in r.json()["detail"]
    assert (await fetch("select status from payments")) == [{"status": "AUTHORIZED"}]


async def test_an_unknown_order_with_a_key_is_a_404_and_stores_nothing(v1):
    r = await v1.post("/v1/orders/11111111-1111-1111-1111-111111111111/settlement", json={"action": "cancel"}, headers=idem("ghost"))
    assert r.status_code == 404 and await count("idempotency_keys") == 0


# ─── legacy POST /orders is unaffected ───────────────────────────────────────────────────────────


async def test_legacy_orders_ignore_the_header_and_never_dedupe(v1):
    a = await v1.post("/orders", json=order_body(), headers=idem("legacy"))
    b = await v1.post("/orders", json=order_body(), headers=idem("legacy"))
    assert a.json()["order_id"] != b.json()["order_id"] and await count("idempotency_keys") == 0
    assert TRANSACTIONS  # (fixtures shared with the other suites)
