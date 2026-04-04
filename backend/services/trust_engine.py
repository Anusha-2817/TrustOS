"""
TrustOS — Trust Engine
Computes long-term reputation scores for buyers and sellers.

Formulas (from TrustOS Master Architecture):
  BT = 40 + (2 × SuccessfulOrders) - (15 × DisputeRate%) - (20 × FraudFlags)
  ST = 50 + (1.5 × SuccessfulOrders) - (20 × ComplaintRate%) - (30 × FraudFlags)

Trust Levels:
  0–40   → Low
  41–70  → Medium
  71–100 → High

Buyer Trust Tiers (order count based):
  Level 0 (UNKNOWN):       0–2 orders
  Level 1 (Basic Trust):   3–5 successful orders, dispute rate < threshold
  Level 2 (Trusted):       6–15 successful orders, dispute rate < 10%
  Level 3 (Highly Trusted):15+ successful orders, dispute rate < 5%, no fraud

Seller Trust Tiers:
  Level 0 (New Seller):         0–10 orders
  Level 1 (Emerging Seller):    10–30 orders, complaint rate < 15%
  Level 2 (Trusted Seller):     30–100 orders, complaint rate < 8%
  Level 3 (Highly Trusted):     100+ orders, complaint rate < 3%
"""

from typing import Tuple, Dict, Any
from models import BuyerProfile, SellerProfile


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def trust_level_label(score: float) -> str:
    if score <= 40:
        return "Low"
    elif score <= 70:
        return "Medium"
    else:
        return "High"


class TrustEngine:

    # ─── Buyer Trust ──────────────────────────────────────────────────────────

    def compute_buyer_trust(
        self, profile: BuyerProfile
    ) -> Tuple[float, str, Dict[str, Any]]:
        """
        Returns (score, level_label, breakdown_dict)
        BT = 40 + (2 × SuccessfulOrders) - (15 × DisputeRate%) - (20 × FraudFlags)
        """
        base = 40.0
        order_bonus = 2.0 * profile.successful_orders

        # Dispute rate as a percentage (0–100)
        dispute_rate = (
            (profile.disputes / profile.total_orders * 100)
            if profile.total_orders > 0
            else 0.0
        )
        dispute_penalty = 15.0 * (dispute_rate / 100.0) * 100  # scale for formula
        # The formula uses DisputeRate as a fraction like 10% = 0.10, so:
        # -15 × 0.10 = -1.5 — but from the doc example: 1 dispute in 10 = 10% → -15
        # so DisputeRate% here means the raw percentage number × 1, e.g. 10% → penalty = 15
        dispute_penalty = 15.0 * (dispute_rate / 100.0) * 100 / 100
        # Simplify: penalty = 15 × dispute_rate (where dispute_rate is 0–1 fraction)
        dispute_rate_fraction = profile.disputes / profile.total_orders if profile.total_orders > 0 else 0.0
        dispute_penalty = 15.0 * dispute_rate_fraction * 100  # 15 × rate%
        # Per doc example: 1/10 disputes = 10% → -15. So: -15 × (10/100) × 100 = -15. ✓
        # Simplified: -15 × dispute_rate_percent / 1  where percent is 0–100
        dispute_penalty = 15.0 * (dispute_rate / 100.0) * 100 / 100 * 100
        # Let me just write this cleanly:
        # dispute_rate_percent = (disputes/total) * 100, e.g. 10
        # penalty = dispute_rate_percent (same as the raw %)  × 15 / 100 × 100 = rate × 15
        # from doc: 10% rate → -15. So penalty = rate_percent × (15/10) = rate% × 1.5? No.
        # Actually re-reading: "15 × DisputeRate%" where DisputeRate% = 10 → 15×10 = 150? Too big.
        # Doc example: BT = 40 + 20 - 15 = 45 with 1 dispute in 10 orders (10% rate).
        # So: 15 × DisputeRate must equal 15 when rate=10%. Thus DisputeRate = rate/100.
        # → penalty = 15 × (disputes/total)
        # Coefficient 150 derived from doc example: 1/10 disputes (10%) → penalty = 15
        # Formula: BT = 40 + 2×orders - 150×(disputes/total) - 20×fraud_flags
        dispute_penalty = 150.0 * dispute_rate_fraction
        fraud_penalty = 20.0 * profile.fraud_flags

        raw_score = base + order_bonus - dispute_penalty - fraud_penalty
        score = clamp(raw_score)
        level = trust_level_label(score)

        # Buyer tier classification
        tier = self._buyer_tier(profile, dispute_rate_fraction)

        breakdown = {
            "base": base,
            "order_bonus": round(order_bonus, 2),
            "dispute_rate_percent": round(dispute_rate_fraction * 100, 2),
            "dispute_penalty": round(dispute_penalty, 2),
            "fraud_penalty": round(fraud_penalty, 2),
            "raw_score": round(raw_score, 2),
            "clamped_score": round(score, 2),
            "tier": tier
        }

        return round(score, 2), level, breakdown

    def _buyer_tier(self, profile: BuyerProfile, dispute_rate: float) -> Dict[str, Any]:
        """Classify buyer into trust tier 0–3."""
        s = profile.successful_orders
        has_fraud = profile.fraud_flags > 0

        if s < 3:
            return {"level": 0, "label": "Unknown", "unlocks": ["Medium checks applied"]}
        elif s <= 5 and profile.disputes <= 1 and not has_fraud:
            return {"level": 1, "label": "Basic Trust", "unlocks": ["No video (most cases)", "Passive confirmation"]}
        elif s <= 15 and dispute_rate < 0.10 and not has_fraud:
            return {"level": 2, "label": "Trusted Buyer", "unlocks": ["Direct UPI allowed", "Almost zero friction"]}
        elif s > 15 and dispute_rate < 0.05 and not has_fraud:
            return {"level": 3, "label": "Highly Trusted", "unlocks": ["Instant settlement", "Almost never challenged"]}
        else:
            # Downgrade check
            return {"level": 1, "label": "Basic Trust (Conditional)", "unlocks": ["Elevated monitoring"]}

    # ─── Seller Trust ─────────────────────────────────────────────────────────

    def compute_seller_trust(
        self, profile: SellerProfile
    ) -> Tuple[float, str, Dict[str, Any]]:
        """
        Returns (score, level_label, breakdown_dict)
        ST = 50 + (1.5 × SuccessfulOrders) - (20 × ComplaintRate) - (30 × FraudFlags)
        Sellers have stricter penalties (control inventory → higher responsibility).
        """
        base = 50.0
        order_bonus = 1.5 * profile.successful_orders

        complaint_rate = (
            profile.complaints / profile.total_orders
            if profile.total_orders > 0
            else 0.0
        )
        # Coefficient 200 derived from doc example: 5% complaint rate → penalty = 10
        # Formula: ST = 50 + 1.5×orders - 200×(complaints/total) - 30×fraud_flags
        complaint_penalty = 200.0 * complaint_rate
        fraud_penalty = 30.0 * profile.fraud_flags

        raw_score = base + order_bonus - complaint_penalty - fraud_penalty
        score = clamp(raw_score)
        level = trust_level_label(score)

        tier = self._seller_tier(profile, complaint_rate)

        breakdown = {
            "base": base,
            "order_bonus": round(order_bonus, 2),
            "complaint_rate_percent": round(complaint_rate * 100, 2),
            "complaint_penalty": round(complaint_penalty, 2),
            "fraud_penalty": round(fraud_penalty, 2),
            "raw_score": round(raw_score, 2),
            "clamped_score": round(score, 2),
            "tier": tier
        }

        return round(score, 2), level, breakdown

    def _seller_tier(self, profile: SellerProfile, complaint_rate: float) -> Dict[str, Any]:
        """Classify seller into trust tier 0–3."""
        s = profile.successful_orders
        has_fraud = profile.fraud_flags > 0

        if s < 10:
            return {"level": 0, "label": "New Seller", "note": "Always medium/high risk"}
        elif s < 30 and complaint_rate < 0.15 and not has_fraud:
            return {"level": 1, "label": "Emerging Seller", "note": "Complaint rate < 15%"}
        elif s < 100 and complaint_rate < 0.08 and not has_fraud:
            return {"level": 2, "label": "Trusted Seller", "note": "Complaint rate < 8%"}
        elif s >= 100 and complaint_rate < 0.03 and not has_fraud:
            return {"level": 3, "label": "Highly Trusted Seller", "note": "Complaint rate < 3%"}
        else:
            return {"level": 0, "label": "New/Flagged Seller", "note": "Elevated risk"}