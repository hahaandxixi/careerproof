"""A legacy task-owner/candidate mismatch is audit history, not a personal skill report."""
from uuid import UUID

from httpx import ASGITransport, AsyncClient

from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.tests.test_job_discovery_curation import jobs_db, owner_of, seed_job  # noqa: F401
from app.tests.test_jobs_api import organization, register


async def test_personal_reports_exclude_legacy_candidate_mismatch_but_keep_audit_history(jobs_db):  # noqa: F811
    app, factory = jobs_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as hr,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other,
    ):
        await register(hr, "runtime-identity-hr@example.com")
        org = await organization(hr)
        owner = await owner_of(factory, org["id"])
        user = await register(student, "runtime-identity-student@example.com", "student")
        stranger = await register(other, "runtime-identity-other@example.com", "student")
        job = await seed_job(factory, UUID(org["id"]), owner, title="合成身份回归")
        ids = []
        async with factory() as session:
            for candidate in (user["id"], stranger["id"]):
                task = AnalysisTask(
                    created_by=UUID(user["id"]), task_type="job_match", status=TaskStatus.COMPLETED,
                )
                session.add(task)
                await session.flush()
                report = MatchReport(
                    analysis_task_id=task.id, job_id=job, candidate_ref=candidate,
                    candidate_name="合成历史", summary="历史原文不改",
                    analysis_metadata={"mode": "rules"},
                    job_snapshot={
                        "title": "合成身份回归", "category": "software", "requirements": [],
                    }, materials_snapshot=[],
                )
                session.add(report)
                await session.flush()
                ids.append(str(report.id))
            await session.commit()
        personal = (await student.get("/api/v1/match-reports")).json()["data"]
        assert personal["total"] == 1
        assert [r["id"] for r in personal["items"]] == ids[:1]
        assert personal["items"][0]["jobReportCount"] == 1
        audit = (await student.get("/api/v1/match-reports?scope=all")).json()["data"]
        assert audit["total"] == 2
        assert {r["id"] for r in audit["items"]} == set(ids)
        for rid in ids:
            assert (await student.get("/api/v1/match-reports/"+rid)).status_code == 200
            assert (await other.get("/api/v1/match-reports/"+rid)).status_code == 404
        async with factory() as session:
            saved = await session.get(MatchReport, UUID(ids[1]))
            assert saved.candidate_ref == stranger["id"] and saved.summary == "历史原文不改"
