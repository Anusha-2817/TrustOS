"""Request fixtures shared by the characterization and escalation tests."""

# Same three transactions as main.py's built-in low/medium/high scenarios.
TRANSACTIONS = {
    "low_risk": {
        "buyer": {"successful_orders": 12, "total_orders": 13, "disputes": 1, "fraud_flags": 0},
        "seller": {"successful_orders": 55, "total_orders": 58, "complaints": 2, "fraud_flags": 0},
        "order_value": 1500,
        "is_new_pair": False,
        "is_new_device": False,
    },
    "medium_risk": {
        "buyer": {"successful_orders": 5, "total_orders": 6, "disputes": 1, "fraud_flags": 0},
        "seller": {"successful_orders": 25, "total_orders": 28, "complaints": 3, "fraud_flags": 0},
        "order_value": 5000,
        "is_new_pair": True,
        "is_new_device": False,
    },
    "high_risk": {
        "buyer": {"successful_orders": 1, "total_orders": 2, "disputes": 1, "fraud_flags": 0},
        "seller": {"successful_orders": 5, "total_orders": 8, "complaints": 2, "fraud_flags": 0},
        "order_value": 12000,
        "is_new_pair": True,
        "is_new_device": True,
    },
    # main.py's "low_risk" scenario actually scores 44.02 = MEDIUM, so it can't exercise the LOW
    # branch. This one does (25.0 = LOW); it mirrors SIMULATOR_INPUTS["trusted"].
    "trusted": {
        "buyer": {"successful_orders": 200, "total_orders": 200, "disputes": 0, "fraud_flags": 0},
        "seller": {"successful_orders": 400, "total_orders": 404, "complaints": 4, "fraud_flags": 0},
        "order_value": 900,
        "is_new_pair": False,
        "is_new_device": False,
    },
}

# The frontend's demo payloads for POST /evaluate-product (frontend/src/data/trustosDemoTransactions.js).
PRODUCT_EVALUATIONS = {
    "low_risk": {
        "product_name": "Ergonomic desk lamp",
        "product_price": 2800,
        "seller_orders": 92,
        "seller_complaints": 2,
        "buyer_orders": 48,
        "buyer_disputes": 1,
        "review_summary": "Consistently positive reviews; quick delivery.",
        "is_new_interaction": False,
        "new_device": False,
    },
    "medium_risk": {
        "product_name": "Wireless mechanical keyboard",
        "product_price": 6200,
        "seller_orders": 22,
        "seller_complaints": 5,
        "buyer_orders": 14,
        "buyer_disputes": 4,
        "review_summary": "Some buyers report packaging issues; seller responds to tickets.",
        "is_new_interaction": True,
        "new_device": False,
    },
    "high_risk": {
        "product_name": "Imported camera lens kit",
        "product_price": 16500,
        "seller_orders": 3,
        "seller_complaints": 6,
        "buyer_orders": 2,
        "buyer_disputes": 5,
        "review_summary": "Sparse reviews; several mention non-delivery or wrong item.",
        "is_new_interaction": True,
        "new_device": True,
    },
    "low_value_high_risk": {
        "product_name": "Phone case bundle",
        "product_price": 750,
        "seller_orders": 2,
        "seller_complaints": 4,
        "buyer_orders": 1,
        "buyer_disputes": 3,
        "review_summary": "New listing; no verified purchase reviews yet.",
        "is_new_interaction": True,
        "new_device": True,
    },
    "high_value_trusted": {
        "product_name": "Professional workstation laptop",
        "product_price": 48500,
        "seller_orders": 240,
        "seller_complaints": 5,
        "buyer_orders": 112,
        "buyer_disputes": 2,
        "review_summary": "Top seller badge; long history of successful high-value orders.",
        "is_new_interaction": False,
        "new_device": False,
    },
    # None of the frontend payloads lands in LOW; this one does (27.0).
    "trusted_cheap": {
        "product_name": "Cotton tote bag",
        "product_price": 900,
        "seller_orders": 200,
        "seller_complaints": 0,
        "buyer_orders": 60,
        "buyer_disputes": 0,
        "review_summary": "Plenty of positive reviews.",
        "is_new_interaction": False,
        "new_device": False,
    },
}

SIMULATOR_INPUTS = {
    "defaults": {},
    "trusted": {
        "buyer_successful_orders": 200, "buyer_dispute_rate_percent": 0, "buyer_fraud_flags": 0,
        "seller_successful_orders": 400, "seller_complaint_rate_percent": 1, "seller_fraud_flags": 0,
        "order_value_inr": 900, "is_new_pair": False, "is_new_device": False,
    },
    "risky": {
        "buyer_successful_orders": 1, "buyer_dispute_rate_percent": 40, "buyer_fraud_flags": 1,
        "seller_successful_orders": 3, "seller_complaint_rate_percent": 30, "seller_fraud_flags": 0,
        "order_value_inr": 25000, "is_new_pair": True, "is_new_device": True,
    },
}

SCENARIOS = ("low_risk", "medium_risk", "high_risk")


def all_cases():
    """Every (name, method, path, kwargs) request whose response is pinned in golden/."""
    cases = []
    for name, body in TRANSACTIONS.items():
        cases.append((f"decision_evaluate.{name}", "POST", "/decision/evaluate", {"json": body}))
        cases.append((f"risk_score.{name}", "POST", "/risk/score", {"json": body}))
    for name, body in PRODUCT_EVALUATIONS.items():
        cases.append((f"evaluate_product.{name}", "POST", "/evaluate-product", {"json": body}))
    for name, body in SIMULATOR_INPUTS.items():
        cases.append((f"simulator_evaluate.{name}", "POST", "/simulator/evaluate", {"json": body}))
    for s in SCENARIOS:
        cases.append((f"simulate.{s}", "GET", f"/simulate/{s}", {}))
        cases.append((f"evaluate_risk.{s}", "GET", "/evaluate-risk", {"params": {"scenario": s}}))
        cases.append((f"payment_lifecycle.{s}", "GET", "/demo/payment-lifecycle", {"params": {"scenario": s}}))
        cases.append((f"initiate_payment.{s}", "POST", "/initiate-payment", {"json": {"scenario": s}}))
    return cases
