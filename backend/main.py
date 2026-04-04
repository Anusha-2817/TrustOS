from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from services.trust_engine import TrustEngine
from services.risk_engine import RiskEngine
from services.decision_engine import DecisionEngine
from models import (
    BuyerProfile, SellerProfile, TransactionRequest,
    TrustScoreResponse, RiskScoreResponse, DecisionModel,
    FullEvaluationResponse, SimulatorEvaluateRequest,
    EvaluateProductRequest,
)

app = FastAPI(
    title="TrustOS API",
    description="Trust enforcement layer for e-commerce: Trust Engine, Risk Engine, Decision Engine",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

trust_engine = TrustEngine()
risk_engine = RiskEngine()
decision_engine = DecisionEngine()


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
    response_model=EvaluateProductRequest,
    tags=["Risk Engine"],
)
def evaluate_product(body: EvaluateProductRequest):
    """Echo validated product evaluation input (minimal contract)."""
    return body


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
    return _run_pipeline(req)


@app.post("/decision/evaluate", response_model=FullEvaluationResponse, tags=["Decision Engine"])
def evaluate_transaction(request: TransactionRequest):
    """
    Full pipeline: Trust → Risk → Decision.
    Returns trust scores, risk score, risk classification, and enforcement actions.
    """
    # Step 1: Trust Scores
    buyer_trust, buyer_level, buyer_breakdown = trust_engine.compute_buyer_trust(request.buyer)
    seller_trust, seller_level, seller_breakdown = trust_engine.compute_seller_trust(request.seller)

    # Step 2: Risk Score
    risk_score, risk_components = risk_engine.compute_risk(
        buyer_trust=buyer_trust,
        seller_trust=seller_trust,
        order_value=request.order_value,
        is_new_pair=request.is_new_pair,
        is_new_device=request.is_new_device
    )

    # Step 3: Decision
    decision = decision_engine.decide(risk_score, buyer_trust, seller_trust)

    return FullEvaluationResponse(
        buyer_trust=buyer_trust,
        buyer_trust_level=buyer_level,
        buyer_breakdown=buyer_breakdown,
        seller_trust=seller_trust,
        seller_trust_level=seller_level,
        seller_breakdown=seller_breakdown,
        risk_score=risk_score,
        risk_components=risk_components,
        decision=decision
    )


# ─── Simulation Endpoint ─────────────────────────────────────────────────────

@app.get("/simulate/{scenario}", tags=["Demo"])
def simulate_scenario(scenario: str):
    """
    Run a pre-built demo scenario.
    Options: low_risk | medium_risk | high_risk
    """
    scenarios = {
        "low_risk": TransactionRequest(
            buyer=BuyerProfile(successful_orders=12, total_orders=13, disputes=1, fraud_flags=0),
            seller=SellerProfile(successful_orders=55, total_orders=58, complaints=2, fraud_flags=0),
            order_value=1500,
            is_new_pair=False,
            is_new_device=False
        ),
        "medium_risk": TransactionRequest(
            buyer=BuyerProfile(successful_orders=5, total_orders=6, disputes=1, fraud_flags=0),
            seller=SellerProfile(successful_orders=25, total_orders=28, complaints=3, fraud_flags=0),
            order_value=5000,
            is_new_pair=True,
            is_new_device=False
        ),
        "high_risk": TransactionRequest(
            buyer=BuyerProfile(successful_orders=1, total_orders=2, disputes=1, fraud_flags=0),
            seller=SellerProfile(successful_orders=5, total_orders=8, complaints=2, fraud_flags=0),
            order_value=12000,
            is_new_pair=True,
            is_new_device=True
        )
    }

    if scenario not in scenarios:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario}' not found. Choose: low_risk, medium_risk, high_risk")

    req = scenarios[scenario]
    buyer_trust, buyer_level, buyer_breakdown = trust_engine.compute_buyer_trust(req.buyer)
    seller_trust, seller_level, seller_breakdown = trust_engine.compute_seller_trust(req.seller)
    risk_score, risk_components = risk_engine.compute_risk(
        buyer_trust=buyer_trust,
        seller_trust=seller_trust,
        order_value=req.order_value,
        is_new_pair=req.is_new_pair,
        is_new_device=req.is_new_device
    )
    decision = decision_engine.decide(risk_score, buyer_trust, seller_trust)

    return FullEvaluationResponse(
        buyer_trust=buyer_trust,
        buyer_trust_level=buyer_level,
        buyer_breakdown=buyer_breakdown,
        seller_trust=seller_trust,
        seller_trust_level=seller_level,
        seller_breakdown=seller_breakdown,
        risk_score=risk_score,
        risk_components=risk_components,
        decision=decision
    )


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "service": "TrustOS API v1.0.0"}


# ─── Demo contract aliases (frontend-friendly) ──────────────────────────────
# Maps existing Trust/Risk/Decision pipeline to the hackathon UI contract.

SCENARIO_KEYS = frozenset({"low_risk", "medium_risk", "high_risk"})


def _transaction_for_scenario(scenario: str) -> TransactionRequest:
    scenarios = {
        "low_risk": TransactionRequest(
            buyer=BuyerProfile(successful_orders=12, total_orders=13, disputes=1, fraud_flags=0),
            seller=SellerProfile(successful_orders=55, total_orders=58, complaints=2, fraud_flags=0),
            order_value=1500,
            is_new_pair=False,
            is_new_device=False,
        ),
        "medium_risk": TransactionRequest(
            buyer=BuyerProfile(successful_orders=5, total_orders=6, disputes=1, fraud_flags=0),
            seller=SellerProfile(successful_orders=25, total_orders=28, complaints=3, fraud_flags=0),
            order_value=5000,
            is_new_pair=True,
            is_new_device=False,
        ),
        "high_risk": TransactionRequest(
            buyer=BuyerProfile(successful_orders=1, total_orders=2, disputes=1, fraud_flags=0),
            seller=SellerProfile(successful_orders=5, total_orders=8, complaints=2, fraud_flags=0),
            order_value=12000,
            is_new_pair=True,
            is_new_device=True,
        ),
    }
    if scenario not in scenarios:
        raise HTTPException(
            status_code=404,
            detail="Unknown scenario. Use: low_risk, medium_risk, high_risk",
        )
    return scenarios[scenario]


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


def _run_pipeline(req: TransactionRequest) -> FullEvaluationResponse:
    buyer_trust, buyer_level, buyer_breakdown = trust_engine.compute_buyer_trust(req.buyer)
    seller_trust, seller_level, seller_breakdown = trust_engine.compute_seller_trust(req.seller)
    risk_score, risk_components = risk_engine.compute_risk(
        buyer_trust=buyer_trust,
        seller_trust=seller_trust,
        order_value=req.order_value,
        is_new_pair=req.is_new_pair,
        is_new_device=req.is_new_device,
    )
    decision = decision_engine.decide(risk_score, buyer_trust, seller_trust)
    return FullEvaluationResponse(
        buyer_trust=buyer_trust,
        buyer_trust_level=buyer_level,
        buyer_breakdown=buyer_breakdown,
        seller_trust=seller_trust,
        seller_trust_level=seller_level,
        seller_breakdown=seller_breakdown,
        risk_score=risk_score,
        risk_components=risk_components,
        decision=decision,
    )


class InitiatePaymentBody(BaseModel):
    scenario: Optional[str] = "medium_risk"


class VerifyBody(BaseModel):
    """Demo-only: drive outcome for the jury."""
    passed: bool = True
    inconsistent: bool = False


class SettleBody(BaseModel):
    """Demo-only: which settlement path to show."""
    action: str = "capture"  # capture | release | cancel


@app.get("/evaluate-risk", tags=["Demo Contract"])
def evaluate_risk_contract(scenario: str = "medium_risk"):
    """{ riskLevel, riskScore } — aligns UI gauge with backend."""
    req = _transaction_for_scenario(scenario)
    full = _run_pipeline(req)
    rc = full.decision.risk_classification
    return {"riskLevel": rc, "riskScore": round(full.risk_score, 2)}


def _payment_lifecycle_payload(full: FullEvaluationResponse) -> dict:
    """Razorpay-style phase labels for settlement UI (demo)."""
    band = full.decision.risk_classification
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
    full = _run_pipeline(_transaction_for_scenario(scenario))
    return _payment_lifecycle_payload(full)


@app.post("/initiate-payment", tags=["Demo Contract"])
def initiate_payment_contract(body: InitiatePaymentBody = InitiatePaymentBody()):
    """{ status, lifecycle } — gateway simulation for UI."""
    scenario = body.scenario or "medium_risk"
    if scenario not in SCENARIO_KEYS:
        raise HTTPException(status_code=400, detail="scenario must be low_risk | medium_risk | high_risk")
    full = _run_pipeline(_transaction_for_scenario(scenario))
    band = full.decision.risk_classification
    status_map = {"LOW": "CAPTURED", "MEDIUM": "AUTHORIZED", "HIGH": "HELD"}
    lifecycle = _payment_lifecycle_payload(full)
    return {
        "status": status_map.get(band, "AUTHORIZED"),
        "lifecycle": lifecycle,
    }


@app.post("/verify", tags=["Demo Contract"])
def verify_contract(body: VerifyBody = VerifyBody()):
    """{ result: SUCCESS | FRAUD | INCONSISTENT } — demo toggles."""
    if body.inconsistent:
        return {"result": "INCONSISTENT"}
    if body.passed:
        return {"result": "SUCCESS"}
    return {"result": "FRAUD"}


@app.post("/settle", tags=["Demo Contract"])
def settle_contract(body: SettleBody = SettleBody()):
    """{ status: CAPTURED | RELEASED | CANCELLED } — demo toggles."""
    action = (body.action or "capture").lower().strip()
    m = {"capture": "CAPTURED", "release": "RELEASED", "cancel": "CANCELLED"}
    if action not in m:
        raise HTTPException(status_code=400, detail="action must be capture | release | cancel")
    return {"status": m[action]}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)