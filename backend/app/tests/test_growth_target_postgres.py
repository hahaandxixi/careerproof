"""Real row locks and migration, only inside the matching fixture's cp_test schema."""

import asyncio
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models.analysis import AnalysisTask
from app.models.evidence_growth import EvidenceGrowthTask
from app.tests.test_evidence_growth import plan
from app.tests.test_growth_target_migration import migration
from app.tests.test_real_matching import (
    create_job,
    match_report,
    matching_db,  # noqa: F401
    register,
    upload_materials,
)


async def setup(student, hr):
    await register(hr, "growth-pg-hr@example.com")
    old = await create_job(hr)
    new = await create_job(hr, skills=("SQL",))
    await register(student, "growth-pg-student@example.com", "student")
    resume, _, version = await upload_materials(student)
    base = await match_report(student, old, resume, version)
    created = await student.post(
        f"/api/v1/match-reports/{base['id']}/growth-tasks", json=plan(base)
    )
    assert created.status_code == 201, created.text
    task = created.json()["data"]
    material = {
        "resumeVersionId": resume["versionId"],
        "projectVersionIds": [version["versionId"]], "targetJobId": new["id"],
    }
    return task, material


async def test_postgres_growth_target_migration_preserves_legacy_task(matching_db):  # noqa: F811
    app, factory = matching_db
    engine = factory.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires explicit PostgreSQL cp_test schema")
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        task, material = await setup(student, hr)
        module = migration("0014_growth_target_job.py")
        query = text(
            "SELECT id,created_by,base_report_id,requirement_id,base_snapshot,plan,materials,"
            "analysis_task_id,status,created_at,updated_at FROM evidence_growth_tasks"
        )
        async with engine.begin() as connection:
            schema = await connection.scalar(text("SELECT current_schema()"))
            assert schema.startswith("cp_test_") and len(schema) == 40
            original = deepcopy((await connection.execute(query)).one()._mapping)

            def run(sync, direction):
                with Operations.context(MigrationContext.configure(sync)):
                    getattr(module, direction)()

            # Model-created nullable column has the same named FK as migration.
            await connection.run_sync(lambda sync: run(sync, "downgrade"))
            assert dict((await connection.execute(query)).one()._mapping) == dict(original)
            await connection.run_sync(lambda sync: run(sync, "upgrade"))
            assert dict((await connection.execute(query)).one()._mapping) == dict(original)
            assert await connection.scalar(text(
                "SELECT target_job_id FROM evidence_growth_tasks"
            )) is None
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(text(
                        "UPDATE evidence_growth_tasks SET target_job_id=:invalid"
                    ), {"invalid": uuid4()})
        selected = await student.put(
            f"/api/v1/growth-tasks/{task['id']}/materials", json=material
        )
        assert selected.status_code == 200, selected.text


async def test_postgres_concurrent_target_attach_and_analyze_cannot_change_frozen_job(
    matching_db, monkeypatch,  # noqa: F811
):
    app, factory = matching_db
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires explicit PostgreSQL row locks")
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        task, material = await setup(student, hr)
        url = f"/api/v1/growth-tasks/{task['id']}"
        assert (await student.put(url + "/materials", json=material)).status_code == 200

        class DeferredRunner:
            def submit(self, *args):
                pass

        monkeypatch.setattr(
            "app.api.v1.evidence_growth.FastAPIBackgroundTaskRunner", DeferredRunner
        )
        responses = await asyncio.gather(
            student.post(url + "/analyze", json={}),
            student.put(url + "/materials", json=material),
            student.post(url + "/analyze", json={}),
        )
        assert responses[0].status_code == responses[2].status_code == 202
        assert responses[1].status_code in {200, 409}, responses[1].text
        first = responses[0].json()["data"]["analysisTaskId"]
        assert responses[2].json()["data"]["analysisTaskId"] == first
        async with factory() as session:
            bound = await session.get(EvidenceGrowthTask, UUID(task["id"]))
            pending = await session.get(AnalysisTask, UUID(first))
            assert str(bound.target_job_id) == material["targetJobId"]
            assert pending.input_snapshot["jobId"] == material["targetJobId"]
            assert pending.input_snapshot["growthRequiresReselect"] is True
            analyses = list(await session.scalars(select(AnalysisTask).where(
                AnalysisTask.task_type == "job_match"
            )))
            assert len(analyses) == 2  # One base report and one pending private analysis.
