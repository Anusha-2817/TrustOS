"""Request fixtures shared by the characterization and escalation tests."""

# Request fixtures for /decision/evaluate and friends. Each tier-named key IS the tier it scores (asserted by
# tests/test_characterization.py::test_fixture_names_match_their_tiers). Two HIGH fixtures exist: high_risk raw-scores
# 152 and is clamped to 100; high_risk_unclamped scores 98.57 without hitting the clamp. The keys used to be off by
# one tier ("low_risk" was MEDIUM, "medium_risk" HIGH, and the only LOW one was called "trusted"), the same
# mistake main.SCENARIOS had. low_risk / medium_risk / high_risk here are also the inputs of the scenarios of the
# same name (tests/test_scenarios.py). Renaming these keys renamed the golden keys derived from them.
TRANSACTIONS = {
    # LOW (25.0); it mirrors SIMULATOR_INPUTS["trusted"].
    "low_risk": {
        "buyer": {"successful_orders": 200, "total_orders": 200, "disputes": 0, "fraud_flags": 0},
        "seller": {"successful_orders": 400, "total_orders": 404, "complaints": 4, "fraud_flags": 0},
        "order_value": 900,
        "is_new_pair": False,
        "is_new_device": False,
    },
    # MEDIUM (44.02)
    "medium_risk": {
        "buyer": {"successful_orders": 12, "total_orders": 13, "disputes": 1, "fraud_flags": 0},
        "seller": {"successful_orders": 55, "total_orders": 58, "complaints": 2, "fraud_flags": 0},
        "order_value": 1500,
        "is_new_pair": False,
        "is_new_device": False,
    },
    # HIGH (100.0, clamped)
    "high_risk": {
        "buyer": {"successful_orders": 1, "total_orders": 2, "disputes": 1, "fraud_flags": 0},
        "seller": {"successful_orders": 5, "total_orders": 8, "complaints": 2, "fraud_flags": 0},
        "order_value": 12000,
        "is_new_pair": True,
        "is_new_device": True,
    },
    # HIGH (98.57, below the clamp)
    "high_risk_unclamped": {
        "buyer": {"successful_orders": 5, "total_orders": 6, "disputes": 1, "fraud_flags": 0},
        "seller": {"successful_orders": 25, "total_orders": 28, "complaints": 3, "fraud_flags": 0},
        "order_value": 5000,
        "is_new_pair": True,
        "is_new_device": False,
    },
}

# Request fixtures for POST /evaluate-product. Tier-named keys are the tier they score (asserted like the above).
# These are the frontend's demo payloads (frontend/src/data/trustosDemoTransactions.js) except low_risk. The frontend
# gives its payloads the same off-by-one names the fixtures used to have, so the mapping is: frontend "low-risk" ->
# medium_risk here (desk lamp, 33.0 MEDIUM), frontend "medium-risk" -> high_risk_unclamped (keyboard, 91.13 HIGH),
# "high-risk", "low-value-high-risk" and "high-value-trusted" keep their names. None of the frontend payloads is LOW;
# low_risk is an added one (cotton tote bag, 27.0).
PRODUCT_EVALUATIONS = {
    # LOW (27.0)
    "low_risk": {
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
    # MEDIUM (33.0)
    "medium_risk": {
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
    # HIGH (100.0, clamped)
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
    # HIGH (91.13, below the clamp)
    "high_risk_unclamped": {
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
    # HIGH (100.0); named for what it is: a low-value order with high-risk signals
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
    # MEDIUM (54.5); named for its inputs (large order, strong counterparties), not its tier
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


# ─── Phase 4 baseline: routes/paths the Phase 3 golden set never pinned ──────────────────────────
# Recorded from the code at commit b403fe6 (before any Phase 4 change) into golden/pre_phase4_responses.json.
# Covers /verify and /settle (not in all_cases() at all), /initiate-payment's edge cases, and the error
# paths (400/404/422) of the routes Phase 4 touches. Every one of these is a request WITHOUT order_id.

def phase4_baseline_cases():
    cases = []
    # /verify: every toggle combination, plus no body at all.
    cases.append(("verify.no_body", "POST", "/verify", {}))
    for name, body in {
        "default": {},
        "passed": {"passed": True},
        "failed": {"passed": False},
        "inconsistent": {"inconsistent": True},
        "inconsistent_and_failed": {"passed": False, "inconsistent": True},
        "extra_field_ignored": {"passed": True, "unexpected": 1},
    }.items():
        cases.append((f"verify.{name}", "POST", "/verify", {"json": body}))
    cases.append(("verify.bad_type", "POST", "/verify", {"json": {"passed": "maybe"}}))
    # /settle: each action, normalisation, and rejections.
    cases.append(("settle.no_body", "POST", "/settle", {}))
    for action in ("capture", "release", "cancel", "CAPTURE", "  Release  "):
        cases.append((f"settle.action[{action!r}]", "POST", "/settle", {"json": {"action": action}}))
    cases.append(("settle.invalid_action", "POST", "/settle", {"json": {"action": "refund"}}))
    cases.append(("settle.null_action", "POST", "/settle", {"json": {"action": None}}))
    cases.append(("settle.empty_body", "POST", "/settle", {"json": {}}))
    # /initiate-payment edge cases (the three happy paths are already in all_cases()).
    cases.append(("initiate_payment.no_body", "POST", "/initiate-payment", {}))
    cases.append(("initiate_payment.empty_body", "POST", "/initiate-payment", {"json": {}}))
    cases.append(("initiate_payment.null_scenario", "POST", "/initiate-payment", {"json": {"scenario": None}}))
    cases.append(("initiate_payment.bad_scenario", "POST", "/initiate-payment", {"json": {"scenario": "nope"}}))
    cases.append(("initiate_payment.extra_field_ignored", "POST", "/initiate-payment", {"json": {"scenario": "high_risk", "x": 1}}))
    # Error paths of the routes Phase 4 wires into or leaves alone.
    cases.append(("simulate.unknown", "GET", "/simulate/nope", {}))
    cases.append(("evaluate_risk.unknown", "GET", "/evaluate-risk", {"params": {"scenario": "nope"}}))
    cases.append(("payment_lifecycle.unknown", "GET", "/demo/payment-lifecycle", {"params": {"scenario": "nope"}}))
    cases.append(("health", "GET", "/health", {}))
    cases.append(("decision_evaluate.missing_buyer", "POST", "/decision/evaluate", {"json": {"order_value": 100}}))
    cases.append(("decision_evaluate.negative_value", "POST", "/decision/evaluate",
                  {"json": {**TRANSACTIONS["medium_risk"], "order_value": -5}}))
    cases.append(("decision_evaluate.total_lt_successful", "POST", "/decision/evaluate", {"json": {
        **TRANSACTIONS["medium_risk"], "buyer": {"successful_orders": 5, "total_orders": 1}}}))
    cases.append(("evaluate_product.bad_price", "POST", "/evaluate-product",
                  {"json": {**PRODUCT_EVALUATIONS["medium_risk"], "product_price": 0}}))
    cases.append(("evaluate_product.missing_name", "POST", "/evaluate-product",
                  {"json": {k: v for k, v in PRODUCT_EVALUATIONS["medium_risk"].items() if k != "product_name"}}))
    # An explicit null order_id (Phase 4's new optional field) must be a no-op on the three routes it is added to.
    return cases
