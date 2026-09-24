"""The built-in demo scenarios: each NAME must be the tier its transaction actually scores.

Before this was enforced the names were off by one tier (``low_risk`` scored 44.02 = MEDIUM, ``medium_risk``
scored 98.57 = HIGH), so the frontend — which sends ``f"{level}_risk"`` and shows the returned payment status —
displayed the wrong payment state for a LOW or MEDIUM transaction. Runs with no database.
"""

import pytest

import main
from cases import TRANSACTIONS
from models import TransactionRequest

SCENARIO_TIER = {"low_risk": "LOW", "medium_risk": "MEDIUM", "high_risk": "HIGH"}
SCENARIO_SCORE = {"low_risk": 25.0, "medium_risk": 44.02, "high_risk": 100.0}
# What the frontend (services/api.js scenarioFromRiskLevel + PaymentScreen CONTRACT_TO_UI_STATUS) expects.
PAYMENT_STATUS = {"low_risk": "CAPTURED", "medium_risk": "AUTHORIZED", "high_risk": "HELD"}

ROUTES = {
    "simulate": lambda c, s: c.get(f"/simulate/{s}").json()["decision"]["risk_classification"],
    "evaluate-risk": lambda c, s: c.get("/evaluate-risk", params={"scenario": s}).json()["riskLevel"],
    "payment-lifecycle": lambda c, s: c.get("/demo/payment-lifecycle", params={"scenario": s}).json()["risk_classification"],
    "initiate-payment": lambda c, s: c.post("/initiate-payment", json={"scenario": s}).json()["lifecycle"]["risk_classification"],
}


@pytest.mark.parametrize("scenario", SCENARIO_TIER)
@pytest.mark.parametrize("route", ROUTES)
def test_the_name_is_the_tier_on_every_route(client, route, scenario):
    assert ROUTES[route](client, scenario) == SCENARIO_TIER[scenario]


def test_there_is_one_scenario_per_tier():
    assert set(main.SCENARIOS) == set(SCENARIO_TIER) == set(main.SCENARIO_KEYS)
    assert sorted(SCENARIO_TIER.values()) == ["HIGH", "LOW", "MEDIUM"]


@pytest.mark.parametrize("scenario", SCENARIO_SCORE)
def test_scores_are_pinned(client, scenario):
    body = client.get(f"/simulate/{scenario}").json()
    assert (body["risk_score"], body["decision"]["risk_classification"]) == (SCENARIO_SCORE[scenario], SCENARIO_TIER[scenario])
    assert client.get("/evaluate-risk", params={"scenario": scenario}).json() == {
        "riskLevel": SCENARIO_TIER[scenario], "riskScore": SCENARIO_SCORE[scenario]}


@pytest.mark.parametrize("scenario", SCENARIO_TIER)
def test_scenario_inputs_are_the_golden_pinned_fixtures(client, scenario):
    """Ties each scenario to the cases.TRANSACTIONS fixture of the same name, whose /decision/evaluate response is
    pinned in the golden files, so the scenario's inputs can't drift silently."""
    fixture = TRANSACTIONS[scenario]
    assert main.SCENARIOS[scenario] == TransactionRequest(**fixture)
    assert client.get(f"/simulate/{scenario}").json() == client.post("/decision/evaluate", json=fixture).json()


@pytest.mark.parametrize("scenario", SCENARIO_TIER)
def test_frontend_payment_states(client, scenario):
    """The UI's low/medium/high levels map to `${level}_risk` and show the returned status."""
    r = client.post("/initiate-payment", json={"scenario": scenario}).json()
    assert r["status"] == PAYMENT_STATUS[scenario]


def test_the_default_scenario_is_the_medium_example(client):
    """/initiate-payment and /evaluate-risk default to medium_risk; that is now genuinely MEDIUM."""
    assert client.post("/initiate-payment").json()["status"] == "AUTHORIZED"
    assert client.post("/initiate-payment", json={}).json() == client.post("/initiate-payment", json={"scenario": "medium_risk"}).json()
    assert client.get("/evaluate-risk").json()["riskLevel"] == "MEDIUM"
    assert client.get("/demo/payment-lifecycle").json()["risk_classification"] == "MEDIUM"


def test_the_scenario_table_is_defined_once_and_callers_get_copies():
    for name, request in main.SCENARIOS.items():
        again = main._transaction_for_scenario(name)
        assert again == request and again is not request
    mine = main._transaction_for_scenario("low_risk")
    mine.order_value = 1
    assert main.SCENARIOS["low_risk"].order_value == 900  # a caller can't corrupt the shared table


def test_unknown_scenarios_are_still_rejected_with_the_old_messages(client):
    assert client.get("/simulate/nope").status_code == 404
    assert client.get("/evaluate-risk", params={"scenario": "nope"}).status_code == 404
    assert client.get("/demo/payment-lifecycle", params={"scenario": "nope"}).status_code == 400
    assert client.post("/initiate-payment", json={"scenario": "nope"}).status_code == 400
