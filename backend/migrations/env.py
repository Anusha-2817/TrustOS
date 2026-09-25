"""Alembic environment (async). URL comes from DATABASE_URL, normalised to the asyncpg driver."""

import asyncio
import sys
from pathlib import Path

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
from db_schema import metadata  # noqa: E402

target_metadata = metadata


def _url() -> str:
    url = db.database_url()
    if url is None:
        raise SystemExit("DATABASE_URL is not set (e.g. postgresql://user:pass@localhost:5432/trustos)")
    return url


def _configure(**kwargs):
    context.configure(target_metadata=target_metadata, compare_type=True, **kwargs)


def run_migrations_offline() -> None:
    _configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
