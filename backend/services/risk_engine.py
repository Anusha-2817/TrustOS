"""
TrustOS — Risk Engine
Computes a per-transaction Risk Score combining trust scores with transaction signals.

Formula:
  Risk = 100 - (0.4 × BT) - (0.4 × ST) + TransactionRisk

  TransactionRisk = ValueRisk + InteractionRisk + ContextRisk

  ValueRisk:
    < ₹3,000  → +5
    ₹3K–10K   → +15
    > ₹10,000 → +25

  InteractionRisk:
    New buyer↔seller pair → +20
    Known pair            → 0

  ContextRisk:
    New device/location → +10
    Normal              → 0

Decision Bands:
  0–30  → LOW RISK
  31–60 → MEDIUM RISK
  61+   → HIGH RISK
"""

from typing import Tuple, Dict
from models import RiskComponentsModel


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class RiskEngine:

    # Value risk thresholds (in INR)
    VALUE_THRESHOLDS = [
        (3_000, 5),
        (10_000, 15),
        (float("inf"), 25),
    ]

    def compute_risk(
        self,
        buyer_trust: float,
        seller_trust: float,
        order_value: float,
        is_new_pair: bool,
        is_new_device: bool,
    ) -> Tuple[float, RiskComponentsModel]:
        """
        Returns (risk_score, components_breakdown)
        """
        base = 100.0

        # Trust reductions
        buyer_reduction = 0.4 * buyer_trust
        seller_reduction = 0.4 * seller_trust

        # Transaction risk components
        value_risk = self._value_risk(order_value)
        interaction_risk = 20.0 if is_new_pair else 0.0
        context_risk = 10.0 if is_new_device else 0.0
        transaction_risk = value_risk + interaction_risk + context_risk

        raw_risk = base - buyer_reduction - seller_reduction + transaction_risk
        final_risk = clamp(raw_risk)

        components = RiskComponentsModel(
            base=base,
            buyer_trust_reduction=round(buyer_reduction, 2),
            seller_trust_reduction=round(seller_reduction, 2),
            value_risk=value_risk,
            interaction_risk=interaction_risk,
            context_risk=context_risk,
            transaction_risk_total=round(transaction_risk, 2),
        )

        return round(final_risk, 2), components

    def value_risk_for_amount(self, order_value: float) -> float:
        """Public helper: INR order value → value-risk points (5 / 15 / 25)."""
        return float(self._value_risk(order_value))

    def _value_risk(self, order_value: float) -> float:
        """Map order value to a risk point addition."""
        for threshold, points in self.VALUE_THRESHOLDS:
            if order_value <= threshold:
                return float(points)
        return 25.0  # fallback for very large values

    def classify(self, risk_score: float) -> str:
        """Classify a risk score into LOW / MEDIUM / HIGH."""
        if risk_score <= 30:
            return "LOW"
        elif risk_score <= 60:
            return "MEDIUM"
        else:
            return "HIGH"