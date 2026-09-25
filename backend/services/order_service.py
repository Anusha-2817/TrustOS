"""
TrustOS — order-mode operations (Phase 4 logic, extracted in Phase 5a so the legacy routes and /v1 share it).

Each function takes an open ``AsyncConnection`` and does one step of the order lifecycle; the CALLER owns the
transaction (``order_transaction()``), which is what lets /v1 wrap the same step in idempotency handling
without duplicating anything. Failures are ``HTTPException`` with the exact status codes and messages the
legacy routes always returned (404 unknown order, 409 wrong state); the persistence-unavailable case is a 503
raised by ``order_transaction`` itself. ``tests/test_characterization_phase5.py`` pins all of it.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

import db
from models import CreateOrderRequest, FullEvaluationResponse, OrderResponse
from services import order_flow, risk_log

logger = logging.getLogger("trustos.api")


@asynccontextmanager
async def order_transaction():
    """One transaction for the order-aware routes. They FAIL CLOSED: an unconfigured or unreachable
    database is a 503, never a response that pretends something was recorded. (HTTPExceptions raised
    inside the block — 404, 409 — pass through and roll the transaction back.)"""
    if not db.is_configured():
        raise HTTPException(status_code=503, detail="Persistence is not configured (DATABASE_URL is not set)")
    try:
        async with db.transaction() as conn:
            yield conn
    except (SQLAlchemyError, OSError, asyncio.TimeoutError):
        logger.exception("order-mode database error")
        raise HTTPException(status_code=503, detail="Database unavailable; nothing was recorded")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def load_order(conn, order_id: UUID, *, for_update: bool = False) -> Dict[str, Any]:
    order = await db.get_order(conn, order_id, for_update=for_update)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


# ─── create ──────────────────────────────────────────────────────────────────────────────────────


async def create_order(conn, body: CreateOrderRequest, full: FullEvaluationResponse) -> Dict[str, Any]:
    """Insert the order and the risk decision it was created under (both in the caller's transaction), and
    return the order row."""
    order = await db.create_order(
        conn,
        buyer_id=body.buyer_id,
        seller_id=body.seller_id,
        product_id=body.product_id,
        amount=db.money(body.order_value),
        currency="INR",
        risk_score=db.money(full.risk_score),
        risk_tier=full.decision.risk_classification,
    )
    await db.insert_risk_decision(
        conn,
        risk_log.pipeline_record(
            "orders_create", body, full, order_id=order["order_id"], buyer_id=body.buyer_id, seller_id=body.seller_id
        ),
    )
    return order


def order_response(order: Dict[str, Any], full: FullEvaluationResponse) -> OrderResponse:
    return OrderResponse(
        order_id=order["order_id"],
        status=order["status"],
        buyer_id=order["buyer_id"],
        seller_id=order["seller_id"],
        product_id=order["product_id"],
        amount=float(order["amount"]),
        currency=order["currency"],
        created_at=order["created_at"],
        evaluation=full,
    )


# ─── payment ─────────────────────────────────────────────────────────────────────────────────────


async def initiate_payment(conn, order_id: UUID) -> Dict[str, Any]:
    """Start the payment of a CREATED order under the decision recorded when it was created (no
    re-evaluation, so no new log row). Returns {order_status, tier, payment, verification}."""
    # Row lock: two simultaneous initiations of one order serialise, and the second sees it is no longer CREATED.
    order = await load_order(conn, order_id, for_update=True)
    if order["status"] != "CREATED":
        raise HTTPException(status_code=409, detail=f"order is {order['status']}; a payment was already initiated")
    tier = order["risk_tier"]
    if tier is None:
        raise HTTPException(status_code=409, detail="order has no recorded risk decision")
    status = order_flow.INITIAL_PAYMENT_STATUS[tier]
    now = _now()
    payment = await db.create_payment(
        conn,
        order_id=order_id,
        route=order_flow.PAYMENT_ROUTE[tier],
        status=status,
        triggered_by="AUTO",  # tier policy, not a request-level action
        amount=order["amount"],
        currency=order["currency"],
        authorized_at=now,
        settled_at=now if status == "CAPTURED" else None,
    )
    verification = await db.create_verification(conn, order_id=order_id, type=order_flow.verification_type_for_tier(tier))
    order_status = order_flow.order_status_for_payment(status)
    await db.set_order_status(conn, order_id, order_status)
    return {"order_status": order_status, "tier": tier, "payment": payment, "verification": verification}


# ─── verification ────────────────────────────────────────────────────────────────────────────────


async def record_verification(conn, order_id: UUID, result: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record a verification outcome: it completes the order's PENDING verification, or (a retry) adds a
    completed one. Returns {order_status, verification}."""
    order = await load_order(conn, order_id, for_update=True)
    if order["status"] in ("CREATED", "CANCELLED"):
        raise HTTPException(status_code=409, detail=f"order is {order['status']}; nothing to verify")
    pending = await db.get_latest_pending_verification(conn, order_id)
    if pending is not None:
        verification = await db.complete_verification(conn, pending["verification_id"], result=result, details=details)
    else:
        verification = await db.create_verification(
            conn,
            order_id=order_id,
            type=order_flow.verification_type_for_tier(order["risk_tier"]),
            result=result,
            details=details,
            completed_at=_now(),
        )
    return {"order_status": order["status"], "verification": verification}


# ─── settlement ──────────────────────────────────────────────────────────────────────────────────


async def settle_payment(conn, order_id: UUID, action: str) -> Dict[str, Any]:
    """Move the order's payment (AUTHORIZED → CAPTURED / CANCELLED, HELD → RELEASED / CANCELLED; anything else
    is a 409) and let the order's status follow. ``action`` must already be a key of SETTLE_ACTION_STATUS.

    A settlement in ``SETTLEMENT_REQUIRES_VERIFIED`` (capture, release: the ones that pay the seller) is also
    refused with a 409 unless the order's latest verification is SUCCESS. That rule applies to every caller:
    /v1 and the legacy /settle (with an order_id) share this function. Returns {order_status, payment}."""
    target = order_flow.SETTLE_ACTION_STATUS[action]
    await load_order(conn, order_id, for_update=True)
    payment = await db.get_latest_payment(conn, order_id, for_update=True)
    if payment is None:
        raise HTTPException(status_code=409, detail="no payment has been initiated for this order")
    if (payment["status"], target) not in order_flow.ALLOWED_SETTLEMENTS:
        raise HTTPException(status_code=409, detail=f"cannot {action} a payment that is {payment['status']}")
    if target in order_flow.SETTLEMENT_REQUIRES_VERIFIED:
        latest = await db.get_latest_verification(conn, order_id)
        seen = latest["result"] if latest is not None else "missing"
        if seen != order_flow.VERIFICATION_PASSED:
            raise HTTPException(
                status_code=409,
                detail=f"cannot {action}: the latest verification is {seen}; {order_flow.VERIFICATION_PASSED} is required",
            )
    payment = await db.update_payment_status(conn, payment["payment_id"], status=target, triggered_by="MANUAL", settled_at=_now())
    order_status = order_flow.order_status_for_payment(target)
    await db.set_order_status(conn, order_id, order_status)
    return {"order_status": order_status, "payment": payment}


# ─── read ────────────────────────────────────────────────────────────────────────────────────────


async def order_view(conn, order_id: UUID) -> Dict[str, Any]:
    """The order, its latest payment (or None) and all its verifications, oldest first."""
    order = await load_order(conn, order_id)
    return {
        "order": order,
        "payment": await db.get_latest_payment(conn, order_id),
        "verifications": await db.list_verifications(conn, order_id),
    }
