"""
TrustOS — Decision Engine
Maps a computed Risk Score to a concrete enforcement decision and money flow.

Risk Bands:
  0–30   → LOW RISK    → Passive, instant settlement
  31–60  → MEDIUM RISK → Delayed capture, user-triggered confirmation
  61–100 → HIGH RISK   → Wallet-based hold, guided unboxing, strict verification

Key TrustOS interception points:
  1. Before Payment  → Risk classification
  2. During Payment  → Authorization / wallet routing
  3. At Delivery     → Enforcement rules (high risk only)
  4. Before Settlement → Final decision: capture | cancel | release
"""

from models import DecisionModel
from services.risk_engine import RiskEngine

_risk_engine = RiskEngine()


class DecisionEngine:

    def decide(
        self,
        risk_score: float,
        buyer_trust: float,
        seller_trust: float,
    ) -> DecisionModel:
        classification = _risk_engine.classify(risk_score)

        if classification == "LOW":
            return self._low_risk_decision(risk_score)
        elif classification == "MEDIUM":
            return self._medium_risk_decision(risk_score)
        else:
            return self._high_risk_decision(risk_score)

    # ─── Low Risk ─────────────────────────────────────────────────────────────

    def _low_risk_decision(self, risk_score: float) -> DecisionModel:
        return DecisionModel(
            risk_classification="LOW",
            risk_range="0–30",
            payment_action="Immediate authorization + capture",
            delivery_control="No restrictions — standard delivery",
            verification_type="Passive (silent window only)",
            settlement_mechanism="Instant settlement to seller",
            trustos_role="Observer only — no active intervention",
            safety_window="30–60 minutes post-delivery (silent)",
            enforcement_actions=[
                "Log transaction with risk score",
                "Attach silent protection window (30–60 min)",
                "If no issue reported → auto-confirm settlement",
                "Update trust scores on completion"
            ],
            money_flow="Buyer → Gateway → Seller (normal flow). TrustOS only observes.",
            killer_line="When trust is high, TrustOS stays invisible."
        )

    # ─── Medium Risk ──────────────────────────────────────────────────────────

    def _medium_risk_decision(self, risk_score: float) -> DecisionModel:
        return DecisionModel(
            risk_classification="MEDIUM",
            risk_range="31–60",
            payment_action="Authorization only — capture DELAYED",
            delivery_control="Flexible — unattended drop allowed",
            verification_type="User-triggered: tap 'I received my order'",
            settlement_mechanism="Capture on user confirmation OR timeout (2–6 hrs)",
            trustos_role="Light control — delays settlement, not payment",
            safety_window="2–6 hours after user confirms delivery",
            enforcement_actions=[
                "Authorize payment (block funds at gateway)",
                "Do NOT capture immediately",
                "Await user delivery confirmation tap",
                "Start 2–6 hour window after confirmation",
                "CASE correct: send CAPTURE → seller",
                "CASE wrong item: block capture, flag seller",
                "CASE dislike (subjective): capture proceeds, log soft complaint",
                "CASE timeout: auto-CAPTURE → seller",
                "Update trust & risk models"
            ],
            money_flow=(
                "Day 0: Buyer → AUTH → Gateway (money blocked, not with seller).\n"
                "After delivery + confirmation: IF OK → CAPTURE → Seller | "
                "IF Wrong → CANCEL → Buyer | IF Dislike → CAPTURE → Seller."
            ),
            killer_line="We don't control the transaction.. we control the moment of settlement."
        )

    # ─── High Risk ────────────────────────────────────────────────────────────

    def _high_risk_decision(self, risk_score: float) -> DecisionModel:
        return DecisionModel(
            risk_classification="HIGH",
            risk_range="61–100",
            payment_action="Funds routed to wallet holding layer (NOT to seller)",
            delivery_control="Controlled delivery — OTP required, no unattended drop",
            verification_type="Mandatory guided unboxing video (continuous, no cuts)",
            settlement_mechanism="RELEASE wallet → seller only after verified delivery",
            trustos_role="Full control — takes over payment path and verification",
            safety_window="15–30 minute strict window post-delivery",
            enforcement_actions=[
                "Route payment: Buyer → Wallet (e.g. Paytm) — seller gets ₹0 initially",
                "TrustOS holds release authority over wallet",
                "Enforce attended delivery with OTP-based handoff",
                "Require seller to attach QR seal + pack properly",
                "Trigger guided unboxing: sealed package → QR/seal → continuous opening → product inside",
                "No cuts allowed in verification video",
                "CASE correct + video consistent: RELEASE wallet → seller",
                "CASE wrong item / scam: DO NOT release — seller gets ₹0, buyer refunded",
                "CASE buyer attempts cheat: check seal continuity + video consistency + history; reject claim",
                "CASE no video in window (15–30 min): auto-release",
                "Heavy trust penalty applied to fraudulent party"
            ],
            money_flow=(
                "Step 1: Buyer → Wallet (money held, seller gets ₹0).\n"
                "Step 2: Delivery + Verification.\n"
                "IF OK → Wallet → Seller (RELEASE).\n"
                "IF Fraud → Wallet → Buyer (no release to seller)."
            ),
            killer_line="Money doesn't move until trust is proven !"
        )