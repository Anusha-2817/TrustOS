"""The Alembic migration against a real PostgreSQL: it matches db_schema.py, enforces the vocabularies,
creates exactly the indexes Phase 4 decided to ship, and makes risk_decision_log append-only."""

import asyncio
import re
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError

import db
import db_schema as S
from pg_fixtures import fetch, run_alembic

# ─── no drift between the frozen migration and the code-side metadata ────────────────────────────


def test_migration_matches_metadata(pg_url):
    """`alembic check` fails if autogenerate would emit any operation (columns, types, indexes, FKs)."""
    proc = run_alembic(pg_url, "check")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_downgrade_then_upgrade_roundtrip(pg_url):
    assert run_alembic(pg_url, "downgrade", "base").returncode == 0
    try:
        assert asyncio.run(_tables(pg_url)) == [], "downgrade left tables behind"
    finally:
        proc = run_alembic(pg_url, "upgrade", "head")
        assert proc.returncode == 0, proc.stdout + proc.stderr
    assert asyncio.run(_tables(pg_url)) == sorted(t.name for t in S.ALL_TABLES)


async def _tables(url):
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "select tablename from pg_tables where schemaname = 'public' and tablename <> 'alembic_version' order by 1"
        )
        return [r["tablename"] for r in rows]
    finally:
        await conn.close()


# ─── vocabularies: the constants the code uses == the CHECK constraints the database enforces ────

VOCAB_CONSTRAINTS = [
    ("ck_orders_status", S.ORDER_STATUSES),
    ("ck_orders_risk_tier", S.TIERS),
    ("ck_payments_status", S.PAYMENT_STATUSES),
    ("ck_payments_triggered_by", S.PAYMENT_TRIGGERS),
    ("ck_payments_route", S.PAYMENT_ROUTES),
    ("ck_verifications_type", S.VERIFICATION_TYPES),
    ("ck_verifications_result", S.VERIFICATION_RESULTS),
    ("ck_risk_decision_log_final_tier", S.TIERS),
    ("ck_risk_decision_log_escalated_from", S.TIERS),
    ("ck_risk_decision_log_product_risk_level", S.TIERS),
]


@pytest.mark.parametrize("constraint,vocab", VOCAB_CONSTRAINTS, ids=[c for c, _ in VOCAB_CONSTRAINTS])
async def test_check_constraint_lists_exactly_the_vocabulary(pg, constraint, vocab):
    rows = await fetch("select pg_get_constraintdef(oid) as d from pg_constraint where conname = :n", n=constraint)
    assert len(rows) == 1, f"{constraint} is missing"
    assert set(re.findall(r"'([A-Z_]+)'", rows[0]["d"])) == set(vocab)


def test_decision_4_vocabularies_are_the_agreed_ones():
    assert S.VERIFICATION_RESULTS == ("PENDING", "SUCCESS", "ISSUE", "FRAUD", "INCONSISTENT", "NO_RESPONSE")
    assert S.PAYMENT_STATUSES == ("AUTHORIZED", "HELD", "CAPTURED", "RELEASED", "CANCELLED", "REFUNDED")
    assert S.PAYMENT_TRIGGERS == ("MANUAL", "AUTO", "TIMEOUT")


# ─── indexes: exactly the "ship with the tables" set, none of the deferred ones ─────────────────

SHIPPED_INDEXES = {
    "ix_orders_seller_id_created_at",
    "ix_orders_buyer_id_created_at",
    "ix_payments_order_id",
    "ix_verifications_order_id",
    "ix_risk_decision_log_order_id_decided_at",
    "ix_risk_decision_log_decided_at_brin",
    "ix_idempotency_keys_expires_at",  # Phase 5a: the expired-key purge runs on every idempotent write
}


async def test_only_the_decided_secondary_indexes_exist(pg):
    """A guard against speculative indexes. The deferred ones (payments/verifications sweeper partials,
    risk-log buyer/seller, open-orders status) are listed in CLAUDE.md and must be added deliberately."""
    rows = await fetch(
        "select c.relname as indexname from pg_index i join pg_class c on c.oid = i.indexrelid"
        " join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and not i.indisprimary"
    )
    assert {r["indexname"] for r in rows} == SHIPPED_INDEXES


async def test_index_shapes(pg):
    defs = {r["indexname"]: r["indexdef"] for r in await fetch("select indexname, indexdef from pg_indexes where schemaname='public'")}
    assert "(seller_id, created_at DESC)" in defs["ix_orders_seller_id_created_at"]
    assert "(buyer_id, created_at DESC)" in defs["ix_orders_buyer_id_created_at"]
    log = defs["ix_risk_decision_log_order_id_decided_at"]
    assert "(order_id, decided_at DESC)" in log and "WHERE (order_id IS NOT NULL)" in log
    assert "USING brin (decided_at)" in defs["ix_risk_decision_log_decided_at_brin"]


# ─── the log is append-only ──────────────────────────────────────────────────────────────────────

LOG_ROW = dict(source="decision_evaluate", formula="static_v1", code_version="t", request_payload={}, risk_score=10, final_tier="LOW")


async def test_risk_decision_log_rejects_update_and_delete(pg):
    async with db.transaction() as conn:
        rid = await db.insert_risk_decision(conn, LOG_ROW)
    for stmt in ("update risk_decision_log set risk_score = 99 where id = :i", "delete from risk_decision_log where id = :i"):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db.transaction() as conn:
                await conn.execute(sa.text(stmt), {"i": rid})
    assert (await fetch("select risk_score from risk_decision_log where id = :i", i=rid))[0]["risk_score"] == 10


# ─── constraints that carry rules, not just vocabularies ─────────────────────────────────────────


@pytest.mark.parametrize(
    "overrides",
    [
        {"risk_score": 101},
        {"final_tier": "SEVERE"},
        {"escalated_from": "LOW", "final_tier": "LOW"},  # "escalated" to the same tier
        {"source": ""},
        {"llm_confidence": 0.5},  # an LLM field without the fallback flag
    ],
    ids=["score>100", "bad-tier", "escalated-to-same-tier", "empty-source", "llm-fields-need-flag"],
)
async def test_risk_log_row_constraints(pg, overrides):
    with pytest.raises(IntegrityError):
        async with db.transaction() as conn:
            await db.insert_risk_decision(conn, {**LOG_ROW, **overrides})


async def test_llm_fields_allowed_with_the_flag_either_way(pg):
    async with db.transaction() as conn:
        for flag in (True, False):
            await db.insert_risk_decision(conn, {**LOG_ROW, "llm_is_fallback": flag, "llm_confidence": 0.5, "llm_signals": []})


async def test_verification_completed_iff_resolved(pg):
    async with db.transaction() as conn:
        order = await db.create_order(conn, buyer_id="b", seller_id="s", product_id=None, amount=db.money(10))
    resolved_without_time = {"result": "SUCCESS"}
    pending_with_time = {"result": "PENDING", "completed_at": datetime.now(timezone.utc)}
    for kw in (resolved_without_time, pending_with_time):
        with pytest.raises(IntegrityError):
            async with db.transaction() as conn:
                await db.create_verification(conn, order_id=order["order_id"], type="PASSIVE", **kw)
