"""
TrustOS — order-mode policy (Phase 4): how a decision tier maps onto persisted payment / verification /
order state. Pure functions and tables, no I/O, so the rules are testable without a database.

Stateless demo mode (no ``order_id``) never touches this module.
"""

from typing import Optional

from services.verification_engine import VerificationEngine

# What /initiate-payment produces per tier. These are the same statuses the stateless route returns
# (main.py used to hold this table inline).
INITIAL_PAYMENT_STATUS = {"LOW": "CAPTURED", "MEDIUM": "AUTHORIZED", "HIGH": "HELD"}

# Which money path the tier takes (PaymentEngine: CAPTURE / AUTHORIZE / WALLET_HOLD).
PAYMENT_ROUTE = {"LOW": "DIRECT_CAPTURE", "MEDIUM": "AUTHORIZE_ONLY", "HIGH": "WALLET_HOLD"}

# /settle's action → resulting payment status (unchanged from the stateless route).
SETTLE_ACTION_STATUS = {"capture": "CAPTURED", "release": "RELEASED", "cancel": "CANCELLED"}

# Order-mode /settle only moves a payment that is still waiting on TrustOS: an AUTHORIZED payment
# (MEDIUM) is captured or cancelled, a HELD one (HIGH) is released or cancelled. Anything else (capturing
# a wallet hold, settling twice, settling an instant-captured LOW payment) is a 409, not a silent overwrite.
ALLOWED_SETTLEMENTS = frozenset(
    {
        ("AUTHORIZED", "CAPTURED"),
        ("AUTHORIZED", "CANCELLED"),
        ("HELD", "RELEASED"),
        ("HELD", "CANCELLED"),
    }
)

_PAYMENT_TO_ORDER_STATUS = {
    "AUTHORIZED": "ACTIVE",
    "HELD": "ACTIVE",
    "CAPTURED": "COMPLETED",
    "RELEASED": "COMPLETED",
    "CANCELLED": "CANCELLED",
    "REFUNDED": "CANCELLED",
}


def order_status_for_payment(payment_status: Optional[str]) -> str:
    """The order's status is derived from its payment: no payment → CREATED; waiting on TrustOS → ACTIVE;
    money delivered to the seller → COMPLETED; money returned / never moved → CANCELLED."""
    return "CREATED" if payment_status is None else _PAYMENT_TO_ORDER_STATUS[payment_status]


def verification_type_for_tier(tier: str) -> str:
    """PASSIVE / USER_CONFIRMATION / MANDATORY_VIDEO (VerificationEngine, whose values match the DB vocabulary)."""
    return VerificationEngine.get_verification_flow(tier)
