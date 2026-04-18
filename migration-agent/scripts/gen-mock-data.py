#!/usr/bin/env python3
"""Generate larger synthetic datasets for load testing.

Run: python scripts/gen-mock-data.py --users 200
"""
from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "MIGRATION_AGENT_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/migration_agent",
)


async def generate(user_count: int) -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    from agent.state.models.core import SourceInventory

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    batch_size = 50
    total = 0

    async with async_session() as session:
        for i in range(user_count):
            depts = ["engineering", "accounting", "tax", "ops"]
            dept = depts[i % len(depts)]
            entry = SourceInventory(
                id=uuid.uuid4(),
                tenant_id="contoso.com",
                entity_type="user",
                source_id=f"mock-user-{i:06d}",
                normalized={
                    "source_id": f"mock-user-{i:06d}",
                    "upn": f"mockuser{i}@contoso.com",
                    "display_name": f"Mock User {i}",
                    "email": f"mockuser{i}@contoso.com",
                    "timezone": "America/New_York",
                    "license_skus": ["ENTERPRISEPACK"],
                    "is_service_account": i % 20 == 0,
                    "is_contractor": i % 15 == 0,
                    "department": dept,
                },
                discovered_at=now,
            )
            session.add(entry)
            total += 1

            if total % batch_size == 0:
                await session.commit()
                print(f"  {total}/{user_count} users committed")

        await session.commit()

    print(f"Done: {total} mock users inserted")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(generate(args.users))
