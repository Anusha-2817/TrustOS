"""
TrustOS — the shared Trust → Risk → Decision pipeline (formerly ``main._run_pipeline``).

Every route that turns a TransactionRequest into a decision goes through ``run_pipeline``, so the
escalate-only product-risk step (``DecisionEngine.decide(..., product_risk=...)``) applies uniformly.
"""

from models import FullEvaluationResponse, TransactionRequest
from services.decision_engine import DecisionEngine
from services.product_risk import assess_product
from services.risk_engine import RiskEngine
from services.trust_engine import TrustEngine

_trust_engine = TrustEngine()
_risk_engine = RiskEngine()
_decision_engine = DecisionEngine()


def run_pipeline(req: TransactionRequest) -> FullEvaluationResponse:
    buyer_trust, buyer_level, buyer_breakdown = _trust_engine.compute_buyer_trust(req.buyer)
    seller_trust, seller_level, seller_breakdown = _trust_engine.compute_seller_trust(req.seller)
    risk_score, risk_components = _risk_engine.compute_risk(
        buyer_trust=buyer_trust,
        seller_trust=seller_trust,
        order_value=req.order_value,
        is_new_pair=req.is_new_pair,
        is_new_device=req.is_new_device,
    )
    # Reported alongside the components but not added into risk_score: it can only escalate the tier.
    product_risk = assess_product(req.product_id)
    risk_components.product_risk = product_risk
    decision = _decision_engine.decide(risk_score, buyer_trust, seller_trust, product_risk=product_risk)
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
