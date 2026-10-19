"""Read-only public demo ownership inventory. Does not load credentials or write DB."""
import asyncio
import json
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.identity import Enterprise
from app.models.recruitment import Job
from scripts.import_market_scenarios import LEGACY_COMPANY, _enterprise_owner, load_scenarios


async def main():
    url = make_url(settings.database_url)
    assert url.host == "127.0.0.1" and url.port in {None, 5432} and url.database == "careerproof"
    engine = create_async_engine(settings.database_url, hide_parameters=True)
    try:
        async with AsyncSession(engine) as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            orgs = list(await session.scalars(select(Enterprise).where(
                Enterprise.name.in_([LEGACY_COMPANY, load_scenarios()["companyName"]])
            )))
            result = []
            for org in orgs:
                jobs = list(await session.scalars(select(Job).where(Job.enterprise_id == org.id)))
                result.append({"enterpriseId": str(org.id), "name": org.name,
                               "ownerId": str(await _enterprise_owner(session, org.id)),
                               "jobs": [{"id": str(j.id), "title": j.title,
                                         "creatorId": str(j.created_by), "status": j.status,
                                         "description": j.description, "companyName": j.company_name}
                                        for j in jobs]})
            path = Path(__file__).with_name("normal-plan-inventory.json")
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


asyncio.run(main())
