"""Dedicated PostgreSQL curation/concurrent replay; never app-configured URL."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.enums import UserRole
from app.models.identity import Enterprise, User
from app.models.recruitment import Job
from scripts.import_market_scenarios import load_scenarios, seed_scenarios

OUT = Path(__file__).resolve().parent
BACKEND = OUT.parents[2] / "backend"
URL = "postgresql+asyncpg://ci:ci@127.0.0.1:55438/cp_curation82"


async def main():
    env = {**os.environ, "DATABASE_URL": URL, "APP_ENV": "test",
           "AI_EXTERNAL_ENABLED": "false", "AI_PROVIDER": "mock"}
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=BACKEND, env=env, capture_output=True)
    (OUT / "pg-migrate.raw.out").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, "Dedicated migration failed"
    engine = create_async_engine(URL, hide_parameters=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            user = User(email="curation82@synthetic.invalid", password_hash="unused-synthetic",
                        display_name="Synthetic owner", role=UserRole.ENTERPRISE)
            session.add(user)
            await session.commit()
            owner = user.id

        async def seed():
            async with AsyncSession(engine, expire_on_commit=False) as session:
                return await seed_scenarios(session, owner)

        concurrent = await asyncio.gather(seed(), seed())
        assert sorted(len(r["created"]) for r in concurrent) == [0, 3]
        async with AsyncSession(engine, expire_on_commit=False) as session:
            assert await session.scalar(select(func.count()).select_from(Enterprise)) == 1
            assert await session.scalar(select(func.count()).select_from(Job)) == 3
            job = await session.scalar(select(Job).order_by(Job.id))
            job.status, job.discovery_visible = "closed", False
            await session.commit()
            before = (job.id, job.status, job.discovery_visible, job.updated_at)
        replay = await seed()
        async with AsyncSession(engine) as session:
            job = await session.get(Job, before[0])
            assert (job.id, job.status, job.discovery_visible, job.updated_at) == before
        assert replay["created"] == replay["updated"] == replay["hidden"] == []
        summary = {"dedicatedPort": 55438, "scenarioCount": len(load_scenarios()["scenarios"]),
                   "concurrentCreateCounts": [len(r["created"]) for r in concurrent],
                   "replayPreservesClosedHiddenAndTimestamp": True}
        (OUT / "pg-curation-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))
    finally:
        await engine.dispose()


asyncio.run(main())
