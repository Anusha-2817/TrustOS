"""Phase 4 parity: the API must answer exactly as before whether persistence is live, unreachable, or off.

Replays every pinned golden request (the Phase 3 set and the Phase 4 baseline, all WITHOUT order_id) with
  * persistence LIVE  — same responses, and the log gets exactly the rows the log-writing routes imply;
  * persistence DEAD  — DATABASE_URL points at a closed port: log-writing routes fail open (same responses,
                        failure reported on the ``trustos.risk_log`` logger), nothing else is affected.
(Persistence OFF is what test_characterization*.py already prove: the default suite has no DATABASE_URL.)
"""

import json
import logging
import time
from pathlib import Path

import httpx
import pytest

import db
from cases import all_cases, phase4_baseline_cases
from pg_fixtures import fetch

GOLDEN_DIR = Path(__file__).parent / "golden"
CASES = [(f"p3:{n}", m, p, kw, "pre_phase3_responses.json", n) for n, m, p, kw in all_cases()] + [
    (f"p4:{n}", m, p, kw, "pre_phase4_responses.json", n) for n, m, p, kw in phase4_baseline_cases()
]
GOLDENS = {f: json.loads((GOLDEN_DIR / f).read_text(encoding="utf-8")) for f in ("pre_phase3_responses.json", "pre_phase4_responses.json")}
LOGGING_PATHS = {"/decision/evaluate", "/evaluate-product", "/initiate-payment"}

# A port nothing listens on: connection refused, the fastest way to be "unreachable".
DEAD_URL = "postgresql://postgres@127.0.0.1:9/trustos_dead"


async def replay(client):
    for label, method, path, kwargs, golden_file, name in CASES:
        r = await client.request(method, path, **kwargs)
        assert {"status": r.status_code, "body": r.json()} == GOLDENS[golden_file][name], label


def expected_log_rows() -> int:
    return sum(
        1 for _, _, path, _, golden_file, name in CASES if path in LOGGING_PATHS and GOLDENS[golden_file][name]["status"] == 200
    )


async def test_every_golden_response_is_unchanged_with_persistence_live(api):
    await replay(api)
    rows = await fetch("select source, order_id from risk_decision_log")
    assert len(rows) == expected_log_rows() == 17
    assert {r["source"] for r in rows} == {"decision_evaluate", "evaluate_product", "initiate_payment"}
    assert {r["order_id"] for r in rows} == {None}  # none of these requests had an order
    assert await fetch("select count(*) as n from orders") == [{"n": 0}]


@pytest.fixture
async def api_dead(monkeypatch):
    import main
    from conftest import fake_llm

    monkeypatch.setattr(main, "call_llm", fake_llm)
    db.configure(DEAD_URL)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as client:
        yield client
    await db.dispose()


async def test_every_golden_response_is_unchanged_with_persistence_unreachable(api_dead, caplog):
    caplog.set_level(logging.ERROR, logger="trustos.risk_log")
    started = time.monotonic()
    await replay(api_dead)
    elapsed = time.monotonic() - started
    failures = [r for r in caplog.records if r.name == "trustos.risk_log"]
    assert len(failures) == expected_log_rows()  # one report per lost write (FAILED or SKIPPED), none for any other route
    assert sum("FAILED" in r.getMessage() for r in failures) >= 1 and all("fail-open" in r.getMessage() for r in failures)
    # 17 logged requests; without the circuit breaker each waited out its own refused connection (~2 s apiece on Windows)
    assert elapsed < 12, f"fail-open writes stalled the API for {elapsed:.1f}s"


async def test_a_failed_write_is_reported_with_the_full_row_so_it_can_be_replayed(api_dead, caplog):
    caplog.set_level(logging.ERROR, logger="trustos.risk_log")
    r = await api_dead.post("/decision/evaluate", json={"buyer": {"successful_orders": 1, "total_orders": 2}, "seller": {"successful_orders": 5, "total_orders": 8}, "order_value": 12000, "is_new_pair": True, "is_new_device": True})
    assert r.status_code == 200
    [record] = [r for r in caplog.records if r.name == "trustos.risk_log"]
    assert record.exc_info is not None  # the underlying error, with traceback
    assert "fail-open" in record.getMessage() and "source=decision_evaluate" in record.getMessage()
    row = json.loads(record.getMessage().split("record=", 1)[1])
    assert (row["final_tier"], row["formula"], row["source"]) == ("HIGH", "static_v1", "decision_evaluate")
    assert row["request_payload"]["order_value"] == 12000
