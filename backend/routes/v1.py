"""
TrustOS — the versioned public API (``/v1``), Phase 5a. What a payment gateway calls.

Everything here needs ``X-API-Key`` (services/auth.py), is rate limited per API key (services/rate_limit.py),
and is order-oriented: unlike the legacy demo routes there is no stateless mode, so the routes that touch orders
need DATABASE_URL and answer 503 without it (a request that can't be recorded is never pretended to be).

  POST /v1/risk/evaluate                     evaluate a transaction (no order); same handler as /decision/evaluate
  POST /v1/orders                            create + evaluate an order      (Idempotency-Key required)
  GET  /v1/orders/{order_id}                 the order, its payment and verifications
  POST /v1/orders/{order_id}/payment         start the payment under the order's decision
  POST /v1/orders/{order_id}/verification    report the verification outcome
  POST /v1/orders/{order_id}/settlement      capture / release / cancel (Idempotency-Key required)
                                             capture and release need the latest verification to be SUCCESS (as on the legacy /settle)

Errors use the API's usual ``{"detail": ...}`` body: 400 bad Idempotency-Key, 401 key, 404 unknown order,
409 wrong state, 422 invalid body or a reused Idempotency-Key, 429 rate limit, 503 database unavailable.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.concurrency import run_in_threadpool

from models import CreateOrderRequest, FullEvaluationResponse, OrderResponse, TransactionRequest
from models.v1 import (
    V1OrderView,
    V1PaymentStarted,
    V1Settled,
    V1SettlementRequest,
    V1VerificationRecorded,
    V1VerificationRequest,
    payment_view,
    verification_view,
)
from services import evaluation, idempotency, order_service, rate_limit
from services.auth import require_api_key
from services.pipeline import run_pipeline
from services.rate_limit import limiter

_RESPONSES = {
    401: {"description": "Missing, unknown or revoked X-API-Key"},
    429: {"description": "Rate limit exceeded (see Retry-After)"},
    503: {"description": "Database unavailable; nothing was recorded"},
}

router = APIRouter(prefix="/v1", tags=["v1"], dependencies=[Depends(require_api_key)], responses=_RESPONSES)

_IDEMPOTENCY_HEADER = Header(
    None,
    alias=idempotency.HEADER,
    description=(
        "Required. 1-255 printable ASCII characters; a retry with the same key and the same request replays the "
        "original response (header Idempotent-Replayed: true) instead of repeating the work. Kept 24 hours. "
        "The same key with a different request is a 422."
    ),
)


def _caller(request: Request) -> str:
    return request.state.api_key_hash


@router.post(
    "/risk/evaluate",
    response_model=FullEvaluationResponse,
    summary="Evaluate a transaction",
    description="Trust → risk → decision for one transaction, without creating an order. Same handler as the legacy "
    "/decision/evaluate; the decision is logged (risk_decision_log), and a logging problem never changes the response.",
)
@limiter.shared_limit(rate_limit.risk_evaluate, scope=rate_limit.SCOPE_RISK_EVALUATE)
async def v1_risk_evaluate(request: Request, response: Response, body: TransactionRequest):
    return await evaluation.evaluate_and_log(body)


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=201,
    summary="Create and evaluate an order",
    description="Creates the order, evaluates it, and records the decision, all in one transaction (no order without "
    "its decision). Idempotency-Key is required.",
)
@limiter.shared_limit(rate_limit.orders_create, scope=rate_limit.SCOPE_ORDERS_CREATE)
async def v1_create_order(
    request: Request,
    response: Response,
    body: CreateOrderRequest,
    idempotency_key: Optional[str] = _IDEMPOTENCY_HEADER,
):
    idem = idempotency.context(_caller(request), idempotency_key, "POST", request.url.path, body)
    full = await run_in_threadpool(run_pipeline, body)
    async with order_service.order_transaction() as conn:
        stored = await idempotency.begin(conn, idem)
        if stored is not None:
            return idempotency.response(stored["status"], stored["body"], replayed=True)
        order = await order_service.create_order(conn, body, full)
        payload = order_service.order_response(order, full).model_dump(mode="json")
        await idempotency.store(conn, idem, status=201, body=payload, order_id=order["order_id"])
        return idempotency.response(201, payload, replayed=False)


@router.get("/orders/{order_id}", response_model=V1OrderView, summary="Get an order")
@limiter.shared_limit(rate_limit.v1_other, scope=rate_limit.SCOPE_V1_OTHER)
async def v1_get_order(request: Request, response: Response, order_id: UUID):
    async with order_service.order_transaction() as conn:
        view = await order_service.order_view(conn, order_id)
    order, payment = view["order"], view["payment"]
    return V1OrderView(
        order_id=order["order_id"],
        status=order["status"],
        buyer_id=order["buyer_id"],
        seller_id=order["seller_id"],
        product_id=order["product_id"],
        amount=float(order["amount"]),
        currency=order["currency"],
        risk_score=float(order["risk_score"]) if order["risk_score"] is not None else None,
        risk_tier=order["risk_tier"],
        created_at=order["created_at"],
        updated_at=order["updated_at"],
        payment=payment_view(payment) if payment is not None else None,
        verifications=[verification_view(v) for v in view["verifications"]],
    )


@router.post(
    "/orders/{order_id}/payment",
    response_model=V1PaymentStarted,
    status_code=201,
    summary="Start the payment",
    description="Starts the payment of a CREATED order under the decision recorded when it was created (LOW: captured "
    "at once; MEDIUM: authorized, capture later; HIGH: held), and opens the verification that tier requires. "
    "409 if a payment was already started.",
)
@limiter.shared_limit(rate_limit.v1_other, scope=rate_limit.SCOPE_V1_OTHER)
async def v1_start_payment(request: Request, response: Response, order_id: UUID):
    async with order_service.order_transaction() as conn:
        started = await order_service.initiate_payment(conn, order_id)
    return V1PaymentStarted(
        order_id=order_id,
        order_status=started["order_status"],
        payment=payment_view(started["payment"]),
        verification=verification_view(started["verification"]),
    )


@router.post(
    "/orders/{order_id}/verification",
    response_model=V1VerificationRecorded,
    summary="Report a verification outcome",
    description="Completes the order's pending verification (or, when none is pending, records a retry as a further "
    "verification). 409 for an order that has no payment yet or is cancelled.",
)
@limiter.shared_limit(rate_limit.v1_other, scope=rate_limit.SCOPE_V1_OTHER)
async def v1_record_verification(request: Request, response: Response, order_id: UUID, body: V1VerificationRequest):
    async with order_service.order_transaction() as conn:
        recorded = await order_service.record_verification(conn, order_id, body.result, body.details)
    return V1VerificationRecorded(
        order_id=order_id, order_status=recorded["order_status"], verification=verification_view(recorded["verification"])
    )


@router.post(
    "/orders/{order_id}/settlement",
    response_model=V1Settled,
    summary="Settle the payment",
    description="capture / cancel an AUTHORIZED payment, release / cancel a HELD one; anything else is a 409. "
    "**A capture or a release is refused with 409 unless the order's latest verification is SUCCESS** (cancel is "
    "not gated; the legacy /settle with an order_id applies the same rule). Idempotency-Key is required.",
)
@limiter.shared_limit(rate_limit.v1_other, scope=rate_limit.SCOPE_V1_OTHER)
async def v1_settle(
    request: Request,
    response: Response,
    order_id: UUID,
    body: V1SettlementRequest,
    idempotency_key: Optional[str] = _IDEMPOTENCY_HEADER,
):
    idem = idempotency.context(_caller(request), idempotency_key, "POST", request.url.path, body)
    async with order_service.order_transaction() as conn:
        stored = await idempotency.begin(conn, idem)
        if stored is not None:
            return idempotency.response(stored["status"], stored["body"], replayed=True)
        settled = await order_service.settle_payment(conn, order_id, body.action)
        payload = V1Settled(
            order_id=order_id, order_status=settled["order_status"], payment=payment_view(settled["payment"])
        ).model_dump(mode="json")
        await idempotency.store(conn, idem, status=200, body=payload, order_id=order_id)
        return idempotency.response(200, payload, replayed=False)
