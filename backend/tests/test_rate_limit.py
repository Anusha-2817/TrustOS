"""Phase 5a: rate limiting (slowapi, in-memory). The suite runs with limits OFF (conftest); these tests switch them on."""

import pytest

from cases import PRODUCT_EVALUATIONS, TRANSACTIONS
from pg_fixtures import mint_api_key
from services import rate_limit
from test_api_v1 import GHOST, idem, order_body, started


@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setattr(rate_limit.limiter, "enabled", True)


def evaluate(v1, headers=None):
    return v1.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers=headers)


async def test_limits_are_off_by_default_in_the_suite(v1):
    assert all([(await evaluate(v1)).status_code == 200 for _ in range(70)])


async def test_risk_evaluate_is_limited_per_key_with_headers(v1, limits_on, monkeypatch):
    monkeypatch.setenv("RL_RISK_EVALUATE", "3/minute")
    rs = [await evaluate(v1) for _ in range(3)]
    assert [r.status_code for r in rs] == [200, 200, 200]
    assert [r.headers["x-ratelimit-limit"] for r in rs] == ["3"] * 3
    assert [r.headers["x-ratelimit-remaining"] for r in rs] == ["2", "1", "0"]
    blocked = await evaluate(v1)
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Rate limit exceeded: 3 per 1 minute"}
    assert 0 < int(blocked.headers["retry-after"]) <= 61


async def test_each_key_has_its_own_bucket(v1, limits_on, monkeypatch):
    monkeypatch.setenv("RL_RISK_EVALUATE", "2/minute")
    other = await mint_api_key("other")
    for _ in range(2):
        await evaluate(v1)
    assert (await evaluate(v1)).status_code == 429
    assert (await evaluate(v1, {"X-API-Key": other})).status_code == 200


async def test_buckets_are_separate_per_group(v1, limits_on, monkeypatch):
    monkeypatch.setenv("RL_RISK_EVALUATE", "1/minute")
    await evaluate(v1)
    assert (await evaluate(v1)).status_code == 429
    r = await v1.post("/v1/orders", json=order_body(), headers=idem())  # orders have their own 30/minute
    assert r.status_code == 201


async def test_orders_are_limited_to_30_a_minute_by_default(v1, limits_on):
    codes = [(await v1.post("/v1/orders", json=order_body(), headers=idem())).status_code for _ in range(31)]
    assert codes.count(201) == 30 and codes[-1] == 429


async def test_every_other_v1_route_shares_one_pool(v1, limits_on, monkeypatch):
    order_id = await started(v1)  # the setup calls below are outside the limited window
    monkeypatch.setenv("RL_V1_OTHER", "3/minute")
    rate_limit.reset()
    assert (await v1.get(f"/v1/orders/{order_id}")).status_code == 200
    assert (await v1.post(f"/v1/orders/{order_id}/verification", json={"result": "SUCCESS"})).status_code == 200
    assert (await v1.get(f"/v1/orders/{GHOST}")).status_code == 404  # a 404 still counts
    assert (await v1.get(f"/v1/orders/{order_id}")).status_code == 429
    assert (await v1.post(f"/v1/orders/{order_id}/settlement", json={"action": "capture"}, headers=idem())).status_code == 429


async def test_a_replayed_request_still_counts(v1, limits_on, monkeypatch):
    monkeypatch.setenv("RL_ORDERS_CREATE", "2/minute")
    key = idem("dup")
    assert (await v1.post("/v1/orders", json=order_body(), headers=key)).status_code == 201
    assert (await v1.post("/v1/orders", json=order_body(), headers=key)).headers["idempotent-replayed"] == "true"
    assert (await v1.post("/v1/orders", json=order_body(), headers=key)).status_code == 429


async def test_unauthenticated_calls_are_401_not_429_and_do_not_use_the_key_bucket(api, key, limits_on, monkeypatch):
    monkeypatch.setenv("RL_RISK_EVALUATE", "1/minute")
    for _ in range(3):
        assert (await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"])).status_code == 401
    assert (await api.post("/v1/risk/evaluate", json=TRANSACTIONS["low_risk"], headers={"X-API-Key": key})).status_code == 200


async def test_a_flood_of_unrecognised_keys_is_stopped_before_it_reaches_the_database(api, key, limits_on, monkeypatch):
    monkeypatch.setenv("AUTH_LOOKUP_LIMIT", "3/minute")
    good = {"X-API-Key": key}
    assert (await evaluate(api, good)).status_code == 200  # lookup 1, then cached
    statuses = [(await evaluate(api, {"X-API-Key": f"tos_bogus{i}"})).status_code for i in range(3)]
    assert statuses == [401, 401, 429]
    assert (await evaluate(api, good)).status_code == 200  # cached keys never touch the limit


def test_evaluate_product_is_limited_per_ip(client, limits_on, monkeypatch):
    monkeypatch.setenv("RL_EVALUATE_PRODUCT", "2/minute")
    body = next(iter(PRODUCT_EVALUATIONS.values()))
    assert [client.post("/evaluate-product", json=body).status_code for _ in range(2)] == [200, 200]
    blocked = client.post("/evaluate-product", json=body)
    assert blocked.status_code == 429 and blocked.json()["detail"].startswith("Rate limit exceeded")
    # an API key does not buy a separate bucket on the unauthenticated legacy route: it is keyed by IP
    assert client.post("/evaluate-product", json=body, headers={"X-API-Key": "tos_x"}).status_code == 429


def test_the_default_evaluate_product_limit_is_10_a_minute(client, limits_on):
    body = next(iter(PRODUCT_EVALUATIONS.values()))
    codes = [client.post("/evaluate-product", json=body).status_code for _ in range(11)]
    assert codes.count(200) == 10 and codes[-1] == 429


def test_the_other_legacy_routes_are_not_limited(client, limits_on):
    assert all(client.post("/decision/evaluate", json=TRANSACTIONS["low_risk"]).status_code == 200 for _ in range(70))
    assert all(client.get("/health").status_code == 200 for _ in range(70))


def test_the_storage_uri_is_configurable(monkeypatch):
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-c", "from services import rate_limit as r; print(r.STORAGE_URI)"],
        cwd=str(__import__('pathlib').Path(__file__).resolve().parents[1]),
        env={**__import__('os').environ, "RATE_LIMIT_STORAGE_URI": "memory://"}, capture_output=True, text=True,
    )
    assert out.stdout.strip() == "memory://"
