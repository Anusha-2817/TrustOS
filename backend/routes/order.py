from fastapi import APIRouter
from services.schemas import OrderInput
from services.trust_engine import TrustEngine
from services.risk_engine import RiskEngine
from services.decision_engine import DecisionEngine
from services.payment_engine import PaymentEngine
from services.verification_engine import VerificationEngine

router = APIRouter(prefix="/order", tags=["Order"])


@router.post("/create")
def create_order(data: OrderInput):

    buyer = data.buyer
    seller = data.seller

    # Trust
    bt = TrustEngine.calculate_buyer_trust(buyer)
    st = TrustEngine.calculate_seller_trust(seller)

    # Risk
    tr = RiskEngine.transaction_risk(data)
    risk = RiskEngine.final_risk(bt, st, tr)

    # Decision
    decision = DecisionEngine.classify(risk)

    # Payment
    payment = PaymentEngine.process_payment(data, decision)

    # Verification
    verification = VerificationEngine.get_verification_flow(decision)

    return {
        "buyer_trust": bt,
        "seller_trust": st,
        "risk_score": risk,
        "decision": decision,
        "payment_action": payment,
        "verification_type": verification
    }