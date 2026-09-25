"""Phase 4 tests that need no live database: config, pool, fail-closed behaviour, the LLM fallback flag,
and the order-mode policy tables. (Everything here runs in the default suite, with DATABASE_URL unset.)"""

import asyncio
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
import sqlalchemy as sa

import db
import db_schema as S
from cases import TRANSACTIONS
from services import order_flow, payment_engine, risk_log

# ─── configuration ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("postgresql://u:p@h:5432/d", "postgresql+asyncpg://u:p@h:5432/d"),
        ("postgres://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
        ("postgresql+asyncpg://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
        ("  postgresql://u@h/d  ", "postgresql+asyncpg://u@h/d"),
        ("", None),
        ("   ", None),
    ],
)
def test_database_url_is_normalised_to_asyncpg(raw, expected):
    assert db.database_url(raw) == expected


def test_database_url_reads_the_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.database_url() is None and not db.is_configured()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@h/d")
    assert db.database_url() == "postgresql+asyncpg://u@h/d" and db.is_configured()


async def test_engine_pool_is_configured_from_the_environment(monkeypatch):
    for k, v in {"DB_POOL_SIZE": "3", "DB_MAX_OVERFLOW": "7", "DB_POOL_TIMEOUT": "1.5", "DB_POOL_RECYCLE": "60"}.items():
        monkeypatch.setenv(k, v)
    engine = db.configure("postgresql://u@127.0.0.1:9/d")
    try:
        assert engine.dialect.driver == "asyncpg"
        pool = engine.pool
        assert (pool.size(), pool._max_overflow, pool._timeout, pool._recycle, pool._pre_ping) == (3, 7, 1.5, 60, True)
        with pytest.raises(RuntimeError):
            db.configure("postgresql://u@127.0.0.1:9/other")  # reconfiguring without dispose() is a bug, not a silent swap
    finally:
        await db.dispose()
    assert db.get_engine  # (module still importable after dispose)


async def test_pool_defaults(monkeypatch):
    for k in ("DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    engine = db.configure("postgresql://u@127.0.0.1:9/d")
    try:
        assert (engine.pool.size(), engine.pool._max_overflow, engine.pool._timeout) == (5, 10, 3.0)
    finally:
        await db.dispose()


async def test_sslmode_in_the_url_is_translated_for_asyncpg(monkeypatch):
    engine = db.configure("postgresql://u@127.0.0.1:9/d?sslmode=require")
    try:
        assert "sslmode" not in str(engine.url)  # asyncpg would reject libpq's spelling
    finally:
        await db.dispose()


def test_get_engine_without_configuration_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(db.DatabaseNotConfigured):
        db.get_engine()


def test_money_is_exact():
    assert str(db.money(0.1 + 0.2)) == "0.3" and str(db.money(1234.5)) == "1234.5"
    assert str(db.money(0.8766, 3)) == "0.877" and str(db.money(0.8764, 3)) == "0.876"
    assert str(db.money(25.0)) == "25.0"  # already-rounded engine scores pass through unchanged


# ─── persistence OFF: order routes fail closed, stateless routes carry on ────────────────────────


@pytest.fixture
def order_id():
    return "11111111-1111-1111-1111-111111111111"


def test_order_routes_answer_503_when_persistence_is_off(client, order_id):
    order = {"buyer_id": "b", "seller_id": "s", **TRANSACTIONS["low_risk"]}
    for path, body in (
        ("/orders", order),
        ("/initiate-payment", {"order_id": order_id}),
        ("/verify", {"order_id": order_id}),
        ("/settle", {"order_id": order_id}),
    ):
        r = client.post(path, json=body)
        assert r.status_code == 503 and "DATABASE_URL" in r.json()["detail"], path


def test_stateless_routes_work_with_persistence_off(client):
    assert client.post("/decision/evaluate", json=TRANSACTIONS["low_risk"]).status_code == 200
    assert client.post("/initiate-payment", json={"scenario": "high_risk"}).status_code == 200
    assert client.post("/verify", json={}).json() == {"result": "SUCCESS"}
    assert client.post("/settle", json={}).json() == {"status": "CAPTURED"}


async def test_order_routes_answer_503_when_the_database_is_unreachable(monkeypatch, order_id):
    import main

    db.configure("postgresql://postgres@127.0.0.1:9/trustos_dead")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
            order = {"buyer_id": "b", "seller_id": "s", **TRANSACTIONS["low_risk"]}
            for path, body in (("/orders", order), ("/initiate-payment", {"order_id": order_id}),
                               ("/verify", {"order_id": order_id}), ("/settle", {"order_id": order_id})):
                r = await c.post(path, json=body)
                assert r.status_code == 503 and r.json() == {"detail": "Database unavailable; nothing was recorded"}, path
    finally:
        await db.dispose()


async def test_the_writer_contains_a_bug_while_building_the_row(caplog):
    db.configure("postgresql://postgres@127.0.0.1:9/trustos_dead")
    caplog.set_level(logging.ERROR, logger="trustos.risk_log")
    try:
        assert await risk_log.log_decision_fail_open(lambda: 1 / 0, source="unit") is None
    finally:
        await db.dispose()
    [rec] = caplog.records
    assert "record could not be built" in rec.getMessage() and rec.exc_info[0] is ZeroDivisionError


async def test_the_writer_is_a_no_op_without_persistence():
    def boom():
        raise AssertionError("must not even build the row when persistence is off")

    assert await risk_log.log_decision_fail_open(boom, source="unit") is None


# ─── the fail-open writer's circuit breaker ──────────────────────────────────────────────────────

DEAD = "postgresql://postgres@127.0.0.1:9/trustos_dead"


@pytest.mark.parametrize(
    "exc,expected",
    [(ConnectionRefusedError(), True), (OSError("unreachable"), True), (TimeoutError(), True),
     (sa.exc.OperationalError("s", {}, Exception("x")), True), (sa.exc.InterfaceError("s", {}, Exception("x")), True),
     (sa.exc.IntegrityError("s", {}, Exception("x")), False), (sa.exc.DataError("s", {}, Exception("x")), False),
     (ValueError("bug"), False), (KeyError("llm"), False)],
)
def test_only_connectivity_errors_count_as_an_outage(exc, expected):
    assert db.is_connectivity_error(exc) is expected


@pytest.fixture
async def counted_dead_db(monkeypatch):
    """db configured against a dead port; counts how many times a write actually tried the database."""
    attempts = []
    real = db.transaction

    def counting():
        attempts.append(1)
        return real()

    monkeypatch.setattr(db, "transaction", counting)
    db.configure(DEAD)
    yield attempts
    await db.dispose()


async def test_an_outage_costs_one_attempt_per_cooldown_not_one_per_request(counted_dead_db, caplog, monkeypatch):
    monkeypatch.setenv("DB_LOG_COOLDOWN", "60")
    caplog.set_level(logging.ERROR, logger="trustos.risk_log")
    row = {"source": "unit", "risk_score": 1}
    for _ in range(5):
        assert await risk_log.log_decision_fail_open(lambda: row, source="unit") is None
    assert len(counted_dead_db) == 1  # one real attempt, then the breaker skipped the rest
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 5 and "FAILED" in msgs[0] and all("SKIPPED" in m for m in msgs[1:])
    assert all('"source": "unit"' in m for m in msgs)  # every lost row is still reported in full, so it can be replayed


async def test_the_breaker_retries_after_the_cooldown(counted_dead_db, monkeypatch):
    monkeypatch.setenv("DB_LOG_COOLDOWN", "0.05")
    await risk_log.log_decision_fail_open(lambda: {"a": 1}, source="unit")
    assert db.circuit_is_open()
    await asyncio.sleep(0.1)
    assert not db.circuit_is_open()
    await risk_log.log_decision_fail_open(lambda: {"a": 1}, source="unit")
    assert len(counted_dead_db) == 2


async def test_reconfiguring_resets_the_breaker(counted_dead_db, monkeypatch):
    monkeypatch.setenv("DB_LOG_COOLDOWN", "60")
    await risk_log.log_decision_fail_open(lambda: {}, source="unit")
    assert db.circuit_is_open()
    await db.dispose()
    assert not db.circuit_is_open()
    db.configure(DEAD)  # (the fixture disposes this one)
    assert not db.circuit_is_open()


async def test_a_builder_bug_does_not_trip_the_breaker(counted_dead_db):
    await risk_log.log_decision_fail_open(lambda: 1 / 0, source="unit")
    assert not db.circuit_is_open()


# ─── call_llm: real answers vs the error fallback ────────────────────────────────────────────────


def _llm_returning(text=None, exc=None):
    def create(**_):
        if exc:
            raise exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


CALL = {"product_name": "x", "review_summary": "y", "seller_complaints": 0, "buyer_disputes": 0}


def test_a_genuine_half_confidence_answer_is_not_marked_as_the_fallback(monkeypatch):
    monkeypatch.setattr(payment_engine, "client", _llm_returning(json.dumps({"signals": [], "risk_modifier": 0, "confidence": 0.5})))
    real = payment_engine.call_llm(CALL)
    monkeypatch.setattr(payment_engine, "client", _llm_returning(exc=RuntimeError("openai is down")))
    fallback = payment_engine.call_llm(CALL)
    assert real == {"signals": [], "risk_modifier": 0.0, "confidence": 0.5, "is_fallback": False}
    assert fallback == {"signals": [], "risk_modifier": 0, "confidence": 0.5, "is_fallback": True}
    assert {k: v for k, v in real.items() if k != "is_fallback"} == {k: v for k, v in fallback.items() if k != "is_fallback"}


@pytest.mark.parametrize(
    "text",
    ["not json at all", "[1, 2]", '{"signals": [], "risk_modifier": "lots", "confidence": 0.5}',
     '{"signals": [], "risk_modifier": 0, "confidence": "high"}', "", None],
    ids=["no-json", "not-an-object", "bad-modifier", "bad-confidence", "empty", "none"],
)
def test_every_error_path_is_marked_as_the_fallback(monkeypatch, text):
    monkeypatch.setattr(payment_engine, "client", _llm_returning(text))
    assert payment_engine.call_llm(CALL)["is_fallback"] is True


def test_the_real_answer_carries_its_values(monkeypatch):
    monkeypatch.setattr(payment_engine, "client", _llm_returning(json.dumps({"signals": ["a", " ", "b"], "risk_modifier": 12, "confidence": 3})))
    out = payment_engine.call_llm(CALL)
    assert out == {"signals": ["a", "b"], "risk_modifier": 12.0, "confidence": 1.0, "is_fallback": False}  # confidence clamped, blanks dropped


def test_the_log_builder_refuses_an_llm_output_without_the_flag():
    """A caller that forgets is_fallback must fail loudly (contained by the fail-open writer), never guess."""
    import main
    from cases import PRODUCT_EVALUATIONS
    from conftest import fake_llm
    from models import EvaluateProductRequest

    body = EvaluateProductRequest(**PRODUCT_EVALUATIONS["medium_risk"])
    main.call_llm, real = fake_llm, main.call_llm
    try:
        resp, llm = main._evaluate_product(body)
    finally:
        main.call_llm = real
    risk_log.product_evaluation_record("t", body, resp, llm)  # fine with the flag
    llm.pop("is_fallback")
    with pytest.raises(KeyError):
        risk_log.product_evaluation_record("t", body, resp, llm)


# ─── order-mode policy ───────────────────────────────────────────────────────────────────────────


def test_policy_tables_cover_every_tier_and_only_use_canonical_vocabulary():
    for table, vocab in ((order_flow.INITIAL_PAYMENT_STATUS, S.PAYMENT_STATUSES), (order_flow.PAYMENT_ROUTE, S.PAYMENT_ROUTES)):
        assert set(table) == set(S.TIERS) and set(table.values()) <= set(vocab)
    assert set(order_flow.SETTLE_ACTION_STATUS.values()) <= set(S.PAYMENT_STATUSES)
    assert {order_flow.verification_type_for_tier(t) for t in S.TIERS} == set(S.VERIFICATION_TYPES)
    assert all(a in S.PAYMENT_STATUSES and b in S.PAYMENT_STATUSES for a, b in order_flow.ALLOWED_SETTLEMENTS)


def test_settlement_transitions():
    assert order_flow.ALLOWED_SETTLEMENTS == {
        ("AUTHORIZED", "CAPTURED"), ("AUTHORIZED", "CANCELLED"), ("HELD", "RELEASED"), ("HELD", "CANCELLED")}


@pytest.mark.parametrize(
    "payment,order",
    [(None, "CREATED"), ("AUTHORIZED", "ACTIVE"), ("HELD", "ACTIVE"), ("CAPTURED", "COMPLETED"), ("RELEASED", "COMPLETED"),
     ("CANCELLED", "CANCELLED"), ("REFUNDED", "CANCELLED")],
)
def test_order_status_follows_the_payment(payment, order):
    assert order_flow.order_status_for_payment(payment) == order
    assert order in S.ORDER_STATUSES


def test_every_payment_status_maps_to_an_order_status():
    for status in S.PAYMENT_STATUSES:
        assert order_flow.order_status_for_payment(status) in S.ORDER_STATUSES


# ─── app lifecycle ───────────────────────────────────────────────────────────────────────────────


def test_app_shutdown_disposes_the_engine_and_startup_never_connects(monkeypatch, caplog):
    """Booting with DATABASE_URL set must not touch the network (the engine is lazy), and shutting the app down
    must release the pool."""
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres@127.0.0.1:9/trustos_dead")
    caplog.set_level(logging.INFO, logger="trustos.api")
    db.get_engine()  # what the first request would do
    assert db._engine is not None
    with TestClient(main.app) as client:  # runs the lifespan: startup ... shutdown
        assert client.get("/health").status_code == 200
    assert db._engine is None
    assert any("DATABASE_URL set" in r.getMessage() for r in caplog.records)


def test_app_boots_and_says_so_without_persistence(monkeypatch, caplog):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.delenv("DATABASE_URL", raising=False)
    caplog.set_level(logging.INFO, logger="trustos.api")
    with TestClient(main.app):
        pass
    assert any("running stateless" in r.getMessage() for r in caplog.records)
