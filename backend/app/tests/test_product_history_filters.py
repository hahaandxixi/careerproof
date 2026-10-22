"""History/navigation filters operate before paging inside existing permissions."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus, UserRole
from app.models.identity import StudentProfile, User
from app.models.recruitment import Application, Job
from app.tests import test_jobs_api as shared_jobs
from app.tests.test_applications_api import close, setup
from app.tests.test_z57_pagination import seed_owned_applications, source_scope

jobs_db = shared_jobs.jobs_db


async def test_report_history_search_is_owned_global_and_preserves_material_versions(
    jobs_db,
    tmp_path,
    monkeypatch,
):
    hr, student, outsider, job, rid, _, _, factory = await setup(jobs_db, tmp_path, monkeypatch)
    try:
        scope = await source_scope(factory, job["id"], str(rid))
        async with factory() as session:
            original = await session.get(MatchReport, rid)
            material = deepcopy(original.materials_snapshot)
            base = datetime(2026, 1, 1, tzinfo=UTC)
            old_ids = []
            for index in range(43):
                foreign = index == 42
                task = AnalysisTask(
                    created_by=scope["created_by"] if foreign else scope["user_id"],
                    task_type="job_match",
                    status=TaskStatus.COMPLETED,
                )
                session.add(task)
                await session.flush()
                selected = index < 2 or foreign
                snapshot = deepcopy(material)
                snapshot[0]["versionNumber"] = index + 1
                report = MatchReport(
                    analysis_task_id=task.id,
                    job_id=UUID(job["id"]) if selected else uuid4(),
                    candidate_ref=str(scope["student_id"]),
                    candidate_name="合成学生",
                    summary="固定材料",
                    job_snapshot={"title": "目标100%_岗位" if selected else "其他"},
                    materials_snapshot=snapshot,
                    created_at=base + timedelta(minutes=index),
                )
                # Use an actual job FK for all unrelated rows as well.
                if not selected:
                    other_job = Job(
                        enterprise_id=scope["enterprise_id"],
                        created_by=scope["created_by"],
                        title=f"其他岗位{index}",
                        company_name="合成企业",
                        status="published",
                    )
                    session.add(other_job)
                    await session.flush()
                    report.job_id = other_job.id
                session.add(report)
                await session.flush()
                if index < 2:
                    old_ids.append(str(report.id))
            await session.commit()
        response = await student.get(
            "/api/v1/match-reports",
            params={
                "q": "100%_",
                "jobId": job["id"],
                "page": 99,
                "pageSize": 20,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["total"] == 2 and data["page"] == 1
        assert [row["id"] for row in data["items"]] == list(reversed(old_ids))
        # Original report for this job is newer but does not match the old title;
        # filtering must not make the two historical matches appear "latest".
        assert all(row["jobReportCount"] == 3 for row in data["items"])
        assert all(row["isLatestForJob"] is False for row in data["items"])
        assert [row["materials"][0]["versionNumber"] for row in data["items"]] == [2, 1]
        current = (
            await student.get(
                "/api/v1/match-reports",
                params={
                    "jobId": job["id"],
                },
            )
        ).json()["data"]
        assert current["total"] == 3
        assert current["items"][0]["id"] == str(rid)
        assert current["items"][0]["isLatestForJob"] is True
        empty = (
            await student.get(
                "/api/v1/match-reports",
                params={
                    "q": "不存在",
                    "page": 9,
                },
            )
        ).json()["data"]
        assert empty["total"] == 0 and empty["page"] == 1 and empty["items"] == []
    finally:
        await close(hr, student, outsider)


async def test_application_views_and_keyword_count_across_pages(jobs_db, tmp_path, monkeypatch):
    hr, student, outsider, job, rid, _, _, factory = await setup(jobs_db, tmp_path, monkeypatch)
    try:
        scope = await source_scope(factory, job["id"], str(rid))
        rows = await seed_owned_applications(
            factory,
            scope,
            count=27,
            statuses=["replied", "withdrawn"] + ["submitted"] * 25,
        )
        async with factory() as session:
            target_job = await session.get(Job, UUID(rows[0]["job_id"]))
            target_job.title = "目标100%_岗位"
            application = await session.get(Application, UUID(rows[0]["application_id"]))
            application.reply_text, application.reply_kind = "请核对这份固定材料", "continue"
            await session.commit()
        response = await student.get(
            "/api/v1/applications/mine",
            params={
                "view": "action",
                "q": "100%_",
                "page": 99,
            },
        )
        assert response.status_code == 200, response.text
        action = response.json()["data"]
        assert action["total"] == action["page"] == 1
        assert action["items"][0]["id"] == rows[0]["application_id"]
        assert action["items"][0]["replyText"] == "请核对这份固定材料"
        waiting = (await student.get("/api/v1/applications/mine?view=waiting&page=2")).json()[
            "data"
        ]
        assert waiting["total"] == 25 and waiting["page"] == 2
        assert len(waiting["items"]) == 5
        assert all(row["status"] == "submitted" for row in waiting["items"])
        withdrawn = await student.get("/api/v1/applications/mine?view=withdrawn&page=99")
        assert withdrawn.json()["data"]["total"] == 1
        assert withdrawn.json()["data"]["page"] == 1
        assert (await outsider.get("/api/v1/applications/mine?view=action")).status_code == 403
        assert (await student.get("/api/v1/applications/mine?view=unknown")).status_code == 422
    finally:
        await close(hr, student, outsider)


async def test_enterprise_filters_use_same_snapshot_item_before_count_and_page(
    jobs_db,
    tmp_path,
    monkeypatch,
):
    hr, student, outsider, job, rid, _, _, factory = await setup(jobs_db, tmp_path, monkeypatch)
    try:
        await source_scope(factory, job["id"], str(rid))
        required, other_requirement = str(uuid4()), str(uuid4())
        base = datetime(2026, 1, 1, tzinfo=UTC)
        expected = None
        async with factory() as session:
            for index in range(28):
                user = User(
                    email=f"candidate-{index}-{uuid4().hex}@example.test",
                    password_hash="synthetic",
                    display_name="目标100%_姓名" if index == 0 else f"其他候选人{index}",
                    role=UserRole.STUDENT,
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(user_id=user.id)
                session.add(profile)
                await session.flush()
                item = Application(
                    job_id=UUID(job["id"]),
                    student_id=profile.id,
                    report_id=rid,
                    consent_at=base,
                    consent_version="synthetic",
                    status="withdrawn"
                    if index == 27
                    else "replied"
                    if index == 26
                    else "submitted",
                    created_at=base + timedelta(minutes=index),
                    report_snapshot={
                        "summary": "事务回滚演示" if index == 0 else "其他摘要",
                        "items": [
                            {
                                "requirementId": required,
                                "requirementTitle": "容量不足处理" if index == 0 else "核心要求",
                                "skill": "Python",
                                "explanation": "非法输入拒绝" if index == 0 else "其他说明",
                                "aiExplanation": "持久化提交一致性" if index == 0 else None,
                                "verdict": "supported" if index == 0 else "gap",
                            },
                            {
                                "requirementId": other_requirement,
                                "requirementTitle": "其他要求",
                                "verdict": "supported",
                            },
                        ]
                    },
                )
                session.add(item)
                await session.flush()
                if index == 0:
                    expected = str(item.id)
            await session.commit()
        endpoint = f"/api/v1/jobs/{job['id']}/applications"
        filtered = await hr.get(
            endpoint,
            params={
                "requirementId": required,
                "verdict": "supported",
                "page": 99,
            },
        )
        assert filtered.status_code == 200, filtered.text
        data = filtered.json()["data"]
        assert data["total"] == data["page"] == 1
        assert [row["id"] for row in data["items"]] == [expected]
        keyword = await hr.get(endpoint, params={"q": "100%_"})
        assert keyword.json()["data"]["total"] == 1
        assert keyword.json()["data"]["items"][0]["id"] == expected
        for term in ("事务回滚", "容量不足", "非法输入", "持久化"):
            response = await hr.get(endpoint, params={"q": term, "page": 99})
            assert response.status_code == 200, response.text
            found = response.json()["data"]
            assert found["total"] == found["page"] == 1, (term, found)
            assert [row["id"] for row in found["items"]] == [expected]
        replied = (await hr.get(endpoint, params={"status": "replied"})).json()["data"]
        assert replied["total"] == 1 and replied["items"][0]["status"] == "replied"
        assert (await outsider.get(endpoint, params={"q": "100%_"})).status_code == 404
        mine = (await hr.get("/api/v1/jobs/mine")).json()["data"]
        target = next(row for row in mine["items"] if row["id"] == job["id"])
        assert target["applicationCount"] == 27 and target["pendingApplicationCount"] == 26
        public = (await student.get("/api/v1/jobs")).json()["data"]
        assert all(row["applicationCount"] is None for row in public["items"])
    finally:
        await close(hr, student, outsider)
