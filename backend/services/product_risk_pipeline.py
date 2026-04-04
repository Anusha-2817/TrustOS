"""
TrustOS — Advanced product evaluation pipeline for POST /evaluate-product.

Computes BT/ST, structured risk components, LLM behavior signals, and final decision.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from models import BuyerProfile, SellerProfile
from services.decision_engine import DecisionEngine
from services.llm_risk_signals import LlmRiskAssessment, assess_with_llm
from services.risk_engine import RiskEngine
from services.trust_engine import TrustEngine


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def trust_risk_from_scores(bt: float, st: float) -> float:
    """
    Risk contribution from distrust: higher when BT/ST are low.
    Both at 100 → 0; both at 0 → 50 (capped contribution).
    """
    raw = ((100.0 - bt) + (100.0 - st)) / 4.0
    return round(clamp(raw, 0.0, 60.0), 2)


def context_risk_flags(is_new_interaction: bool, new_device: bool) -> float:
    interaction = 20.0 if is_new_interaction else 0.0
    device = 10.0 if new_device else 0.0
    return round(interaction + device, 2)


def behavior_risk_formula(signals_count: int, confidence: float) -> float:
    """behavior_risk = len(signals)*7 + confidence*10"""
    return round(signals_count * 7.0 + confidence * 10.0, 2)


def profiles_from_product_request(
    buyer_orders: int,
    buyer_disputes: int,
    seller_orders: int,
    seller_complaints: int,
) -> Tuple[BuyerProfile, SellerProfile]:
    buyer_total = max(buyer_orders + buyer_disputes, buyer_orders, 1)
    seller_total = max(seller_orders + seller_complaints, seller_orders, 1)
    buyer = BuyerProfile(
        successful_orders=buyer_orders,
        total_orders=buyer_total,
        disputes=buyer_disputes,
        fraud_flags=0,
    )
    seller = SellerProfile(
        successful_orders=seller_orders,
        total_orders=seller_total,
        complaints=seller_complaints,
        fraud_flags=0,
    )
    return buyer, seller


class ProductRiskPipeline:
    def __init__(self) -> None:
        self._trust = TrustEngine()
        self._risk = RiskEngine()
        self._decision = DecisionEngine()

    def evaluate(
        self,
        product_name: str,
        product_price: float,
        seller_orders: int,
        seller_complaints: int,
        buyer_orders: int,
        buyer_disputes: int,
        review_summary: str,
        is_new_interaction: bool,
        new_device: bool,
    ) -> Dict[str, Any]:
        buyer, seller = profiles_from_product_request(
            buyer_orders, buyer_disputes, seller_orders, seller_complaints
        )

        bt, bt_level, bt_breakdown = self._trust.compute_buyer_trust(buyer)
        st, st_level, st_breakdown = self._trust.compute_seller_trust(seller)

        trust_risk = trust_risk_from_scores(bt, st)
        value_risk = self._risk.value_risk_for_amount(product_price)
        context_risk = context_risk_flags(is_new_interaction, new_device)

        llm: LlmRiskAssessment
        llm_source: str
        llm, llm_source = assess_with_llm(
            product_name=product_name,
            review_summary=review_summary,
            seller_complaints=seller_complaints,
            buyer_disputes=buyer_disputes,
        )

        behavior_risk = behavior_risk_formula(len(llm.signals), llm.confidence)
        risk_modifier = float(llm.risk_modifier)

        components_sum = (
            trust_risk + value_risk + context_risk + behavior_risk + risk_modifier
        )
        final_risk = round(clamp(components_sum, 0.0, 100.0), 2)

        decision = self._decision.decide(final_risk, bt, st)

        breakdown = {
            "trust_risk": trust_risk,
            "value_risk": value_risk,
            "context_risk": context_risk,
            "behavior_risk": behavior_risk,
            "llm_risk_modifier": int(llm.risk_modifier),
            "components_raw_sum": round(components_sum, 2),
            "final_risk": final_risk,
        }

        return {
            "buyer_trust": bt,
            "buyer_trust_level": bt_level,
            "buyer_breakdown": bt_breakdown,
            "seller_trust": st,
            "seller_trust_level": st_level,
            "seller_breakdown": st_breakdown,
            "risk_breakdown": breakdown,
            "llm_signals": llm.signals,
            "llm_risk_modifier": llm.risk_modifier,
            "llm_source": llm_source,
            "confidence": llm.confidence,
            "final_risk": final_risk,
            "decision": decision.risk_classification,
            "decision_detail": decision,
        }
