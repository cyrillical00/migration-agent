#!/usr/bin/env python3
"""Seed the local Postgres with dev fixtures.

Run: python scripts/load-fixtures.py
Requires MIGRATION_AGENT_DATABASE_URL to point at local Postgres.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "MIGRATION_AGENT_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/migration_agent",
)

_NOW = datetime.now(timezone.utc)


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    from agent.state.models.core import (
        Base,
        BusySeason,
        SourceInventory,
        WavePlan,
    )

    async with engine.begin() as conn:
        pass  # Tables already created by Alembic

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        # Busy season: tax returns
        season = BusySeason(
            id=uuid.uuid4(),
            name="Tax Returns 2026",
            hard_freeze_start=datetime(2026, 1, 15, tzinfo=timezone.utc),
            hard_freeze_end=datetime(2026, 4, 18, tzinfo=timezone.utc),
            soft_freeze_weeks_before=2,
            soft_freeze_weeks_after=1,
            applies_to_users=[],
        )
        session.add(season)

        # Sample wave plan
        wave = WavePlan(
            id=uuid.uuid4(),
            wave_number=1,
            name="Wave 1 - Corp Engineering",
            status="draft",
            members=[],
        )
        session.add(wave)

        # Sample source inventory entries
        for i in range(3):
            entry = SourceInventory(
                id=uuid.uuid4(),
                tenant_id="contoso.com",
                entity_type="user",
                source_id=f"user-{i+1:04d}",
                normalized={
                    "source_id": f"user-{i+1:04d}",
                    "upn": f"user{i+1}@contoso.com",
                    "display_name": f"Dev User {i+1}",
                    "email": f"user{i+1}@contoso.com",
                    "timezone": "America/New_York",
                    "license_skus": ["ENTERPRISEPACK"],
                    "is_service_account": False,
                    "is_contractor": False,
                },
                discovered_at=_NOW,
            )
            session.add(entry)

        await session.commit()
        print("Fixtures loaded: busy_season, wave_plan (wave 1), 3 source_inventory users")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
