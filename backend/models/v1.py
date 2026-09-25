"""Request / response models of the versioned public API (``/v1``, Phase 5a).

They are separate from the legacy demo models on purpose: a /v1 shape is a contract, so internal changes must
not leak into it. (``POST /v1/orders`` and ``POST /v1/risk/evaluate`` still return the shared
``OrderResponse`` / ``FullEvaluationResponse``, whose shape is pinned by tests.)
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

MAX_DETAILS_BYTES = 16 * 1024


class V1VerificationRequest(BaseModel):
    """POST /v1/orders/{order_id}/verification"""

    result: Literal["SUCCESS", "FRAUD", "INCONSISTENT"] = Field(..., description="Outcome of the buyer-side check")
    details: Optional[Dict[str, Any]] = Field(None, description="Type-specific evidence, stored as given (max 16 KB serialised)")

    @field_validator("details")
    @classmethod
    def _details_not_huge(cls, v):
        if v is not None and len(json.dumps(v)) > MAX_DETAILS_BYTES:
            raise ValueError(f"details must be at most {MAX_DETAILS_BYTES} bytes when serialised")
        return v


class V1SettlementRequest(BaseModel):
    """POST /v1/orders/{order_id}/settlement"""

    action: Literal["capture", "release", "cancel"] = Field(
        ..., description="capture / cancel an AUTHORIZED payment (MEDIUM); release / cancel a HELD one (HIGH). "
        "A capture or a release also needs the latest verification to be SUCCESS."
    )


class V1Payment(BaseModel):
    payment_id: UUID
    route: Literal["DIRECT_CAPTURE", "AUTHORIZE_ONLY", "WALLET_HOLD"]
    status: Literal["AUTHORIZED", "HELD", "CAPTURED", "RELEASED", "CANCELLED", "REFUNDED"]
    triggered_by: Literal["MANUAL", "AUTO", "TIMEOUT"] = Field(..., description="What caused the latest status change")
    amount: float
    currency: str
    authorized_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None


class V1Verification(BaseModel):
    verification_id: UUID
    type: Literal["PASSIVE", "USER_CONFIRMATION", "MANDATORY_VIDEO"]
    result: Literal["PENDING", "SUCCESS", "ISSUE", "FRAUD", "INCONSISTENT", "NO_RESPONSE"]
    details: Optional[Dict[str, Any]] = None
    requested_at: datetime
    completed_at: Optional[datetime] = None


class V1OrderView(BaseModel):
    """GET /v1/orders/{order_id}"""

    order_id: UUID
    status: Literal["CREATED", "ACTIVE", "COMPLETED", "CANCELLED"]
    buyer_id: str
    seller_id: str
    product_id: Optional[str] = None
    amount: float
    currency: str
    risk_score: Optional[float] = None
    risk_tier: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None
    created_at: datetime
    updated_at: datetime
    payment: Optional[V1Payment] = Field(None, description="The order's latest payment; null until one is initiated")
    verifications: List[V1Verification] = Field(default_factory=list, description="Oldest first; a retry is a further row")


class V1PaymentStarted(BaseModel):
    """POST /v1/orders/{order_id}/payment"""

    order_id: UUID
    order_status: Literal["CREATED", "ACTIVE", "COMPLETED", "CANCELLED"]
    payment: V1Payment
    verification: V1Verification = Field(..., description="The verification the tier requires; PENDING until it is reported")


class V1VerificationRecorded(BaseModel):
    """POST /v1/orders/{order_id}/verification"""

    order_id: UUID
    order_status: Literal["CREATED", "ACTIVE", "COMPLETED", "CANCELLED"]
    verification: V1Verification


class V1Settled(BaseModel):
    """POST /v1/orders/{order_id}/settlement"""

    order_id: UUID
    order_status: Literal["CREATED", "ACTIVE", "COMPLETED", "CANCELLED"]
    payment: V1Payment


def payment_view(row: Dict[str, Any]) -> V1Payment:
    return V1Payment(
        payment_id=row["payment_id"],
        route=row["route"],
        status=row["status"],
        triggered_by=row["triggered_by"],
        amount=float(row["amount"]),
        currency=row["currency"],
        authorized_at=row["authorized_at"],
        settled_at=row["settled_at"],
    )


def verification_view(row: Dict[str, Any]) -> V1Verification:
    return V1Verification(
        verification_id=row["verification_id"],
        type=row["type"],
        result=row["result"],
        details=row["details"],
        requested_at=row["requested_at"],
        completed_at=row["completed_at"],
    )
