"""Job discovery curation: hidden samples, enterprise postings, access by id, idempotent import.

The discovery predicate is asserted through the real HTTP endpoints and the real
repository, on a temporary SQLite database. PostgreSQL behaviour is not covered here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.main import create_app
from app.models.identity import EnterpriseMembership, User
from app.models.recruitment import Job, JobRequirement
from app.repositories.jobs import JobRepository
from app.tests.test_jobs_api import organization, register

BACKEND = Path(__file__).resolve().parents[2]


def _load_importer():
    path = BACKEND / "scripts" / "import_market_scenarios.py"
    spec = importlib.util.spec_from_file_location("import_market_scenarios", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def jobs_db(tmp_path):
    """Temporary SQLite with the real app wired the same way as the jobs API suite."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'curation.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection, _record):
        connection.create_function(
            "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
        )
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[t for t in Base.metadata.sorted_tables if t.name != "knowledge_chunks"],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = session_override
    try:
        yield app, factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def owner_of(factory, enterprise_id) -> UUID:
    async with factory() as session:
        value = await session.scalar(
            select(EnterpriseMembership.user_id).where(
                EnterpriseMembership.enterprise_id == UUID(enterprise_id)
            )
        )
    assert value is not None, "the enterprise has a member"
    return value


async def seed_job(
    factory,
    enterprise_id,
    created_by,
    *,
    title: str,
    status: str = "published",
    is_demo: bool = False,
    visible: bool = True,
    requirements: int = 0,
) -> UUID:
    async with factory() as session:
        job = Job(
            enterprise_id=enterprise_id,
            created_by=created_by,
            title=title,
            company_name="测试企业",
            description=f"{title} 描述",
            status=status,
            is_demo=is_demo,
            discovery_visible=visible,
        )
        session.add(job)
        await session.flush()
        for index in range(requirements):
            session.add(
                JobRequirement(
                    job_id=job.id,
                    raw_text=f"要求 {index}",
                    skill_name=f"skill-{index}",
                    weight=1,
                    normalized_status="pending",
                )
            )
        await session.commit()
        return job.id


async def test_hidden_sample_is_not_counted_or_paged_while_enterprise_jobs_stay(jobs_db):
    app, factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "curator-ent@example.com")
        org = await organization(client, "真实企业")
        creator = await owner_of(factory, org["id"])
        visible = [
            await seed_job(factory, UUID(org["id"]), creator, title=f"企业岗位 {i}", requirements=2)
            for i in range(3)
        ]
        hidden = await seed_job(
            factory,
            UUID(org["id"]),
            creator,
            title="旧合成样例",
            is_demo=True,
            visible=False,
        )
        closed = await seed_job(
            factory, UUID(org["id"]), creator, title="已关闭岗位", status="closed"
        )

        first = (await client.get("/api/v1/jobs", params={"pageSize": 2})).json()["data"]
        second = (await client.get("/api/v1/jobs", params={"pageSize": 2, "page": 2})).json()[
            "data"
        ]
        ids = {row["id"] for row in first["items"] + second["items"]}

        assert first["total"] == 3, "hidden or closed postings must not be counted"
        assert len(first["items"]) == 2 and len(second["items"]) == 1
        assert ids == {str(value) for value in visible}
        assert str(hidden) not in ids and str(closed) not in ids
        # The sample marker travels with the row, so the UI can label it.
        assert all(row["isDemo"] is False for row in first["items"])


async def test_hidden_job_keeps_its_id_reachable_and_stays_in_owner_management(jobs_db):
    app, factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "owner-ent@example.com")
        org = await organization(client, "归属企业")
        creator = await owner_of(factory, org["id"])
        hidden = await seed_job(
            factory, UUID(org["id"]), creator, title="收起的样例", is_demo=True, visible=False
        )

        by_id = await client.get(f"/api/v1/jobs/{hidden}")
        assert by_id.status_code == 200, "a hidden but published posting stays readable by id"
        assert by_id.json()["data"]["discoveryVisible"] is False
        assert by_id.json()["data"]["isDemo"] is True

        mine = (await client.get("/api/v1/jobs/mine", params={"pageSize": 50})).json()["data"]
        assert str(hidden) in {row["id"] for row in mine["items"]}, "owner still manages it"


async def test_another_enterprise_cannot_manage_and_closed_stays_hidden(jobs_db):
    app, factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as a:
        await register(a, "a-ent@example.com")
        org = await organization(a, "A 企业")
        creator = await owner_of(factory, org["id"])
        closed = await seed_job(
            factory, UUID(org["id"]), creator, title="A 关闭岗位", status="closed"
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as b:
        await register(b, "b-ent@example.com")
        assert (await b.get(f"/api/v1/jobs/{closed}")).status_code == 404
        mine = (await b.get("/api/v1/jobs/mine", params={"pageSize": 50})).json()["data"]
        assert str(closed) not in {row["id"] for row in mine["items"]}


async def test_recommendation_candidates_share_the_discovery_predicate(jobs_db):
    app, factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "rec-ent@example.com")
        org = await organization(client, "推荐企业")
        creator = await owner_of(factory, org["id"])
        shown = await seed_job(factory, UUID(org["id"]), creator, title="可推荐岗位")
        hidden = await seed_job(
            factory, UUID(org["id"]), creator, title="收起样例", is_demo=True, visible=False
        )

    async with factory() as session:
        candidates = {job.id for job in await JobRepository(session).recommendation_candidates(100)}
    assert shown in candidates
    assert hidden not in candidates, "a curated-away sample must not return through recommendations"


async def test_import_plan_lists_evidence_and_apply_is_idempotent(jobs_db):
    app, factory = jobs_db
    importer = _load_importer()
    payload = importer.load_scenarios()
    legacy_titles = sorted(importer.legacy_titles())
    assert legacy_titles, "the legacy catalog is expected in demo/jobs.json"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "demo-ent@example.com")
        org = await organization(client, payload["companyName"])
        creator = await owner_of(factory, org["id"])
        old_org = await organization(client, importer.LEGACY_COMPANY)
        legacy = await seed_job(factory, UUID(old_org["id"]), creator, title=legacy_titles[0])
    async with factory() as session:
        old = await session.get(Job, legacy)
        old.company_name = importer.LEGACY_COMPANY
        old.description = importer.LEGACY_DESCRIPTION
        spec = next(
            s
            for s in __import__("json").loads(importer.LEGACY_CATALOG.read_text(encoding="utf-8"))
            if s["title"] == old.title
        )
        session.add_all(
            [
                JobRequirement(
                    job_id=legacy,
                    raw_text=r["rawText"],
                    skill_name=r["skillName"],
                    weight=r["weight"],
                    is_required=r["isRequired"],
                )
                for r in spec["requirements"]
            ]
        )
        await session.commit()

    async with factory() as session:
        plan = await importer.build_plan(session, payload, UUID(org["id"]), UUID(old_org["id"]))
        assert plan["targetEnterprise"]["resolved"] is True
        assert [row["action"] for row in plan["scenarios"]] == ["create"] * 3
        assert [row["jobId"] for row in plan["legacyToHide"]] == [str(legacy)]
        legacy_before = await session.get(Job, legacy)
        assert legacy_before.discovery_visible is True

    async with factory() as session:
        first = await importer.apply_plan(session, payload, UUID(org["id"]), UUID(old_org["id"]))
    assert len(first["created"]) == 3 and first["hidden"] == [str(legacy)]

    async with factory() as session:
        second = await importer.apply_plan(session, payload, UUID(org["id"]), UUID(old_org["id"]))
        assert second["created"] == [], "re-running must reuse the created scenarios"
        assert second["updated"] == [], "replay must be a true no-op"
        assert second["hidden"] == [], "already-hidden legacy postings are left alone"

        count = await session.scalar(
            select(func.count()).select_from(Job).where(Job.enterprise_id == UUID(org["id"]))
        )
        assert count == 3, "three new scenarios in a separate enterprise, no duplicates"

        scenarios = list(
            await session.scalars(
                select(Job).where(
                    Job.enterprise_id == UUID(org["id"]),
                    Job.title.in_([item["title"] for item in payload["scenarios"]]),
                )
            )
        )
        assert all(
            job.is_demo and job.discovery_visible and job.status == "published" for job in scenarios
        )
        requirement_counts = {
            job.id: await session.scalar(
                select(func.count())
                .select_from(JobRequirement)
                .where(JobRequirement.job_id == job.id)
            )
            for job in scenarios
        }
        assert all(value == 5 for value in requirement_counts.values())

        legacy_after = await session.get(Job, legacy)
        assert legacy_after.discovery_visible is False
        assert legacy_after.status == "published", "curation must not close the old posting"


async def test_apply_refuses_unconfirmed_enterprise(jobs_db):
    app, factory = jobs_db
    importer = _load_importer()
    payload = importer.load_scenarios()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "wrong-ent@example.com")
        org = await organization(client, "不是演示企业")
    async with factory() as session:
        with pytest.raises(ValueError, match="does not match"):
            await importer.apply_plan(session, payload, UUID(org["id"]))


async def curated_org(jobs_db, email="curation-guard@example.com"):
    app, factory = jobs_db
    importer = _load_importer()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, email)
        org = await organization(client, importer.load_scenarios()["companyName"])
    return importer, factory, UUID(org["id"])


async def test_replay_keeps_closed_hidden_sample_and_exact_timestamps(jobs_db):
    importer, factory, org = await curated_org(jobs_db)
    async with factory() as session:
        first = await importer.apply_plan(session, importer.load_scenarios(), org)
        job = await session.get(Job, UUID(first["created"][0]))
        job.status, job.discovery_visible = "closed", False
        await session.commit()
        await session.refresh(job)  # Compare values after the same SQLite round-trip.
        before = (job.id, job.status, job.discovery_visible, job.updated_at)
    async with factory() as session:
        replay = await importer.apply_plan(session, importer.load_scenarios(), org)
        job = await session.get(Job, before[0])
        assert replay["created"] == replay["updated"] == replay["hidden"] == []
        assert (job.id, job.status, job.discovery_visible, job.updated_at) == before


@pytest.mark.parametrize("duplicate", [False, True])
async def test_import_refuses_same_title_without_curated_origin(jobs_db, duplicate):
    importer, factory, org = await curated_org(jobs_db)
    owner = await owner_of(factory, str(org))
    for _ in range(2 if duplicate else 1):
        await seed_job(
            factory, org, owner, title=importer.load_scenarios()["scenarios"][0]["title"]
        )
    async with factory() as session:
        with pytest.raises(ValueError, match="Ambiguous|not an unchanged"):
            await importer.apply_plan(session, importer.load_scenarios(), org)
        assert await session.scalar(select(func.count()).select_from(Job)) == (
            2 if duplicate else 1
        )


async def test_import_rejects_inactive_owner_before_any_write(jobs_db):
    importer, factory, org = await curated_org(jobs_db)
    owner = await owner_of(factory, str(org))
    async with factory() as session:
        user = await session.get(User, owner)
        user.is_active = False
        await session.commit()
    async with factory() as session:
        with pytest.raises(ValueError, match="exactly one active"):
            await importer.apply_plan(session, importer.load_scenarios(), org)
        assert await session.scalar(select(func.count()).select_from(Job)) == 0


async def test_plan_database_enforces_read_only(jobs_db):
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    importer, factory, org = await curated_org(jobs_db)
    async with factory() as session:
        await importer.enable_read_only(session)
        await importer.build_plan(session, importer.load_scenarios(), org)
        with pytest.raises(OperationalError, match="readonly"):
            await session.execute(text("UPDATE enterprises SET description='should-not-write'"))


async def test_legacy_title_alone_is_not_origin_evidence(jobs_db):
    importer, factory, org = await curated_org(jobs_db)
    owner = await owner_of(factory, str(org))
    from app.models.identity import Enterprise

    async with factory() as session:
        old = Enterprise(name=importer.LEGACY_COMPANY)
        session.add(old)
        await session.flush()
        from app.models.enums import MembershipRole

        session.add(
            EnterpriseMembership(
                enterprise_id=old.id, user_id=owner, role=MembershipRole.OWNER, is_active=True
            )
        )
        await session.commit()
        old_id = old.id
    suspicious = await seed_job(factory, old_id, owner, title=sorted(importer.legacy_titles())[0])
    async with factory() as session:
        plan = await importer.build_plan(session, importer.load_scenarios(), org, old_id)
        assert plan["legacyToHide"] == [] and plan["preservedUnproven"] == [str(suspicious)]
        result = await importer.apply_plan(session, importer.load_scenarios(), org, old_id)
        assert result["hidden"] == []
        assert (await session.get(Job, suspicious)).discovery_visible


async def test_fresh_demo_seed_creates_only_three_and_replays_without_writes(jobs_db):
    app, factory = jobs_db
    importer = _load_importer()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user = await register(client, "fresh-demo@example.com")
    async with factory() as session:
        first = await importer.seed_scenarios(session, UUID(user["id"]))
        assert len(first["created"]) == 3 and first["hidden"] == []
    async with factory() as session:
        second = await importer.seed_scenarios(session, UUID(user["id"]))
        assert second["created"] == second["updated"] == second["hidden"] == []
        assert await session.scalar(select(func.count()).select_from(Job)) == 3
        assert len(await JobRepository(session).recommendation_candidates(100)) == 3
