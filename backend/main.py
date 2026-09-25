import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from pydantic import BaseModel
from openai import OpenAI
from slowapi.errors import RateLimitExceeded


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sys.path.insert(0, os.path.dirname(__file__))

import db
from services import auth, evaluation, order_flow, order_service, rate_limit, risk_log
from services.trust_engine import TrustEngine
from services.risk_engine import RiskEngine
from services.decision_engine import escalate_tier
from services.payment_engine import call_llm
from services.pipeline import run_pipeline
from services.product_risk import assess_product
from routes.v1 import router as v1_router
from models import (
    BuyerProfile, SellerProfile, TransactionRequest,
    TrustScoreResponse, RiskScoreResponse, DecisionModel,
    FullEvaluationResponse, SimulatorEvaluateRequest,
    EvaluateProductRequest,
    EvaluateProductResponse,
    ProductEvaluateRiskBreakdown,
    CreateOrderRequest, OrderResponse,
)

logger = logging.getLogger("trustos.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if db.is_configured():
        logger.info("persistence: DATABASE_URL set (orders + risk_decision_log enabled)")
    else:
        logger.warning("persistence: DATABASE_URL not set — running stateless; /orders answers 503 and nothing is logged")
    yield
    await db.dispose()


app = FastAPI(
    title="TrustOS API",
    description="Trust enforcement layer for e-commerce: Trust Engine, Risk Engine, Decision Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: explicit origins and NO credentials. (It used to be allow_origins=["*"] with allow_credentials=True, which
# browsers reject and which, echoed back by Starlette, would let any site make credentialed requests.) Auth is
# the X-API-Key header, not cookies, so credentials are not needed. Server-to-server callers (a payment
# gateway) are not subject to CORS at all. Override with CORS_ALLOW_ORIGINS="https://a.example,https://b.example".
_DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
CORS_ORIGINS = [o.strip() for o in (os.environ.get("CORS_ALLOW_ORIGINS") or _DEFAULT_CORS_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "X-API-Key", "Idempotency-Key"],
    # so browser code can read them (Retry-After on a 429, whether a response was a replay)
    expose_headers=["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Idempotent-Replayed"],
)

app.state.limiter = rate_limit.limiter
app.add_exception_handler(RateLimitExceeded, rate_limit.rate_limit_exceeded_handler)

trust_engine = TrustEngine()
risk_engine = RiskEngine()


def _clamp_trust(score: float) -> float:
    return max(0.0, min(100.0, score))


def _product_eval_scores(body: EvaluateProductRequest) -> tuple[float, float, float]:
    bo, bd = body.buyer_orders, body.buyer_disputes
    so, sc = body.seller_orders, body.seller_complaints
    bt = _clamp_trust(40 + (2 * bo) - (15 * (bd / bo if bo > 0 else 0)))
    st = _clamp_trust(50 + (1.5 * so) - (20 * (sc / so if so > 0 else 0)))
    base_risk = 100 - (0.4 * bt) - (0.4 * st)
    return bt, st, base_risk


# ─── Trust Engine Routes ────────────────────────────────────────────────────

@app.post("/trust/buyer", response_model=TrustScoreResponse, tags=["Trust Engine"])
def compute_buyer_trust(profile: BuyerProfile):
    """Calculate Buyer Trust Score (BT) from transaction history."""
    score, level, breakdown = trust_engine.compute_buyer_trust(profile)
    return TrustScoreResponse(
        score=score,
        level=level,
        entity_type="buyer",
        breakdown=breakdown
    )


@app.post("/trust/seller", response_model=TrustScoreResponse, tags=["Trust Engine"])
def compute_seller_trust(profile: SellerProfile):
    """Calculate Seller Trust Score (ST) from transaction history."""
    score, level, breakdown = trust_engine.compute_seller_trust(profile)
    return TrustScoreResponse(
        score=score,
        level=level,
        entity_type="seller",
        breakdown=breakdown
    )


# ─── Risk Engine Routes ─────────────────────────────────────────────────────

@app.post(
    "/evaluate-product",
    response_model=EvaluateProductResponse,
    tags=["Risk Engine"],
)
@rate_limit.limiter.shared_limit(rate_limit.evaluate_product, scope=rate_limit.SCOPE_EVALUATE_PRODUCT, key_func=rate_limit.ip_key)
async def evaluate_product(request: Request, response: Response, body: EvaluateProductRequest):
    """Product context: trust scores, risk breakdown, clamped final risk, LOW|MEDIUM|HIGH.

    Writes the decision (and the raw LLM output) to risk_decision_log; a database problem never changes the response.
    Rate limited per IP (every call is a paid LLM request): 10/minute by default."""
    # The scoring does blocking work (the OpenAI call, and the ML fit on the first catalogue product), so it
    # runs in the threadpool exactly as it did when this route was a plain ``def``.
    response, llm_output = await run_in_threadpool(_evaluate_product, body)
    await risk_log.log_decision_fail_open(
        lambda: risk_log.product_evaluation_record("evaluate_product", body, response, llm_output),
        source="evaluate_product",
    )
    return response


def _evaluate_product(body: EvaluateProductRequest) -> tuple[EvaluateProductResponse, Dict[str, Any]]:
    bt, st, base_risk = _product_eval_scores(body)
    value_risk = risk_engine.value_risk_for_amount(body.product_price)
    context_risk = (20.0 if body.is_new_interaction else 0.0) + (
        10.0 if body.new_device else 0.0
    )
    trust_risk = base_risk
    final_raw = trust_risk + value_risk + context_risk
    existing_final_risk = round(max(0.0, min(100.0, final_raw)), 2)

    data = {
        "product_name": body.product_name,
        "review_summary": body.review_summary,
        "seller_complaints": body.seller_complaints,
        "buyer_disputes": body.buyer_disputes,
    }
    llm_output = call_llm(data)
    signals = llm_output["signals"]
    confidence = float(llm_output["confidence"])
    risk_modifier = float(llm_output["risk_modifier"])
    behavior_risk = len(signals) * 7 + confidence * 10
    final_risk = round(
        max(0.0, min(100.0, existing_final_risk + behavior_risk)),
        2,
    )
    base_decision = risk_engine.classify(final_risk)
    product_risk = assess_product(body.product_id)
    decision = escalate_tier(base_decision, product_risk)

    response = EvaluateProductResponse(
        **body.model_dump(),
        buyer_trust=round(bt, 2),
        seller_trust=round(st, 2),
        base_risk=round(base_risk, 2),
        risk_breakdown=ProductEvaluateRiskBreakdown(
            trust_risk=round(trust_risk, 2),
            value_risk=float(value_risk),
            context_risk=context_risk,
            product_risk=product_risk,
        ),
        final_risk=final_risk,
        decision=decision,
        escalated_from=base_decision if decision != base_decision else None,
        signals=signals,
        risk_modifier=risk_modifier,
        confidence=confidence,
        behavior_risk=round(behavior_risk, 2),
    )
    return response, llm_output


@app.post("/risk/score", response_model=RiskScoreResponse, tags=["Risk Engine"])
def compute_risk_score(request: TransactionRequest):
    """Compute transaction-level Risk Score combining trust + transaction signals."""
    buyer_score, _, _ = trust_engine.compute_buyer_trust(request.buyer)
    seller_score, _, _ = trust_engine.compute_seller_trust(request.seller)
    risk_score, risk_components = risk_engine.compute_risk(
        buyer_trust=buyer_score,
        seller_trust=seller_score,
        order_value=request.order_value,
        is_new_pair=request.is_new_pair,
        is_new_device=request.is_new_device
    )
    risk_components.product_risk = assess_product(request.product_id)
    return RiskScoreResponse(
        risk_score=risk_score,
        buyer_trust=buyer_score,
        seller_trust=seller_score,
        components=risk_components
    )


# ─── Decision Engine Routes ─────────────────────────────────────────────────

@app.post("/simulator/evaluate", response_model=FullEvaluationResponse, tags=["Simulator"])
def evaluate_simulator(body: SimulatorEvaluateRequest):
    """
    Live what-if evaluation from slider inputs (buyer/seller history + order value).
    Same response shape as /decision/evaluate for the UI gauge.
    """
    buyer = _buyer_from_simulator(
        body.buyer_successful_orders,
        body.buyer_dispute_rate_percent,
        body.buyer_fraud_flags,
    )
    seller = _seller_from_simulator(
        body.seller_successful_orders,
        body.seller_complaint_rate_percent,
        body.seller_fraud_flags,
    )
    req = TransactionRequest(
        buyer=buyer,
        seller=seller,
        order_value=body.order_value_inr,
        is_new_pair=body.is_new_pair,
        is_new_device=body.is_new_device,
    )
    return run_pipeline(req)


@app.post("/decision/evaluate", response_model=FullEvaluationResponse, tags=["Decision Engine"])
async def evaluate_transaction(request: TransactionRequest):
    """
    Full pipeline: Trust → Risk → Decision (+ escalate-only product risk when product_id is set).
    Returns trust scores, risk score, risk classification, and enforcement actions.
    The decision is written to risk_decision_log; a database problem never changes the response.
    """
    return await evaluation.evaluate_and_log(request)


# ─── Orders (persisted) ─────────────────────────────────────────────────────


@app.post("/orders", response_model=OrderResponse, status_code=201, tags=["Orders"])
async def create_order(body: CreateOrderRequest):
    """Create an order and evaluate it. The order, its risk decision (risk_decision_log) and the order's
    denormalised risk_score / risk_tier are written in ONE transaction: if any part fails there is no order.
    Follow up with /initiate-payment, /verify and /settle passing the returned order_id."""
    full = await run_in_threadpool(run_pipeline, body)
    async with order_service.order_transaction() as conn:
        order = await order_service.create_order(conn, body, full)
    return order_service.order_response(order, full)


# ─── Simulation Endpoint ─────────────────────────────────────────────────────

# The built-in demo transactions, defined ONCE (this table used to be duplicated for /simulate and for the
# demo-contract routes). Each NAME is the tier its transaction actually scores; tests/test_scenarios.py
# asserts that on every route that takes a scenario. Before the rename the names were off by one tier:
# "low_risk" scored 44.02 (MEDIUM) and "medium_risk" scored 98.57 (HIGH).
SCENARIOS = {
    # 25.0 -> LOW
    "low_risk": TransactionRequest(
        buyer=BuyerProfile(successful_orders=200, total_orders=200, disputes=0, fraud_flags=0),
        seller=SellerProfile(successful_orders=400, total_orders=404, complaints=4, fraud_flags=0),
        order_value=900,
        is_new_pair=False,
        is_new_device=False,
    ),
    # 44.02 -> MEDIUM (the inputs the old "low_risk" had)
    "medium_risk": TransactionRequest(
        buyer=BuyerProfile(successful_orders=12, total_orders=13, disputes=1, fraud_flags=0),
        seller=SellerProfile(successful_orders=55, total_orders=58, complaints=2, fraud_flags=0),
        order_value=1500,
        is_new_pair=False,
        is_new_device=False,
    ),
    # 100.0 -> HIGH (unchanged; the old 98.57 "medium_risk" was a second HIGH example and has no name any more)
    "high_risk": TransactionRequest(
        buyer=BuyerProfile(successful_orders=1, total_orders=2, disputes=1, fraud_flags=0),
        seller=SellerProfile(successful_orders=5, total_orders=8, complaints=2, fraud_flags=0),
        order_value=12000,
        is_new_pair=True,
        is_new_device=True,
    ),
}


@app.get("/simulate/{scenario}", tags=["Demo"])
def simulate_scenario(scenario: str):
    """
    Run a pre-built demo scenario; the name is the tier it scores.
    Options: low_risk | medium_risk | high_risk
    """
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario}' not found. Choose: low_risk, medium_risk, high_risk")

    return run_pipeline(SCENARIOS[scenario].model_copy(deep=True))


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "service": "TrustOS API v1.0.0"}


# ─── Demo contract aliases (frontend-friendly) ──────────────────────────────
# Maps existing Trust/Risk/Decision pipeline to the hackathon UI contract.

SCENARIO_KEYS = frozenset(SCENARIOS)


def _transaction_for_scenario(scenario: str) -> TransactionRequest:
    if scenario not in SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail="Unknown scenario. Use: low_risk, medium_risk, high_risk",
        )
    return SCENARIOS[scenario].model_copy(deep=True)


def _buyer_from_simulator(
    successful: int,
    dispute_rate_pct: float,
    fraud_flags: int,
) -> BuyerProfile:
    disputes = int(round(successful * (dispute_rate_pct / 100)))
    if dispute_rate_pct > 0 and disputes < 1 and successful > 0:
        disputes = 1
    total_orders = max(successful + disputes, successful, 1)
    return BuyerProfile(
        successful_orders=successful,
        total_orders=total_orders,
        disputes=disputes,
        fraud_flags=fraud_flags,
    )


def _seller_from_simulator(
    successful: int,
    complaint_rate_pct: float,
    fraud_flags: int,
) -> SellerProfile:
    complaints = int(round(successful * (complaint_rate_pct / 100)))
    if complaint_rate_pct > 0 and complaints < 1 and successful > 0:
        complaints = 1
    total_orders = max(successful + complaints, successful, 1)
    return SellerProfile(
        successful_orders=successful,
        total_orders=total_orders,
        complaints=complaints,
        fraud_flags=fraud_flags,
    )


class InitiatePaymentBody(BaseModel):
    scenario: Optional[str] = "medium_risk"
    order_id: Optional[UUID] = None  # with an order the tier comes from its stored decision; scenario is ignored


class VerifyBody(BaseModel):
    """Demo-only: drive outcome for the jury. With order_id the result is recorded on that order."""
    passed: bool = True
    inconsistent: bool = False
    order_id: Optional[UUID] = None


class SettleBody(BaseModel):
    """Demo-only: which settlement path to show. With order_id it settles that order's payment."""
    action: str = "capture"  # capture | release | cancel
    order_id: Optional[UUID] = None


@app.get("/evaluate-risk", tags=["Demo Contract"])
def evaluate_risk_contract(scenario: str = "medium_risk"):
    """{ riskLevel, riskScore } — aligns UI gauge with backend."""
    req = _transaction_for_scenario(scenario)
    full = run_pipeline(req)
    rc = full.decision.risk_classification
    return {"riskLevel": rc, "riskScore": round(full.risk_score, 2)}


def _payment_lifecycle_payload(full: FullEvaluationResponse) -> dict:
    return _lifecycle_for_band(full.decision.risk_classification)


def _lifecycle_for_band(band: str) -> dict:
    """Razorpay-style phase labels for settlement UI (demo)."""
    if band == "LOW":
        phases = [
            {
                "id": "authorized",
                "label": "AUTHORIZED",
                "description": "Payment authorized at gateway",
                "state": "complete",
            },
            {
                "id": "held",
                "label": "HELD",
                "description": "Escrow not required — funds route directly",
                "state": "skipped",
            },
            {
                "id": "captured",
                "label": "CAPTURED",
                "description": "Settlement to seller (low risk)",
                "state": "complete",
            },
        ]
        current = "CAPTURED"
    elif band == "MEDIUM":
        phases = [
            {
                "id": "authorized",
                "label": "AUTHORIZED",
                "description": "Card / UPI authorized; capture delayed",
                "state": "complete",
            },
            {
                "id": "held",
                "label": "HELD",
                "description": "TrustOS escrow — awaiting delivery & window",
                "state": "active",
            },
            {
                "id": "captured",
                "label": "CAPTURED",
                "description": "Released to seller after confirmation / timer",
                "state": "pending",
            },
        ]
        current = "AUTHORIZED"
    else:
        phases = [
            {
                "id": "authorized",
                "label": "AUTHORIZED",
                "description": "Authorization recorded",
                "state": "complete",
            },
            {
                "id": "held",
                "label": "HELD",
                "description": "Full hold until verification completes",
                "state": "active",
            },
            {
                "id": "captured",
                "label": "CAPTURED",
                "description": "Only after multi-factor verification",
                "state": "pending",
            },
        ]
        current = "HELD"
    return {
        "provider": "Razorpay Simulation",
        "risk_classification": band,
        "current_phase": current,
        "phases": phases,
    }


@app.get("/demo/payment-lifecycle", tags=["Demo Contract"])
def payment_lifecycle_demo(scenario: str = "medium_risk"):
    """Phase timeline: AUTHORIZED → HELD → CAPTURED (demo, mirrors Razorpay-style labels)."""
    if scenario not in SCENARIO_KEYS:
        raise HTTPException(status_code=400, detail="scenario must be low_risk | medium_risk | high_risk")
    full = run_pipeline(_transaction_for_scenario(scenario))
    return _payment_lifecycle_payload(full)


async def _require_key_for_order_mode(request: Request) -> None:
    """The legacy stateless demo (no order_id) stays open, but touching a stored order needs a valid X-API-Key,
    exactly as on /v1. The header is read straight off the request, not declared as a parameter, so the legacy
    OpenAPI operations keep their pinned shape (the requirement is stated in their description instead)."""
    await auth.require_api_key(request, request.headers.get(auth.HEADER))


@app.post("/initiate-payment", tags=["Demo Contract"])
async def initiate_payment_contract(request: Request, body: InitiatePaymentBody = InitiatePaymentBody()):
    """{ status, lifecycle } — gateway simulation for UI.

    Without order_id: the stateless demo (runs the scenario, logs the decision to risk_decision_log with
    order_id NULL, fail-open). With order_id: starts the payment of that order under the decision recorded
    when it was created (no re-evaluation, so no new log row) and persists payment + a PENDING verification.
    Order mode needs an X-API-Key, fails closed (503) and adds order_id / payment_id / verification_id to the response."""
    if body.order_id is not None:
        await _require_key_for_order_mode(request)
        return await _initiate_payment_for_order(body.order_id)
    scenario = body.scenario or "medium_risk"
    if scenario not in SCENARIO_KEYS:
        raise HTTPException(status_code=400, detail="scenario must be low_risk | medium_risk | high_risk")
    req = _transaction_for_scenario(scenario)
    full = run_pipeline(req)
    await risk_log.log_decision_fail_open(
        lambda: risk_log.pipeline_record("initiate_payment", req, full), source="initiate_payment"
    )
    band = full.decision.risk_classification
    lifecycle = _payment_lifecycle_payload(full)
    return {
        "status": order_flow.INITIAL_PAYMENT_STATUS.get(band, "AUTHORIZED"),
        "lifecycle": lifecycle,
    }


async def _initiate_payment_for_order(order_id: UUID) -> Dict[str, Any]:
    async with order_service.order_transaction() as conn:
        started = await order_service.initiate_payment(conn, order_id)
    return {
        "status": started["payment"]["status"],
        "lifecycle": _lifecycle_for_band(started["tier"]),
        "order_id": order_id,
        "payment_id": started["payment"]["payment_id"],
        "verification_id": started["verification"]["verification_id"],
    }


@app.post("/verify", tags=["Demo Contract"])
async def verify_contract(request: Request, body: VerifyBody = VerifyBody()):
    """{ result: SUCCESS | FRAUD | INCONSISTENT } — demo toggles.

    With order_id the result is recorded: it completes the order's PENDING verification (or adds a completed
    one for a retry). Order mode needs an X-API-Key, fails closed and adds order_id / verification_id to the response."""
    if body.inconsistent:
        result = "INCONSISTENT"
    elif body.passed:
        result = "SUCCESS"
    else:
        result = "FRAUD"
    if body.order_id is None:
        return {"result": result}
    await _require_key_for_order_mode(request)

    async with order_service.order_transaction() as conn:
        recorded = await order_service.record_verification(conn, body.order_id, result)
    verification = recorded["verification"]
    return {"result": result, "order_id": body.order_id, "verification_id": verification["verification_id"]}


@app.post("/settle", tags=["Demo Contract"])
async def settle_contract(request: Request, body: SettleBody = SettleBody()):
    """{ status: CAPTURED | RELEASED | CANCELLED } — demo toggles.

    With order_id it moves that order's payment (AUTHORIZED → CAPTURED / CANCELLED, HELD → RELEASED /
    CANCELLED; anything else is a 409) and the order's status follows. A capture or release also needs the
    order's latest verification to be SUCCESS (409 otherwise), as on /v1. Order mode needs an X-API-Key, fails
    closed and adds order_id / payment_id to the response."""
    if body.order_id is not None:
        await _require_key_for_order_mode(request)  # before anything else, so an anonymous caller learns nothing
    action = (body.action or "capture").lower().strip()
    if action not in order_flow.SETTLE_ACTION_STATUS:
        raise HTTPException(status_code=400, detail="action must be capture | release | cancel")
    target = order_flow.SETTLE_ACTION_STATUS[action]
    if body.order_id is None:
        return {"status": target}

    async with order_service.order_transaction() as conn:
        settled = await order_service.settle_payment(conn, body.order_id, action)
    payment = settled["payment"]
    return {"status": target, "order_id": body.order_id, "payment_id": payment["payment_id"]}


# ─── /v1 (the public API) and the "legacy" note ─────────────────────────────────────────────────

app.include_router(v1_router)

# Every unversioned route below predates /v1 and stays exactly as it is for the demo frontend. Say so in
# their OpenAPI descriptions so nobody integrates against them by accident. (/health is ops, not legacy.)
_LEGACY_NOTE = (
    "\n\n**Deprecated for external use — kept for the demo frontend.** Integrate against the versioned, "
    "authenticated `/v1` API instead. This route needs no API key and is not covered by the `/v1` guarantees."
)
_LEGACY_ORDER_NOTE = (
    " With an `order_id` this route requires the `X-API-Key` header (the stateless demo without `order_id` stays open), "
    "but it still does NOT enforce the other `/v1` rules (no `Idempotency-Key`). `/settle` with an `order_id` applies "
    "the same verification rule as `/v1`: a capture or a release is a 409 unless the latest verification is SUCCESS."
)
_LEGACY_ORDERS_NOTE = (
    " It is unauthenticated, creates a stored order, and does NOT enforce the `/v1` rules (no `Idempotency-Key`); "
    "such an order can only be moved on with an API key."
)
_LEGACY_PATHS = frozenset(
    {
        "/trust/buyer", "/trust/seller", "/evaluate-product", "/risk/score", "/simulator/evaluate",
        "/decision/evaluate", "/orders", "/simulate/{scenario}", "/evaluate-risk", "/demo/payment-lifecycle",
        "/initiate-payment", "/verify", "/settle",
    }
)
_LEGACY_ORDER_PATHS = frozenset({"/initiate-payment", "/verify", "/settle"})
for _route in app.routes:
    if isinstance(_route, APIRoute) and _route.path in _LEGACY_PATHS:
        _route.description = (
            (_route.description or "")
            + _LEGACY_NOTE
            + (_LEGACY_ORDER_NOTE if _route.path in _LEGACY_ORDER_PATHS else _LEGACY_ORDERS_NOTE if _route.path == "/orders" else "")
        )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

