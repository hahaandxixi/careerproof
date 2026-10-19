"""One reviewed local curation; require exact pre-reviewed legacy ids before writing."""
import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from scripts.import_market_scenarios import legacy_candidates, seed_scenarios

OUT = Path(__file__).resolve().parent


async def snapshot(engine, label):
    async with engine.connect() as c, c.begin():
        await c.execute(text("SET TRANSACTION READ ONLY"))
        tables = (await c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ))).scalars().all()
        quote = c.dialect.identifier_preparer.quote
        digests = {}
        for table in tables:
            count, digest = (await c.execute(text(
                "SELECT count(*),md5(COALESCE(string_agg(row_to_json(t)::text,'' "
                f"ORDER BY row_to_json(t)::text),'')) FROM {quote(table)} t"
            ))).one()
            digests[table] = {"rows": count, "digest": digest}
        jobs = (await c.execute(text("SELECT row_to_json(j) FROM jobs j ORDER BY id"))).scalars().all()
        result = {"tables": digests, "jobs": jobs}
        (OUT / f"normal-{label}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result


async def main():
    url = make_url(settings.database_url)
    assert url.host == "127.0.0.1" and url.port in {None, 5432} and url.database == "careerproof"
    assert settings.app_env == "development"
    assert not (OUT / "normal-before.json").exists(), "One-shot; do not overwrite evidence"
    plan = json.loads((OUT / "normal-curation-plan.json").read_text(encoding="utf-8"))
    owner, legacy = UUID(plan["ownerId"]), UUID(plan["legacyEnterpriseId"])
    expected = {r["id"] for r in plan["hide"]}
    assert len(expected) == 9
    engine = create_async_engine(settings.database_url, hide_parameters=True)
    try:
        before = await snapshot(engine, "before")
        async with AsyncSession(engine, expire_on_commit=False) as session:
            rows, unproven = await legacy_candidates(session, owner, legacy)
            assert not unproven
            assert {str(j.id) for j in rows if j.discovery_visible} == expected
            result = await seed_scenarios(session, owner)
        assert len(result["created"]) == 3 and set(result["hidden"]) == expected
        after = await snapshot(engine, "after")
        old = {j["id"]: j for j in before["jobs"]}
        new = {j["id"]: j for j in after["jobs"]}
        assert set(old) <= set(new)
        for key, prior in old.items():
            ignored = {"is_demo", "discovery_visible", "updated_at"} if key in expected else set()
            assert {k: v for k, v in prior.items() if k not in ignored} == {
                k: v for k, v in new[key].items() if k not in ignored}
            if key in expected:
                assert new[key]["status"] == prior["status"] and not new[key]["discovery_visible"]
        changed = [t for t in before["tables"] if before["tables"][t] != after["tables"][t]]
        assert set(changed) == {"enterprises", "enterprise_memberships", "jobs", "job_requirements"}
        # A second explicit replay must not write even timestamps.
        async with AsyncSession(engine, expire_on_commit=False) as session:
            replay = await seed_scenarios(session, owner)
        final = await snapshot(engine, "replay")
        assert after == final
        assert replay["created"] == replay["updated"] == replay["hidden"] == []
        summary = {"created": result["created"], "hidden": result["hidden"],
                   "changedTables": changed, "oldJobsPreserved": len(old),
                   "replayAllTableDigestsIdentical": True,
                   "reportsApplicationsSnapshotsNotificationsUnchanged": True}
        (OUT / "normal-apply-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))
    finally:
        await engine.dispose()


asyncio.run(main())
