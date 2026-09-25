"""Postgres fixtures for the database tests (imported into conftest.py).

Where the database comes from, in order:
  1. TEST_DATABASE_URL — an existing scratch database (its name must end in ``_test``: the fixture drops and
     recreates its ``public`` schema). Use this in CI.
  2. ``pixeltable-pgserver`` (a dev dependency that bundles PostgreSQL) — a throwaway local server in a temp dir.
  3. Neither available → the database tests are SKIPPED (the rest of the suite still runs).

The schema is created by running the real Alembic migration (``alembic upgrade head``) in a subprocess, so
every database test also exercises migrations/env.py and 0001.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
TABLES = "orders, payments, verifications, risk_decision_log"


def run_alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120
    )


async def _reset_public_schema(url: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    """A migrated, empty scratch database (``postgresql://…``); see the module docstring for where it comes from."""
    external = os.environ.get("TEST_DATABASE_URL")
    server = None
    if external:
        dbname = external.rsplit("/", 1)[-1].split("?")[0]
        if not dbname.endswith("_test"):
            pytest.fail(f"TEST_DATABASE_URL must point at a database whose name ends in '_test' (got {dbname!r})")
        url = external
        asyncio.run(_reset_public_schema(url))
    else:
        try:
            import pixeltable_pgserver
        except ImportError:
            pytest.skip("no Postgres for the database tests: set TEST_DATABASE_URL or `pip install pixeltable-pgserver`")
        server = pixeltable_pgserver.get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="delete")
        server.psql("CREATE DATABASE trustos_test;")
        url = server.get_uri("trustos_test")
    proc = run_alembic(url, "upgrade", "head")
    assert proc.returncode == 0, f"alembic upgrade head failed:\n{proc.stdout}\n{proc.stderr}"
    try:
        yield url
    finally:
        if server is not None:
            server.cleanup()


@pytest.fixture
async def pg(pg_url):
    """Persistence ON for one test: empty tables, ``db`` configured against the scratch database (created
    inside the test's own event loop, so asyncpg connections never cross loops), disposed afterwards."""
    import db

    db.configure(pg_url)
    async with db.transaction() as conn:
        import sqlalchemy as sa

        await conn.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield pg_url
    await db.dispose()


@pytest.fixture
async def api(pg, monkeypatch):
    """An async client on the real app with persistence on and the deterministic fake LLM."""
    import httpx

    import main
    from conftest import fake_llm

    monkeypatch.setattr(main, "call_llm", fake_llm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as client:
        yield client


async def fetch(sql: str, **params):
    """Run a read query on the configured test database; rows as dicts."""
    import sqlalchemy as sa

    import db

    async with db.transaction() as conn:
        return [dict(r._mapping) for r in (await conn.execute(sa.text(sql), params)).all()]
