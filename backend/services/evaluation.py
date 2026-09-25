"""
TrustOS — the one implementation of "evaluate a transaction and log the decision", shared by the legacy
``POST /decision/evaluate`` and ``POST /v1/risk/evaluate`` (Phase 5a). Same pipeline, same log row
(``source=decision_evaluate``), same fail-open behaviour: a database problem never changes the response.
"""

from fastapi.concurrency import run_in_threadpool

from models import FullEvaluationResponse, TransactionRequest
from services import risk_log
from services.pipeline import run_pipeline


async def evaluate_and_log(request: TransactionRequest) -> FullEvaluationResponse:
    full = await run_in_threadpool(run_pipeline, request)
    await risk_log.log_decision_fail_open(
        lambda: risk_log.pipeline_record("decision_evaluate", request, full), source="decision_evaluate"
    )
    return full
