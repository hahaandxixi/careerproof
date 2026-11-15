"""Read-policy regression: exact provenance + creator, never title, skill or analysis mode."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.models.identity import StudentProfile
from app.models.recruitment import Application
from app.repositories.jobs import JobRepository
from app.tests.test_job_discovery_curation import jobs_db, owner_of, seed_job  # noqa: F401
from app.tests.test_jobs_api import organization, register
from app.tools import fixture_provenance


def test_only_matrix_diagnostic_is_excluded_not_curated_experience_scenarios():
    expected = {
        UUID("1233f1e2-169f-4ea5-a5a0-542fa940e897"):
            UUID("568df462-33af-4824-9ebd-11a9b2760e0a"),
    }
    assert expected == fixture_provenance.FIXTURE_JOB_OWNERS


async def test_fixture_discovery_default_history_and_authorized_direct_access(jobs_db, monkeypatch):  # noqa: F811
    app, factory = jobs_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as hr,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger,
    ):
        await register(hr, "provenance-hr@example.com")
        org = await organization(hr)
        owner = await owner_of(factory, org["id"])
        user = await register(student, "provenance-student@example.com", "student")
        await register(stranger, "provenance-stranger@example.com", "student")
        fixture_id = await seed_job(factory, UUID(org["id"]), owner, title="任意标题")
        normal_id = await seed_job(
            factory, UUID(org["id"]), owner, title="Kubernetes 与 Python 规则研究",
        )
        owner_mismatch_id = await seed_job(factory, UUID(org["id"]), owner, title="合成验收")
        monkeypatch.setattr(fixture_provenance, "FIXTURE_JOB_OWNERS", {
            fixture_id: owner, owner_mismatch_id: uuid4(),
        })
        listing = (await student.get("/api/v1/jobs?pageSize=1")).json()["data"]
        assert listing["total"] == 2
        second = (await student.get("/api/v1/jobs?pageSize=1&page=2")).json()["data"]
        assert {UUID(row["id"]) for row in [*listing["items"], *second["items"]]} == {
            normal_id, owner_mismatch_id,
        }
        assert (await student.get(f"/api/v1/jobs/{fixture_id}")).status_code == 200
        managed = (await hr.get("/api/v1/jobs/mine")).json()["data"]
        assert managed["total"] == 2
        assert {UUID(row["id"]) for row in managed["items"]} == {normal_id, owner_mismatch_id}
        job_detail = (await hr.get(f"/api/v1/jobs/{fixture_id}")).json()["data"]
        assert job_detail["recordProvenance"] == "test_fixture"
        assert (await hr.get(f"/api/v1/jobs/{fixture_id}/applications")).status_code == 404
        assert (await hr.get(f"/api/v1/jobs/{owner_mismatch_id}/applications")).status_code == 200
        async with factory() as session:
            candidates = await JobRepository(session).recommendation_candidates(100)
            assert {job.id for job in candidates} == {normal_id, owner_mismatch_id}
            report_ids = []
            for index, job_id in enumerate([normal_id, fixture_id]):
                task = AnalysisTask(
                    created_by=UUID(user["id"]), task_type="job_match", status=TaskStatus.COMPLETED,
                )
                session.add(task)
                await session.flush()
                report = MatchReport(analysis_task_id=task.id, job_id=job_id,
                                     candidate_ref=user["id"], candidate_name="记录所有者",
                                     summary="保存原文不变", analysis_metadata={"mode": "rules"},
                                     job_snapshot={
                                         "title": "固定岗位原文", "category": "software",
                                         "requirements": [],
                                     },
                                     materials_snapshot=[],
                                     created_at=datetime.now(UTC) + timedelta(seconds=index))
                session.add(report)
                await session.flush()
                report_ids.append(report.id)
            student_id = await session.scalar(
                select(StudentProfile.id).where(StudentProfile.user_id == UUID(user["id"]))
            )
            application = Application(
                job_id=fixture_id, student_id=student_id, report_id=report_ids[1],
                report_snapshot={"summary": "固定投递原文", "items": []},
                consent_at=datetime.now(UTC), consent_version="application-report-v1",
            )
            session.add(application)
            await session.flush()
            application_id = application.id
            await session.commit()
        assert (await student.get(f"/api/v1/applications/{application_id}")).status_code == 200
        product_detail = await student.get(f"/api/v1/applications/{application_id}?scope=product")
        assert product_detail.status_code == 404
        product_mine = (await student.get("/api/v1/applications/mine?scope=product")).json()["data"]
        assert product_mine["total"] == 0 and product_mine["items"] == []
        audit_mine = (await student.get("/api/v1/applications/mine?scope=all")).json()["data"]
        assert audit_mine["total"] == 1 and audit_mine["items"][0]["id"] == str(application_id)
        assert (await hr.get(f"/api/v1/applications/{application_id}")).status_code == 404
        assert (await hr.post(f"/api/v1/applications/{application_id}/view")).status_code == 404
        verification = await hr.get(f"/api/v1/applications/{application_id}/verification")
        assert verification.status_code == 404
        normal, fixture = map(str, report_ids)
        default = (await student.get("/api/v1/match-reports")).json()["data"]
        assert default["total"] == 1 and default["items"][0]["id"] == normal
        assert default["items"][0]["analysisMode"] == "rules", "ordinary rules reports are retained"
        audit = (await student.get("/api/v1/match-reports?scope=all")).json()["data"]
        assert audit["total"] == 2
        fixture_row = next(row for row in audit["items"] if row["id"] == fixture)
        assert fixture_row["recordProvenance"] == "test_fixture"
        direct = await student.get(f"/api/v1/match-reports/{fixture}")
        assert direct.status_code == 200 and direct.json()["data"]["summary"] == "保存原文不变"
        hidden = await student.get(f"/api/v1/match-reports/{fixture}?scope=product")
        assert hidden.status_code == 404
        normal_detail = await student.get(f"/api/v1/match-reports/{normal}?scope=product")
        assert normal_detail.status_code == 200
        assert normal_detail.json()["data"]["summary"] == "保存原文不变"
        assert (await stranger.get(f"/api/v1/match-reports/{fixture}")).status_code == 404
        assert (await stranger.get("/api/v1/match-reports?scope=all")).json()["data"]["total"] == 0
        for target in (normal, fixture):
            comparison = await student.get(
                f"/api/v1/match-reports/{fixture}/comparison/{target}",
            )
            assert comparison.status_code == 409
        async with factory() as session:
            saved = await session.get(MatchReport, report_ids[1])
            assert saved.summary == "保存原文不变" and saved.analysis_metadata == {"mode": "rules"}


async def test_retired_demo_keeps_authorized_direct_access(jobs_db, monkeypatch):  # noqa: F811
    app, factory = jobs_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as hr,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger,
    ):
        await register(hr, "retired-demo-hr@example.com")
        org = await organization(hr)
        owner = await owner_of(factory, org["id"])
        user = await register(student, "retired-demo-student@example.com", "student")
        await register(stranger, "retired-demo-stranger@example.com", "student")
        title = "接口测试开发实习生"
        active_id = await seed_job(factory, UUID(org["id"]), owner, title=title, is_demo=True)
        retired_id = await seed_job(factory, UUID(org["id"]), owner, title=title, is_demo=True)
        monkeypatch.setattr(fixture_provenance, "RETIRED_DEMO_JOB", retired_id)
        monkeypatch.setattr(fixture_provenance, "RETIRED_DEMO_CREATOR", uuid4())
        wrong_owner = (await student.get("/api/v1/jobs")).json()["data"]
        assert wrong_owner["total"] == 2
        monkeypatch.setattr(fixture_provenance, "RETIRED_DEMO_CREATOR", owner)

        for client, path in [
            (student, "/api/v1/jobs?pageSize=1"), (hr, "/api/v1/jobs/mine?pageSize=1"),
        ]:
            result = (await client.get(path)).json()["data"]
            assert result["total"] == 1 and result["items"][0]["id"] == str(active_id)
        assert (await student.get(f"/api/v1/jobs/{retired_id}")).status_code == 200
        assert (await hr.get(f"/api/v1/jobs/{retired_id}/applications")).status_code == 200

        async with factory() as session:
            candidates = await JobRepository(session).recommendation_candidates(1)
            assert [job.id for job in candidates] == [active_id]
            ids = []
            for job_id in [active_id, retired_id]:
                task = AnalysisTask(
                    created_by=UUID(user["id"]), task_type="job_match", status=TaskStatus.COMPLETED,
                )
                session.add(task)
                await session.flush()
                report = MatchReport(
                    analysis_task_id=task.id, job_id=job_id,
                    candidate_ref=user["id"], candidate_name="记录所有者",
                    summary="历史原文仍可查阅", analysis_metadata={"mode": "rules"},
                    job_snapshot={"title": title, "category": "software", "requirements": []},
                    materials_snapshot=[],
                )
                session.add(report)
                await session.flush()
                ids.append(str(report.id))
            await session.commit()
        active_report, retired_report = ids
        for view in ["reports", "jobs"]:
            path = f"/api/v1/match-reports?scope=product&view={view}&pageSize=1"
            product = (await student.get(path)).json()["data"]
            assert product["total"] == 1 and product["items"][0]["id"] == active_report
        archived = (await student.get("/api/v1/match-reports?scope=all")).json()["data"]
        assert {row["id"] for row in archived["items"]} == set(ids)
        assert all(row["recordProvenance"] is None for row in archived["items"])
        direct_path = f"/api/v1/match-reports/{retired_report}?scope=product"
        direct = await student.get(direct_path)
        assert direct.status_code == 200 and direct.json()["data"]["summary"] == "历史原文仍可查阅"
        assert (await stranger.get(direct_path)).status_code == 404

