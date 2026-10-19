"""Exercise current repositories/services only in the dedicated migration DB."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.identity import User
from app.models.recruitment import Job
from app.repositories.jobs import JobRepository
from app.services.jobs import JobService


async def main():
    engine = create_async_engine("postgresql+asyncpg://ci:ci@127.0.0.1:55437/cp_migration82")
    try:
        async with AsyncSession(engine) as session:
            owner = await session.scalar(select(User.id))
            rows = []
            for title, visible, status in [
                ("Owned hidden example", False, "published"),
                ("Owned enterprise opening", True, "published"),
                ("Owned closed opening", True, "closed"),
            ]:
                job = Job(created_by=owner, title=title, company_name="Synthetic",
                          description="Synthetic", discovery_visible=visible,
                          is_demo=not visible, status=status)
                session.add(job)
                rows.append(job)
            await session.flush()
            repository = JobRepository(session)
            page1, total = await repository.list(page=1, page_size=1)
            page2, total2 = await repository.list(page=2, page_size=1)
            assert total == total2 == 2
            ids = {page1[0][0].id, page2[0][0].id}
            assert rows[1].id in ids and rows[0].id not in ids and rows[2].id not in ids
            candidates = await repository.recommendation_candidates(100)
            assert {job.id for job in candidates} == ids
            hidden = await JobService(session).get(rows[0].id)
            assert hidden.is_demo and not hidden.discovery_visible
            assert hidden.status == "published"
            await session.rollback()
        result = {"dedicatedPort": 55437, "countAndPagesUseSamePredicate": True,
                  "enterpriseOpeningPreserved": True, "recommendationsRespectVisibility": True,
                  "hiddenPublishedJobStillReadableById": True, "rolledBackFixtures": True}
        with Path(__file__).with_name("pg-discovery-result.json").open("x") as handle:
            json.dump(result, handle, indent=2)
        print("Dedicated PostgreSQL discovery, pagination, recommendation and ID access passed.")
    finally:
        await engine.dispose()


asyncio.run(main())
