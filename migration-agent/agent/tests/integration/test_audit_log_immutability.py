"""Integration test: audit_log must reject UPDATE and DELETE at the DB trigger level.

Requires a live Postgres with the schema applied (make migrate).
Skipped if DATABASE_URL is not set to a real DB.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "MIGRATION_AGENT_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/migration_agent",
)


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(DATABASE_URL, echo=False)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_audit_log_rejects_update(session_factory) -> None:
    async with session_factory() as session:
        # Insert a valid row
        await session.execute(
            text(
                "INSERT INTO audit_log (actor, action, result) VALUES ('test-agent', 'test:action', 'ok')"
            )
        )
        await session.commit()

        # Fetch its id
        row = await session.execute(text("SELECT id FROM audit_log ORDER BY id DESC LIMIT 1"))
        row_id = row.scalar_one()

        # Attempt UPDATE -- must raise
        with pytest.raises(Exception, match="append-only"):
            await session.execute(
                text(f"UPDATE audit_log SET result = 'tampered' WHERE id = {row_id}")
            )
            await session.commit()


@pytest.mark.asyncio
async def test_audit_log_rejects_delete(session_factory) -> None:
    async with session_factory() as session:
        row = await session.execute(text("SELECT id FROM audit_log ORDER BY id DESC LIMIT 1"))
        row_id = row.scalar_one()

        with pytest.raises(Exception, match="append-only"):
            await session.execute(text(f"DELETE FROM audit_log WHERE id = {row_id}"))
            await session.commit()
