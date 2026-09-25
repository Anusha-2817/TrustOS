"""
TrustOS — persistence: async engine + connection pool (asyncpg) and the repository functions.

Replaces the three empty in-memory dicts this file used to hold. Configuration is one environment
variable, ``DATABASE_URL`` (``postgresql://…`` is accepted and rewritten to the asyncpg driver). With it
unset the app runs exactly as before, minus persistence: the log-writing routes skip the write and the
order-aware routes answer 503. The engine is created lazily on first use, so importing this module or
booting the app never touches the network.

Repositories are plain async functions that take an ``AsyncConnection`` and return dicts, so a route can
compose several of them in one transaction::

    async with db.transaction() as conn:
        order = await db.create_order(conn, ...)
        await db.insert_risk_decision(conn, record)

Pool settings (env, all optional): DB_POOL_SIZE=5, DB_MAX_OVERFLOW=10, DB_POOL_TIMEOUT=3 (s waiting for a
pooled connection), DB_CONNECT_TIMEOUT=3 (s to open a connection), DB_COMMAND_TIMEOUT=10 (s per statement),
DB_POOL_RECYCLE=1800, DB_LOG_COOLDOWN=5 (see the circuit breaker below). The timeouts are short on
purpose: the fail-open log writes must not stall a response when the database is down.
"""

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from db_schema import api_keys, idempotency_keys, orders, payments, risk_decision_log, verifications


class DatabaseNotConfigured(RuntimeError):
    """DATABASE_URL is not set and no engine was configured explicitly."""


_engine: Optional[AsyncEngine] = None
_circuit_open_until = 0.0  # time.monotonic() deadline; see the circuit breaker section


# ─── engine / pool ───────────────────────────────────────────────────────────────────────────────


def database_url(raw: Optional[str] = None) -> Optional[str]:
    """DATABASE_URL (or ``raw``) rewritten to the asyncpg driver; None when unset."""
    raw = raw if raw is not None else os.environ.get("DATABASE_URL")
    if not raw or not raw.strip():
        return None
    url = make_url(raw.strip())
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+asyncpg")
    return url.render_as_string(hide_password=False)


def _env_num(name: str, default, cast=float):
    value = os.environ.get(name)
    return cast(value) if value not in (None, "") else default


def _build_engine(url: str) -> AsyncEngine:
    parsed = make_url(url)
    connect_args: Dict[str, Any] = {
        "timeout": _env_num("DB_CONNECT_TIMEOUT", 3.0),
        "command_timeout": _env_num("DB_COMMAND_TIMEOUT", 10.0),
    }
    # asyncpg takes ``ssl=``, not libpq's ``sslmode=``: translate so a standard DATABASE_URL just works.
    sslmode = parsed.query.get("sslmode")
    if sslmode:
        parsed = parsed.difference_update_query(["sslmode"])
        connect_args["ssl"] = sslmode
    return create_async_engine(
        parsed,
        pool_size=_env_num("DB_POOL_SIZE", 5, int),
        max_overflow=_env_num("DB_MAX_OVERFLOW", 10, int),
        pool_timeout=_env_num("DB_POOL_TIMEOUT", 3.0),
        pool_recycle=_env_num("DB_POOL_RECYCLE", 1800, int),
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def configure(url: str) -> AsyncEngine:
    """Create the engine for ``url`` explicitly (tests, scripts). Call ``dispose()`` before reconfiguring."""
    global _engine
    if _engine is not None:
        raise RuntimeError("db is already configured; await db.dispose() first")
    resolved = database_url(url)
    if resolved is None:
        raise DatabaseNotConfigured("empty database url")
    _engine = _build_engine(resolved)
    close_circuit()
    return _engine


def is_configured() -> bool:
    return _engine is not None or database_url() is not None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = database_url()
        if url is None:
            raise DatabaseNotConfigured("DATABASE_URL is not set")
        _engine = _build_engine(url)
    return _engine


async def dispose() -> None:
    """Close every pooled connection (app shutdown / test teardown). Safe to call when never configured."""
    global _engine
    if _engine is not None:
        engine, _engine = _engine, None
        await engine.dispose()
    close_circuit()


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncConnection]:
    """One database transaction: commits on a clean exit, rolls back on any exception."""
    async with get_engine().begin() as conn:
        yield conn


# ─── circuit breaker for the fail-open writers ───────────────────────────────────────────────────
# When the database is unreachable, every fail-open log write would otherwise wait out a connect attempt
# (~2 s to a refused port on Windows, up to DB_CONNECT_TIMEOUT to a black hole) before the response could
# go out. After a connectivity failure the writers skip the database for DB_LOG_COOLDOWN seconds (they
# still report each lost row on the logger), then try again. Order-mode routes fail closed and don't use it.


def is_connectivity_error(exc: BaseException) -> bool:
    """True for "the database can't be reached" (refused / timed out / dropped), not for a rejected statement."""
    if isinstance(exc, (OSError, asyncio.TimeoutError, sa.exc.TimeoutError, sa.exc.InterfaceError, sa.exc.OperationalError)):
        return True
    return isinstance(exc, sa.exc.DBAPIError) and bool(exc.connection_invalidated)


def circuit_is_open() -> bool:
    return time.monotonic() < _circuit_open_until


def trip_circuit() -> None:
    global _circuit_open_until
    _circuit_open_until = time.monotonic() + _env_num("DB_LOG_COOLDOWN", 5.0)


def close_circuit() -> None:
    global _circuit_open_until
    _circuit_open_until = 0.0


def _row(row) -> Optional[Dict[str, Any]]:
    return dict(row._mapping) if row is not None else None


def money(value: float, places: int = 2) -> Decimal:
    """float → Decimal via its rounded repr, so 0.1 + 0.2 style noise never reaches a NUMERIC column."""
    return Decimal(str(round(float(value), places)))


# ─── orders ──────────────────────────────────────────────────────────────────────────────────────


async def create_order(
    conn: AsyncConnection,
    *,
    buyer_id: str,
    seller_id: str,
    product_id: Optional[str],
    amount: Decimal,
    currency: str = "INR",
    risk_score: Optional[Decimal] = None,
    risk_tier: Optional[str] = None,
) -> Dict[str, Any]:
    result = await conn.execute(
        sa.insert(orders)
        .values(
            buyer_id=buyer_id,
            seller_id=seller_id,
            product_id=product_id,
            amount=amount,
            currency=currency,
            risk_score=risk_score,
            risk_tier=risk_tier,
        )
        .returning(*orders.c)
    )
    return _row(result.one())


async def get_order(conn: AsyncConnection, order_id: uuid.UUID, *, for_update: bool = False) -> Optional[Dict[str, Any]]:
    """``for_update`` takes a row lock, serialising concurrent order-mode calls (two /initiate-payment at once)."""
    stmt = sa.select(orders).where(orders.c.order_id == order_id)
    if for_update:
        stmt = stmt.with_for_update()
    return _row((await conn.execute(stmt)).one_or_none())


async def set_order_status(conn: AsyncConnection, order_id: uuid.UUID, status: str) -> None:
    await conn.execute(sa.update(orders).where(orders.c.order_id == order_id).values(status=status, updated_at=sa.func.now()))


# ─── payments ────────────────────────────────────────────────────────────────────────────────────


async def create_payment(
    conn: AsyncConnection,
    *,
    order_id: uuid.UUID,
    route: str,
    status: str,
    triggered_by: str,
    amount: Decimal,
    currency: str = "INR",
    authorized_at: Optional[datetime] = None,
    settled_at: Optional[datetime] = None,
    provider_ref: Optional[str] = None,
) -> Dict[str, Any]:
    result = await conn.execute(
        sa.insert(payments)
        .values(
            order_id=order_id,
            route=route,
            status=status,
            triggered_by=triggered_by,
            amount=amount,
            currency=currency,
            authorized_at=authorized_at,
            settled_at=settled_at,
            provider_ref=provider_ref,
        )
        .returning(*payments.c)
    )
    return _row(result.one())


async def get_latest_payment(conn: AsyncConnection, order_id: uuid.UUID, *, for_update: bool = False) -> Optional[Dict[str, Any]]:
    stmt = sa.select(payments).where(payments.c.order_id == order_id).order_by(payments.c.created_at.desc()).limit(1)
    if for_update:
        stmt = stmt.with_for_update()
    return _row((await conn.execute(stmt)).one_or_none())


async def update_payment_status(
    conn: AsyncConnection,
    payment_id: uuid.UUID,
    *,
    status: str,
    triggered_by: str,
    settled_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    result = await conn.execute(
        sa.update(payments)
        .where(payments.c.payment_id == payment_id)
        .values(status=status, triggered_by=triggered_by, settled_at=settled_at, updated_at=sa.func.now())
        .returning(*payments.c)
    )
    return _row(result.one())


# ─── verifications ───────────────────────────────────────────────────────────────────────────────


async def create_verification(
    conn: AsyncConnection,
    *,
    order_id: uuid.UUID,
    type: str,
    result: str = "PENDING",
    details: Optional[Dict[str, Any]] = None,
    completed_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    res = await conn.execute(
        sa.insert(verifications)
        .values(order_id=order_id, type=type, result=result, details=details, completed_at=completed_at)
        .returning(*verifications.c)
    )
    return _row(res.one())


async def get_latest_pending_verification(conn: AsyncConnection, order_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    stmt = (
        sa.select(verifications)
        .where(verifications.c.order_id == order_id, verifications.c.result == "PENDING")
        .order_by(verifications.c.requested_at.desc(), verifications.c.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    return _row((await conn.execute(stmt)).one_or_none())


async def complete_verification(
    conn: AsyncConnection, verification_id: uuid.UUID, *, result: str, details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    values: Dict[str, Any] = {"result": result, "completed_at": sa.func.now()}
    if details is not None:
        values["details"] = details
    res = await conn.execute(
        sa.update(verifications).where(verifications.c.verification_id == verification_id).values(**values).returning(*verifications.c)
    )
    return _row(res.one())


async def get_latest_verification(conn: AsyncConnection, order_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """The most recently requested verification, whatever its result (a retry is a newer row)."""
    stmt = (
        sa.select(verifications)
        .where(verifications.c.order_id == order_id)
        .order_by(verifications.c.requested_at.desc(), verifications.c.created_at.desc())
        .limit(1)
    )
    return _row((await conn.execute(stmt)).one_or_none())


async def list_verifications(conn: AsyncConnection, order_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Every verification of the order, oldest first."""
    stmt = (
        sa.select(verifications)
        .where(verifications.c.order_id == order_id)
        .order_by(verifications.c.requested_at.asc(), verifications.c.created_at.asc())
    )
    return [dict(r._mapping) for r in (await conn.execute(stmt)).all()]


# ─── risk_decision_log (append-only) ─────────────────────────────────────────────────────────────


async def insert_risk_decision(conn: AsyncConnection, record: Dict[str, Any]) -> int:
    """Append one decision (see services/risk_log.py for how a record is built). Returns its id."""
    result = await conn.execute(sa.insert(risk_decision_log).values(**record).returning(risk_decision_log.c.id))
    return result.scalar_one()


# ─── api_keys ────────────────────────────────────────────────────────────────────────────────────


async def create_api_key(conn: AsyncConnection, *, key_hash: str, label: str) -> Dict[str, Any]:
    result = await conn.execute(sa.insert(api_keys).values(key_hash=key_hash, label=label).returning(*api_keys.c))
    return _row(result.one())


async def get_api_key(conn: AsyncConnection, key_hash: str) -> Optional[Dict[str, Any]]:
    return _row((await conn.execute(sa.select(api_keys).where(api_keys.c.key_hash == key_hash))).one_or_none())


async def list_api_keys(conn: AsyncConnection) -> List[Dict[str, Any]]:
    return [dict(r._mapping) for r in (await conn.execute(sa.select(api_keys).order_by(api_keys.c.created_at))).all()]


async def revoke_api_key(conn: AsyncConnection, key_hash: str) -> bool:
    """True if a live key was revoked; False if it does not exist or was already revoked."""
    result = await conn.execute(
        sa.update(api_keys)
        .where(api_keys.c.key_hash == key_hash, api_keys.c.revoked_at.is_(None))
        .values(revoked_at=sa.func.now())
    )
    return result.rowcount == 1


# ─── idempotency_keys ────────────────────────────────────────────────────────────────────────────


async def lock_idempotency_key(conn: AsyncConnection, scope: str, key: str) -> None:
    """Serialise every request that uses this (scope, key) until this transaction ends. A duplicate that
    arrives while the first is still working waits here, then finds the stored response instead of doing
    the work twice. (The lock is on a hash of the pair; a collision only makes two keys wait for each other.)"""
    await conn.execute(sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtextextended(scope + ":" + key, 0))))


async def get_idempotency_key(conn: AsyncConnection, scope: str, key: str) -> Optional[Dict[str, Any]]:
    """The stored response for (scope, key), or None if there is none or it has expired."""
    stmt = sa.select(idempotency_keys).where(
        idempotency_keys.c.scope == scope, idempotency_keys.c.key == key, idempotency_keys.c.expires_at > sa.func.now()
    )
    return _row((await conn.execute(stmt)).one_or_none())


async def purge_expired_idempotency_keys(conn: AsyncConnection, limit: int = 100) -> int:
    """Delete up to ``limit`` expired rows (oldest first, via the expires_at index). SKIP LOCKED so this never
    waits on a row another request is replacing, which would otherwise be a deadlock waiting to happen."""
    result = await conn.execute(
        sa.text(
            "DELETE FROM idempotency_keys WHERE (scope, key) IN ("
            " SELECT scope, key FROM idempotency_keys WHERE expires_at < now()"
            " ORDER BY expires_at LIMIT :n FOR UPDATE SKIP LOCKED)"
        ),
        {"n": limit},
    )
    return result.rowcount


async def store_idempotency_key(
    conn: AsyncConnection,
    *,
    scope: str,
    key: str,
    request_hash: str,
    response_status: int,
    response_body: Dict[str, Any],
    order_id: Optional[uuid.UUID],
    ttl_seconds: int,
) -> None:
    """Record the response for (scope, key). Call after lock_idempotency_key found no live row: an expired row
    left in the way is replaced. Raises RuntimeError if a live row exists (the lock makes that a bug)."""
    stmt = pg_insert(idempotency_keys).values(
        scope=scope,
        key=key,
        request_hash=request_hash,
        response_status=response_status,
        response_body=response_body,
        order_id=order_id,
        expires_at=sa.func.now() + sa.func.make_interval(0, 0, 0, 0, 0, 0, ttl_seconds),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[idempotency_keys.c.scope, idempotency_keys.c.key],
        set_={
            "request_hash": stmt.excluded.request_hash,
            "response_status": stmt.excluded.response_status,
            "response_body": stmt.excluded.response_body,
            "order_id": stmt.excluded.order_id,
            "created_at": sa.func.now(),
            "expires_at": stmt.excluded.expires_at,
        },
        where=idempotency_keys.c.expires_at <= sa.func.now(),
    )
    result = await conn.execute(stmt)
    if result.rowcount != 1:
        raise RuntimeError("a live idempotency row already exists for this (scope, key); lock_idempotency_key was skipped")
