from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, Literal


# ─── Input Models ────────────────────────────────────────────────────────────

class BuyerProfile(BaseModel):
    successful_orders: int = Field(..., ge=0, description="Number of completed orders without dispute")
    total_orders: int = Field(..., ge=0, description="Total orders placed")
    disputes: int = Field(0, ge=0, description="Number of disputes raised")
    fraud_flags: int = Field(0, ge=0, description="Number of confirmed fraud flags")

    @validator("total_orders")
    def total_gte_successful(cls, v, values):
        if "successful_orders" in values and v < values["successful_orders"]:
            raise ValueError("total_orders must be >= successful_orders")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "successful_orders": 12,
                "total_orders": 13,
                "disputes": 1,
                "fraud_flags": 0
            }
        }


class SellerProfile(BaseModel):
    successful_orders: int = Field(..., ge=0, description="Completed orders without complaint")
    total_orders: int = Field(..., ge=0, description="Total orders fulfilled")
    complaints: int = Field(0, ge=0, description="Number of complaints received")
    fraud_flags: int = Field(0, ge=0, description="Confirmed fraud incidents")

    @validator("total_orders")
    def total_gte_successful(cls, v, values):
        if "successful_orders" in values and v < values["successful_orders"]:
            raise ValueError("total_orders must be >= successful_orders")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "successful_orders": 55,
                "total_orders": 58,
                "complaints": 2,
                "fraud_flags": 0
            }
        }


class TransactionRequest(BaseModel):
    buyer: BuyerProfile
    seller: SellerProfile
    order_value: float = Field(..., gt=0, description="Order value in INR")
    is_new_pair: bool = Field(False, description="First transaction between this buyer-seller pair")
    is_new_device: bool = Field(False, description="Unusual device or location detected")

    class Config:
        json_schema_extra = {
            "example": {
                "buyer": {"successful_orders": 12, "total_orders": 13, "disputes": 1, "fraud_flags": 0},
                "seller": {"successful_orders": 55, "total_orders": 58, "complaints": 2, "fraud_flags": 0},
                "order_value": 1500,
                "is_new_pair": False,
                "is_new_device": False
            }
        }


# ─── Output Models ────────────────────────────────────────────────────────────

class TrustScoreResponse(BaseModel):
    score: float = Field(..., description="Trust score clamped 0–100")
    level: str = Field(..., description="Trust level: Low | Medium | High")
    entity_type: str = Field(..., description="buyer or seller")
    breakdown: Dict[str, Any] = Field(..., description="Score component breakdown")


class RiskComponentsModel(BaseModel):
    base: float
    buyer_trust_reduction: float
    seller_trust_reduction: float
    value_risk: float
    interaction_risk: float
    context_risk: float
    transaction_risk_total: float


class RiskScoreResponse(BaseModel):
    risk_score: float = Field(..., description="Final risk score 0–100")
    buyer_trust: float
    seller_trust: float
    components: RiskComponentsModel


class DecisionModel(BaseModel):
    risk_classification: str = Field(..., description="LOW | MEDIUM | HIGH")
    risk_range: str
    payment_action: str
    delivery_control: str
    verification_type: str
    settlement_mechanism: str
    trustos_role: str
    safety_window: Optional[str]
    enforcement_actions: list[str]
    money_flow: str
    killer_line: str


class FullEvaluationResponse(BaseModel):
    buyer_trust: float
    buyer_trust_level: str
    buyer_breakdown: Dict[str, Any]
    seller_trust: float
    seller_trust_level: str
    seller_breakdown: Dict[str, Any]
    risk_score: float
    risk_components: RiskComponentsModel
    decision: DecisionModel


class SimulatorEvaluateRequest(BaseModel):
    """What-if inputs for the risk simulator (slider panel). Maps to TransactionRequest."""

    buyer_successful_orders: int = Field(12, ge=0, le=500)
    buyer_dispute_rate_percent: float = Field(5, ge=0, le=100)
    buyer_fraud_flags: int = Field(0, ge=0, le=20)
    seller_successful_orders: int = Field(40, ge=0, le=500)
    seller_complaint_rate_percent: float = Field(5, ge=0, le=100)
    seller_fraud_flags: int = Field(0, ge=0, le=20)
    order_value_inr: float = Field(5500, gt=0, le=2_000_000)
    is_new_pair: bool = False
    is_new_device: bool = False


# ─── Advanced product evaluation (LLM-augmented) ─────────────────────────────


class EvaluateProductRequest(BaseModel):
    """POST /evaluate-product — request body; response echoes the same fields."""

    product_name: str = Field(..., min_length=1, max_length=500)
    product_price: float = Field(..., gt=0, le=10_000_000)
    seller_orders: int = Field(..., ge=0, le=1_000_000)
    seller_complaints: int = Field(0, ge=0, le=1_000_000)
    buyer_orders: int = Field(..., ge=0, le=1_000_000)
    buyer_disputes: int = Field(0, ge=0, le=1_000_000)
    review_summary: str = Field("", max_length=20_000)
    is_new_interaction: bool = Field(False, description="First-time buyer–seller pair")
    new_device: bool = Field(False, description="Unrecognized device / session context")

    class Config:
        json_schema_extra = {
            "example": {
                "product_name": "Wireless earbuds Pro",
                "product_price": 4999,
                "seller_orders": 120,
                "seller_complaints": 4,
                "buyer_orders": 8,
                "buyer_disputes": 1,
                "review_summary": "Mixed reviews; some mention delayed shipping.",
                "is_new_interaction": True,
                "new_device": False,
            }
        }


class ProductEvaluateRiskBreakdown(BaseModel):
    """Component risks before clamp; final_risk = clamp(trust_risk + value_risk + context_risk)."""

    trust_risk: float = Field(..., description="100 − 0.4×BT − 0.4×ST (same as base_risk)")
    value_risk: float = Field(..., description="INR price band add-on (5 / 15 / 25)")
    context_risk: float = Field(
        ...,
        description="New buyer–seller pair (+20) + new device (+10)",
    )


class EvaluateProductResponse(EvaluateProductRequest):
    """POST /evaluate-product — full structured evaluation."""

    buyer_trust: float = Field(..., description="Buyer Trust Score (BT), clamped 0–100")
    seller_trust: float = Field(..., description="Seller Trust Score (ST), clamped 0–100")
    base_risk: float = Field(..., description="Trust-only risk: 100 − 0.4×BT − 0.4×ST")
    risk_breakdown: ProductEvaluateRiskBreakdown
    final_risk: float = Field(
        ...,
        description="Clamp 0–100: pre-behavior risk + behavior_risk (LLM-derived)",
    )
    decision: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        ...,
        description="LOW ≤30, MEDIUM ≤60, HIGH otherwise (same bands as RiskEngine)",
    )
    signals: list[str] = Field(
        ...,
        description="LLM risk/trust signal labels (empty on fallback)",
    )
    risk_modifier: float = Field(
        ...,
        description="LLM risk_modifier from JSON (0 on error fallback)",
    )
    confidence: float = Field(
        ...,
        description="LLM confidence 0–1 (0.5 on error fallback)",
    )
    behavior_risk: float = Field(
        ...,
        description="len(signals)×7 + confidence×10",
    )