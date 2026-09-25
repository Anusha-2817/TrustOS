"""
TrustOS — risk decision audit trail (Phase 4).

Turns a pipeline result into a ``risk_decision_log`` row and writes it. Two write modes:

* Order creation writes the row itself inside the order's transaction (``pipeline_record`` →
  ``db.insert_risk_decision``), so it fails closed with the order.
* Pure evaluation routes call ``log_decision_fail_open``: a database problem never changes the response
  the caller gets. The failure is reported on the ``trustos.risk_log`` logger at ERROR together with the
  full row as JSON, so a lost decision can be replayed from the logs.

Two formulas feed the log and their scores are not comparable, hence ``formula``:
  static_v1  — RiskEngine (/decision/evaluate, /orders, /initiate-payment)
  product_v1 — /evaluate-product (trust + value + context + LLM behaviour risk)
For product_v1 the request's ``buyer_orders`` / ``seller_orders`` land in ``*_total_orders`` (the formula
uses them as the order count; the request has no successful-orders or fraud-flag fields, so those stay NULL).
"""

import hashlib
import json
import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import db
from models import EvaluateProductRequest, EvaluateProductResponse, FullEvaluationResponse, ProductRiskModel, TransactionRequest
from services.payment_engine import LLM_MODEL
from services.product_risk import CATALOGUE_PATH

logger = logging.getLogger("trustos.risk_log")

FORMULA_STATIC = "static_v1"
FORMULA_PRODUCT = "product_v1"

_BACKEND_DIR = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def code_version() -> str:
    """TRUSTOS_CODE_VERSION if set (deploys), else the short git sha of the checkout, else 'unknown'."""
    env = os.environ.get("TRUSTOS_CODE_VERSION", "").strip()
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=_BACKEND_DIR, capture_output=True, text=True, timeout=5, check=True
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


@lru_cache(maxsize=1)
def ml_model_version() -> str:
    """sha256 of seed_products.json: the Phase 2 model retrains from it with a fixed seed, so the file hash
    (plus the pinned scikit-learn) identifies the exact model that produced a product_risk score."""
    return hashlib.sha256(CATALOGUE_PATH.read_bytes()).hexdigest()


def _product_risk_columns(pr: Optional[ProductRiskModel]) -> Dict[str, Any]:
    if pr is None:
        return {}
    cols: Dict[str, Any] = {"product_risk_applicable": pr.applicable}
    if pr.applicable:
        dumped = pr.model_dump(mode="json")
        cols.update(
            product_risk_score=db.money(pr.score, 1),
            product_risk_level=pr.level,
            product_risk_top_features=dumped["top_features"],
            product_risk_imputed=list(pr.imputed_features),
            ml_model_version=ml_model_version(),
        )
    return cols


def pipeline_record(
    source: str,
    req: TransactionRequest,
    full: FullEvaluationResponse,
    *,
    order_id=None,
    buyer_id: Optional[str] = None,
    seller_id: Optional[str] = None,
) -> Dict[str, Any]:
    """A risk_decision_log row for a run of ``services.pipeline.run_pipeline`` (formula static_v1)."""
    return {
        "source": source,
        "order_id": order_id,
        "buyer_id": buyer_id,
        "seller_id": seller_id,
        "product_id": req.product_id,
        "formula": FORMULA_STATIC,
        "code_version": code_version(),
        "buyer_successful_orders": req.buyer.successful_orders,
        "buyer_total_orders": req.buyer.total_orders,
        "buyer_disputes": req.buyer.disputes,
        "buyer_fraud_flags": req.buyer.fraud_flags,
        "seller_successful_orders": req.seller.successful_orders,
        "seller_total_orders": req.seller.total_orders,
        "seller_complaints": req.seller.complaints,
        "seller_fraud_flags": req.seller.fraud_flags,
        "order_value": db.money(req.order_value),
        "currency": "INR",
        "is_new_pair": req.is_new_pair,
        "is_new_device": req.is_new_device,
        "request_payload": req.model_dump(mode="json"),
        "buyer_trust": db.money(full.buyer_trust),
        "seller_trust": db.money(full.seller_trust),
        "risk_score": db.money(full.risk_score),
        "final_tier": full.decision.risk_classification,
        "escalated_from": full.decision.escalated_from,
        "components": {
            "risk_components": full.risk_components.model_dump(mode="json", exclude={"product_risk"}),
            "buyer_trust_level": full.buyer_trust_level,
            "buyer_breakdown": full.buyer_breakdown,
            "seller_trust_level": full.seller_trust_level,
            "seller_breakdown": full.seller_breakdown,
        },
        **_product_risk_columns(full.risk_components.product_risk),
    }


def product_evaluation_record(
    source: str,
    body: EvaluateProductRequest,
    resp: EvaluateProductResponse,
    llm_output: Dict[str, Any],
) -> Dict[str, Any]:
    """A risk_decision_log row for /evaluate-product (formula product_v1), including the raw LLM output and
    whether it was the error fallback."""
    return {
        "source": source,
        "product_id": body.product_id,
        "formula": FORMULA_PRODUCT,
        "code_version": code_version(),
        "buyer_total_orders": body.buyer_orders,
        "buyer_disputes": body.buyer_disputes,
        "seller_total_orders": body.seller_orders,
        "seller_complaints": body.seller_complaints,
        "order_value": db.money(body.product_price),
        "currency": "INR",
        "is_new_pair": body.is_new_interaction,
        "is_new_device": body.new_device,
        "request_payload": body.model_dump(mode="json"),
        "buyer_trust": db.money(resp.buyer_trust),
        "seller_trust": db.money(resp.seller_trust),
        "risk_score": db.money(resp.final_risk),
        "final_tier": resp.decision,
        "escalated_from": resp.escalated_from,
        "llm_is_fallback": bool(llm_output["is_fallback"]),  # strict: a caller that forgets the flag must fail loudly
        "llm_model": LLM_MODEL,
        "llm_signals": list(resp.signals),
        "llm_confidence": db.money(resp.confidence, 3),
        "llm_risk_modifier": db.money(resp.risk_modifier),
        "behavior_risk": db.money(resp.behavior_risk),
        "components": {
            "risk_breakdown": resp.risk_breakdown.model_dump(mode="json", exclude={"product_risk"}),
            "base_risk": resp.base_risk,
        },
        **_product_risk_columns(resp.risk_breakdown.product_risk),
    }


async def log_decision_fail_open(build_record: Callable[[], Dict[str, Any]], *, source: str) -> Optional[int]:
    """Write one decision to the log without ever raising. Returns the row id, or None when persistence is
    off or the write did not happen (in which case the loss and the full row are logged at ERROR).

    ``build_record`` is a callable so that a bug while *building* the row is contained too. After a
    connectivity failure the database is skipped for a short cooldown (see db.circuit_is_open) so an outage
    costs one connect attempt per window, not one per request; skipped rows are still reported."""
    if not db.is_configured():
        return None
    record: Optional[Dict[str, Any]] = None
    try:
        record = build_record()
        if db.circuit_is_open():
            _report(source, record, "SKIPPED (database unreachable a moment ago)", exc_info=False)
            return None
        async with db.transaction() as conn:
            return await db.insert_risk_decision(conn, record)
    except Exception as exc:
        if db.is_connectivity_error(exc):
            db.trip_circuit()
        _report(source, record, "FAILED", exc_info=True)
        return None


def _report(source: str, record: Optional[Dict[str, Any]], what: str, *, exc_info: bool) -> None:
    try:
        payload = json.dumps(record, default=str) if record is not None else "<record could not be built>"
    except Exception:
        payload = "<record could not be serialised>"
    logger.error(
        "risk_decision_log write %s (fail-open: the caller still got its decision) source=%s record=%s",
        what,
        source,
        payload,
        exc_info=exc_info,
    )
