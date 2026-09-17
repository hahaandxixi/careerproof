"""Exercise the persisted upload-to-report workflow without the production database.

The fixture uses temporary SQLite by default or a unique disposable PostgreSQL
schema when CAREERPROOF_TEST_DATABASE_URL is explicitly configured. Parsers still
execute in their real isolated worker processes; production rows are never used.
"""

import asyncio
import io
import os
import re
import zipfile
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.contracts import AIRequirementAnalysis, EvidenceAnalysis, ModelUsage
from app.agents.evidence_workflow import EvidenceWorkflowOutcome, build_evidence_contexts
from app.core.config import settings
from app.core.database import Base, get_session
from app.main import create_app
from app.models.analysis import (
    AgentStep,
    AiUsageLog,
    AnalysisTask,
    EvidenceSource,
    MatchItem,
    MatchReport,
    SkillEvidence,
)
from app.models.enums import TaskStatus
from app.models.identity import User
from app.models.portfolio import ProjectFile, ProjectVersion, ResumeVersion
from app.services import analysis as analysis_service
from app.services import portfolio as portfolio_service
from app.tests.test_jobs_api import organization, register


@pytest.fixture
async def matching_db(tmp_path, monkeypatch):
    database_url = os.environ.get("CAREERPROOF_TEST_DATABASE_URL")
    schema_name = None
    if database_url:
        if not database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("The integration database must use postgresql+asyncpg")
        schema_name = f"cp_test_{uuid4().hex}"
        assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema_name)
        engine = create_async_engine(
            database_url,
            connect_args={"server_settings": {"search_path": f"{schema_name},public"}},
        )
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'matching.db'}")

        @event.listens_for(engine.sync_engine, "connect")
        def configure_sqlite(connection, _record):
            connection.create_function(
                "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
            )
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    app = create_app()
    schema_created = False
    try:
        if schema_name:
            async with engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            schema_created = True
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[t for t in Base.metadata.sorted_tables if t.name != "knowledge_chunks"],
                    checkfirst=False,
                )
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async def session_override():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        monkeypatch.setattr(analysis_service, "async_session_factory", factory)
        monkeypatch.setattr(portfolio_service, "async_session_factory", factory)
        monkeypatch.setattr("app.api.v1.analysis.async_session_factory", factory)
        monkeypatch.setattr(settings, "storage_base_dir", tmp_path / "materials")
        yield app, factory
    finally:
        app.dependency_overrides.clear()
        if schema_created:
            # Only this fixture's generated schema is removed; never target public.
            assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema_name)
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await engine.dispose()


def source_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "src/report.py",
            "def calculate_total(values):\n"
            "    return sum(value for value in values if value > 0)\n",
        )
    return buffer.getvalue()


async def create_job(owner, *, category="software", skills=("Python",)):
    org = await organization(owner)
    response = await owner.post(
        "/api/v1/jobs",
        json={
            "enterpriseId": org["id"],
            "companyName": org["name"],
            "title": "原始岗位标题",
            "status": "published",
            "category": category,
            "requirements": [
                {"rawText": f"具备{skill}相关实践材料", "skillName": skill} for skill in skills
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def upload_materials(student, *, document: str | None = None):
    response = await student.post(
        "/api/v1/resumes",
        data={"title": "本人简历"},
        files={
            "file": (
                "resume.txt",
                "本人完成Python课程项目，也参与活动策划实践。".encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 202, response.text
    resume = response.json()["data"]
    project_response = await student.post(
        "/api/v1/projects", json={"name": "本人课程实践", "requestId": str(uuid4())}
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()["data"]
    file = (
        ("campaign.txt", document.encode(), "text/plain")
        if document is not None
        else ("source.zip", source_archive(), "application/zip")
    )
    response = await student.post(
        f"/api/v1/projects/{project['id']}/versions",
        data={"requestId": str(uuid4())},
        files={"file": file},
    )
    assert response.status_code == 202, response.text
    version = response.json()["data"]
    for upload in (resume, version):
        task = await student.get(f"/api/v1/analysis-tasks/{upload['taskId']}")
        assert task.status_code == 200, task.text
        assert task.json()["data"]["status"] == "completed", task.text
    return resume, project, version


async def match_report(student, job, resume, version, **extra):
    accepted = await student.post(
        "/api/v1/matches",
        json={
            "jobId": job["id"],
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            **extra,
        },
    )
    assert accepted.status_code == 202, accepted.text
    task_id = accepted.json()["data"]["taskId"]
    task = await student.get(f"/api/v1/analysis-tasks/{task_id}")
    assert task.status_code == 200, task.text
    assert task.json()["data"]["status"] == "completed", task.text
    report_id = task.json()["data"]["reportId"]
    report = await student.get(f"/api/v1/match-reports/{report_id}")
    assert report.status_code == 200, report.text
    return report.json()["data"]


async def test_real_report_survives_login_and_preserves_sources_and_snapshots(matching_db):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, "hr@example.com")
        job = await create_job(owner)
        user = await register(student, "student@example.com", "student")
        resume, project, version = await upload_materials(student)
        # Client supplied identity or text cannot substitute for authenticated material versions.
        report = await match_report(
            student,
            job,
            resume,
            version,
            candidateName="伪造姓名",
            candidateId=str(uuid4()),
            resumeText="我精通一切技术",
            projectFiles=[{"path": "fake.py", "content": "fake"}],
        )
        assert report["candidateId"] == user["id"]
        assert report["candidateName"] == user["displayName"] != "伪造姓名"
        assert report["jobTitle"] == "原始岗位标题"
        assert 0 < report["overallScore"] < 100
        assert all(item["aiConfidence"] is None for item in report["items"])
        assert all(item["formulaVersion"] == "evidence-v3" for item in report["items"])
        assert report["items"][0]["evidence"]["projectVersionId"] == version["versionId"]
        assert {m["id"] for m in report["materials"]} == {resume["versionId"], version["versionId"]}
        history = (await student.get("/api/v1/match-reports")).json()["data"]
        assert [row["id"] for row in history] == [report["id"]]
        async with factory() as session:
            evidence = list(await session.scalars(select(SkillEvidence)))
            assert evidence
            for record in evidence:
                assert str(record.analysis_task_id) == report["taskId"]
                assert record.skill_id is not None and record.evidence_source_id is not None
                source = await session.get(EvidenceSource, record.evidence_source_id)
                assert source.project_file_id is not None
                file = await session.get(ProjectFile, source.project_file_id)
                assert str(file.project_version_id) == version["versionId"]
                assert source.content_hash == file.content_hash
                assert source.locator["lineStart"] >= 1
            items = list(await session.scalars(select(MatchItem)))
            assert items and items[0].evidence_id is not None
        changed_job = await owner.patch(
            f"/api/v1/jobs/{job['id']}", json={"title": "更新后的岗位标题"}
        )
        assert changed_job.status_code == 200, changed_job.text
        next_version = await student.post(
            f"/api/v1/projects/{project['id']}/versions",
            data={"requestId": str(uuid4())},
            files={
                "file": (
                    "new-work.txt",
                    "这是新提交的不同作品材料，不能覆盖之前的分析报告。".encode(),
                    "text/plain",
                )
            },
        )
        assert next_version.status_code == 202, next_version.text
        assert (await student.get(f"/api/v1/match-reports/{report['id']}")).json()["data"] == report
        assert (await student.post("/api/v1/auth/logout")).status_code == 200
        assert (await student.get("/api/v1/match-reports")).status_code == 401
        login = await student.post(
            "/api/v1/auth/login",
            json={
                "email": "student@example.com",
                "password": "jobs-test-password",
            },
        )
        assert login.status_code == 200, login.text
        assert (await student.get("/api/v1/match-reports")).json()["data"] == history
        assert (await student.get(f"/api/v1/match-reports/{report['id']}")).json()["data"] == report
        # Enterprise authors cannot inspect students' privately generated analyses.
        assert (await owner.get(f"/api/v1/match-reports/{report['id']}")).status_code == 404
        assert (await owner.get(f"/api/v1/analysis-tasks/{report['taskId']}")).status_code == 404


@pytest.mark.parametrize(
    "provider_name,model_name", [("bailian", "qwen-plus-test"), ("zhipu", "glm-4.7-flash")]
)
async def test_validated_ai_explanations_and_citations_are_persisted(
    matching_db, monkeypatch, provider_name, model_name
):
    app, factory = matching_db

    async def fake_workflow(result, progress=None):
        del progress
        contexts = build_evidence_contexts(result)
        return EvidenceWorkflowOutcome(
            contexts=contexts,
            analysis=EvidenceAnalysis(
                summary="千问基于规则证据生成的合成测试结论。",
                model=model_name,
                usage=ModelUsage(input_tokens=320, output_tokens=88, latency_ms=640),
                items=[
                    AIRequirementAnalysis(
                        requirement_id=contexts[0].requirement_id,
                        explanation="路由实现为岗位要求提供了可定位的支持。",
                        citation_ids=[contexts[0].evidence[0].citation_id],
                        confidence=0.84,
                    )
                ],
            ),
            provider=provider_name,
            model=model_name,
            fallback_used=False,
            fallback_reason=None,
        )

    monkeypatch.setattr(analysis_service, "run_evidence_workflow", fake_workflow)
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, "ai-owner@example.com")
        job = await create_job(owner)
        await register(student, "ai-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        report = await match_report(student, job, resume, version)

        assert report["analysisMode"] == "ai_evidence"
        assert report["aiProvider"] == provider_name
        assert report["aiModel"] == model_name
        assert report["summary"].startswith("千问基于规则证据")
        item = report["items"][0]
        assert item["aiStatus"] == "validated"
        assert item["aiCitationIds"] == ["R1-E1"]
        assert item["evidenceList"][0]["citationId"] == "R1-E1"
        assert item["aiConfidence"] == 0.84
        task = (await student.get(f"/api/v1/analysis-tasks/{report['taskId']}")).json()["data"]
        assert [step["name"] for step in task["steps"]] == [
            "核对材料版本",
            "检索候选证据",
            "补取并核对证据上下文",
            "计算材料支持度",
            "模型证据分析",
            "校验模型引用",
            "保存可追溯报告",
        ]
        async with factory() as session:
            usage = list(await session.scalars(select(AiUsageLog)))
            steps = list(await session.scalars(select(AgentStep)))
            assert len(usage) == 1 and usage[0].input_tokens == 320
            assert len(steps) == 7
        assert "return sum" in item["evidenceList"][0]["snippet"]
        assert item["evidenceList"][0]["contextComplete"] is True


@pytest.mark.parametrize("failure", ["context", "configuration", "request", "validation"])
async def test_model_stage_failure_still_persists_rule_report(matching_db, monkeypatch, failure):
    app, _factory = matching_db
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "qianwen")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)

    class Provider:
        name = "bailian"

        async def analyze_evidence(self, *, contexts):
            if failure == "request":
                raise TimeoutError("synthetic timeout")
            return EvidenceAnalysis(
                summary="证明具备Python开发能力",
                model="synthetic",
                items=[
                    AIRequirementAnalysis(
                        requirement_id=contexts[0].requirement_id,
                        explanation="测试用例",
                        citation_ids=[],
                        confidence=0.5,
                    )
                ],
            )

    def factory():
        if failure == "configuration":
            raise ValueError("synthetic configuration")
        return Provider()

    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", factory)
    if failure == "context":

        def broken_context(_result):
            raise ValueError("synthetic context")

        monkeypatch.setattr("app.agents.evidence_workflow.build_evidence_contexts", broken_context)
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, "fault-owner@example.com")
        job = await create_job(owner)
        await register(student, "fault-student@example.com", "student")
        resume, _, version = await upload_materials(student)
        report = await match_report(student, job, resume, version)
        assert report["analysisMode"] == "rules" and report["aiFallbackUsed"]
        assert report["overallScore"] == 65
        assert "return sum" in report["items"][0]["evidenceList"][0]["snippet"]
        assert "证明具备" not in report["summary"]
        assert (await student.get(f"/api/v1/match-reports/{report['id']}")).json()["data"] == report


async def test_matching_materials_and_reports_are_owner_scoped(matching_db):
    app, _factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as alice,
        AsyncClient(transport=transport, base_url="http://test") as bob,
    ):
        await register(owner, "hr@example.com")
        job = await create_job(owner)
        await register(alice, "alice@example.com", "student")
        await register(bob, "bob@example.com", "student")
        resume, _project, version = await upload_materials(alice)
        bob_resume, _bob_project, bob_version = await upload_materials(bob)
        report = await match_report(alice, job, resume, version)
        for payload in (
            {
                "resumeVersionId": resume["versionId"],
                "projectVersionIds": [bob_version["versionId"]],
            },
            {
                "resumeVersionId": bob_resume["versionId"],
                "projectVersionIds": [version["versionId"]],
            },
        ):
            response = await bob.post("/api/v1/matches", json={"jobId": job["id"], **payload})
            assert response.status_code == 404, response.text
        assert (await bob.get(f"/api/v1/match-reports/{report['id']}")).status_code == 404
        assert (await bob.get(f"/api/v1/analysis-tasks/{report['taskId']}")).status_code == 404
        assert (await bob.get("/api/v1/match-reports")).json()["data"] == []
        # A frontend submitting only a fabricated candidate payload cannot create a match.
        fake = await bob.post(
            "/api/v1/matches",
            json={
                "jobId": job["id"],
                "candidateName": "Alice",
                "resumeText": "Python",
            },
        )
        assert fake.status_code == 422, fake.text


async def test_pending_materials_are_rejected_and_operations_documents_are_evaluated(matching_db):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, "hr@example.com")
        job = await create_job(owner, category="operations", skills=("活动策划", "钢琴演奏"))
        await register(student, "student@example.com", "student")
        document = (
            "校园社团招新活动策划书\n"
            "活动目标：在新学期开学两周内完成两百名新同学的报名登记，并持续记录报名转化情况。\n"
            "目标受众：重点面向大一新生与需要跨专业组队实践的大二学生，通过班级宣讲介绍活动。\n"
            "活动预算：总费用控制在一千元以内，其中场地物料六百元、宣传印刷三百元、机动费用一百元。\n"
            "执行排期：第一周周一完成报名表设计，周三举办宣讲，第二周周五汇总结果并进行团队复盘。\n"
        )
        resume, _project, version = await upload_materials(student, document=document)
        payload = {
            "jobId": job["id"],
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
        }
        async with factory() as session:
            row = await session.get(ResumeVersion, UUID(resume["versionId"]))
            row.parse_status = "running"
            await session.commit()
        assert (await student.post("/api/v1/matches", json=payload)).status_code == 409
        async with factory() as session:
            row = await session.get(ResumeVersion, UUID(resume["versionId"]))
            row.parse_status = "completed"
            project_version = await session.get(ProjectVersion, UUID(version["versionId"]))
            project_version.analysis_status = "running"
            await session.commit()
        assert (await student.post("/api/v1/matches", json=payload)).status_code == 409
        async with factory() as session:
            row = await session.get(ProjectVersion, UUID(version["versionId"]))
            row.analysis_status = "completed"
            await session.commit()
        report = await match_report(student, job, resume, version)
        assert report["jobCategory"] == "operations"
        items = {item["skill"]: item for item in report["items"]}
        assert 0 < items["活动策划"]["finalScore"] < 100
        assert items["活动策划"]["evidence"]["evidenceType"] == "document_structure"
        assert items["钢琴演奏"]["verdict"] == "unsupported"
        assert items["钢琴演奏"]["finalScore"] is None
        assert report["overallScore"] == items["活动策划"]["finalScore"]


async def test_pending_and_running_matches_coalesce_and_use_frozen_inputs(matching_db, monkeypatch):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    callbacks = []

    class DeferredRunner:
        def submit(self, _background_tasks, callback, *args):
            callbacks.append((callback, args))

    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, "hr@example.com")
        job = await create_job(owner)
        user = await register(student, "student@example.com", "student")
        resume, project, version = await upload_materials(student)
        monkeypatch.setattr("app.api.v1.analysis.FastAPIBackgroundTaskRunner", DeferredRunner)
        payload = {
            "jobId": job["id"],
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
        }
        first = await student.post("/api/v1/matches", json=payload)
        second = await student.post("/api/v1/matches", json=payload)
        assert first.status_code == second.status_code == 202
        task_id = first.json()["data"]["taskId"]
        assert second.json()["data"]["taskId"] == task_id
        assert second.json()["data"]["status"] == "pending"
        assert (
            await owner.patch(f"/api/v1/jobs/{job['id']}", json={"title": "排队后修改的岗位标题"})
        ).status_code == 200
        assert (
            await owner.patch(f"/api/v1/jobs/{job['id']}", json={"requirements": []})
        ).status_code == 409
        new_version = await student.post(
            f"/api/v1/projects/{project['id']}/versions",
            data={"requestId": str(uuid4())},
            files={
                "file": (
                    "new.txt",
                    "这份新版本没有代码实现，不应改变排队任务。".encode(),
                    "text/plain",
                )
            },
        )
        assert new_version.status_code == 202, new_version.text
        async with factory() as session:
            current_user = await session.get(User, UUID(user["id"]))
            current_user.display_name = "排队后修改的姓名"
            await session.commit()
        started, release = asyncio.Event(), asyncio.Event()
        original_isolated = analysis_service.run_isolated

        async def blocked_isolated(*args, **kwargs):
            started.set()
            await release.wait()
            return await original_isolated(*args, **kwargs)

        monkeypatch.setattr(analysis_service, "run_isolated", blocked_isolated)
        callback, args = callbacks[0]
        execution = asyncio.create_task(callback(*args))
        try:
            await asyncio.wait_for(started.wait(), timeout=10)
            third = await student.post("/api/v1/matches", json=payload)
            assert third.status_code == 202, third.text
            assert third.json()["data"] == {"taskId": task_id, "status": "running"}
        finally:
            release.set()
            await asyncio.wait_for(execution, timeout=30)
        # Duplicated callbacks may be scheduled, but only one can claim the task.
        for callback, args in callbacks[1:]:
            await callback(*args)
        task = (await student.get(f"/api/v1/analysis-tasks/{task_id}")).json()["data"]
        assert task["status"] == "completed", task
        report = (await student.get(f"/api/v1/match-reports/{task['reportId']}")).json()["data"]
        assert report["jobTitle"] == job["title"]
        assert report["candidateName"] == user["displayName"]
        assert report["items"][0]["evidence"]["projectVersionId"] == version["versionId"]
        assert {m["id"] for m in report["materials"]} == {resume["versionId"], version["versionId"]}
        async with factory() as session:
            tasks = list(
                await session.scalars(
                    select(AnalysisTask).where(AnalysisTask.task_type == "job_match")
                )
            )
            assert len(tasks) == 1 and tasks[0].attempt == 1
            assert len(list(await session.scalars(select(MatchReport)))) == 1


async def test_failed_match_retry_is_owner_only_atomic_and_not_duplicated(matching_db, monkeypatch):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as stranger,
    ):
        await register(owner, "hr@example.com")
        job = await create_job(owner)
        await register(student, "student@example.com", "student")
        await register(stranger, "stranger@example.com", "student")
        resume, _project, version = await upload_materials(student)
        original_isolated = analysis_service.run_isolated

        async def fail_worker(*_args, **_kwargs):
            raise RuntimeError("internal worker secret must not reach the browser")

        monkeypatch.setattr(analysis_service, "run_isolated", fail_worker)
        response = await student.post(
            "/api/v1/matches",
            json={
                "jobId": job["id"],
                "resumeVersionId": resume["versionId"],
                "projectVersionIds": [version["versionId"]],
            },
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["data"]["taskId"]
        task_url = f"/api/v1/analysis-tasks/{task_id}"
        task = (await student.get(task_url)).json()["data"]
        assert task["status"] == "failed" and task["reportId"] is None
        assert "internal worker secret" not in task["errorMessage"]
        assert (await stranger.post(f"{task_url}/retry")).status_code == 404
        assert (await owner.post(f"{task_url}/retry")).status_code == 404
        async with factory() as session:
            assert list(await session.scalars(select(MatchReport))) == []
            assert list(await session.scalars(select(SkillEvidence))) == []
            assert (await session.get(AnalysisTask, UUID(task_id))).attempt == 1
        monkeypatch.setattr(analysis_service, "run_isolated", original_isolated)
        retry = await student.post(f"{task_url}/retry")
        assert retry.status_code == 202 and retry.json()["data"]["taskId"] == task_id
        completed = (await student.get(task_url)).json()["data"]
        assert completed["status"] == "completed" and completed["errorMessage"] is None
        assert (await student.post(f"{task_url}/retry")).status_code == 409
        await analysis_service.execute_match_task(UUID(task_id))
        async with factory() as session:
            row = await session.get(AnalysisTask, UUID(task_id))
            assert row.status == TaskStatus.COMPLETED and row.attempt == 2
            assert len(list(await session.scalars(select(MatchReport)))) == 1
        history = (await student.get("/api/v1/match-reports")).json()["data"]
        assert len(history) == 1 and history[0]["id"] == completed["reportId"]


async def test_entirely_unsupported_job_has_null_overall_score(matching_db):
    app, _factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, "hr@example.com")
        job = await create_job(owner, category="other", skills=("钢琴演奏",))
        await register(student, "student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        report = await match_report(student, job, resume, version)
        assert report["overallScore"] is None
        assert report["items"][0]["finalScore"] is None
        assert report["items"][0]["verdict"] == "unsupported"
        assert report["items"][0]["evidence"] is None


async def test_evidence_review_is_owner_scoped_and_persisted(matching_db):
    app, _factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as stranger,
    ):
        await register(owner, "hr@example.com")
        job = await create_job(owner)
        await register(student, "student@example.com", "student")
        await register(stranger, "stranger@example.com", "student")
        resume, _project, version = await upload_materials(student)
        report = await match_report(student, job, resume, version)
        item = report["items"][0]
        assert item["confirmationStatus"] == "pending"
        url = f"/api/v1/match-reports/{report['id']}/items/{item['requirementId']}/review"
        assert (await stranger.patch(url, json={"status": "accepted"})).status_code == 404
        assert (await owner.patch(url, json={"status": "accepted"})).status_code == 404
        reviewed = await student.patch(
            url,
            json={"status": "accepted", "note": "已核对路由实现与引用行"},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["data"]["confirmationStatus"] == "accepted"
        refreshed = (await student.get(f"/api/v1/match-reports/{report['id']}")).json()["data"]
        assert refreshed["items"][0]["reviewerNote"] == "已核对路由实现与引用行"
        assert refreshed["items"][0]["confirmedAt"] is not None


async def test_deepseek_web_handoff_is_private_owner_scoped_and_validated(matching_db):
    app, _factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as stranger,
    ):
        await register(owner, "hr@example.com")
        job = await create_job(owner)
        user = await register(student, "student@example.com", "student")
        await register(stranger, "stranger@example.com", "student")
        resume, _project, version = await upload_materials(student)
        report = await match_report(student, job, resume, version)
        url = f"/api/v1/match-reports/{report['id']}/deepseek-web"

        assert (await stranger.get(url)).status_code == 404
        handoff_response = await student.get(url)
        assert handoff_response.status_code == 200, handoff_response.text
        handoff = handoff_response.json()["data"]
        assert handoff["providerUrl"] == "https://chat.deepseek.com/"
        assert user["displayName"] not in handoff["prompt"]
        assert "student@example.com" not in handoff["prompt"]
        claim_texts = [item["claimText"] for item in report["items"] if item.get("claimText")]
        assert all(claim not in handoff["prompt"] for claim in claim_texts)

        response_items = []
        for item in report["items"]:
            citations = [item["evidenceList"][0]["citationId"]] if item["evidenceList"] else []
            boundary = (
                "当前规则暂不支持评估，建议人工核验。"
                if item["verdict"] == "unsupported"
                else "材料中可见相关片段，仍需人工核对。"
            )
            response_items.append(
                {
                    "requirement_id": item["requirementId"],
                    "explanation": boundary,
                    "citation_ids": citations,
                    "information_gap": "静态材料不能确认运行结果和本人贡献。",
                    "suggestion": "补充可审计的运行记录并由独立人员核验。",
                    "confidence": 0.5,
                    "rating": {
                        "level": None,
                        "reason": "现有材料暂不授予实践证据等级。",
                        "criteria": [
                            {
                                "criterion": criterion,
                                "supported": False,
                                "citation_ids": [],
                                "reason": "证据不足。",
                            }
                            for criterion in ("relevance", "operation", "task")
                        ],
                    },
                }
            )
        response = {"summary": "这是材料证据初评，仍需人工核验。", "items": response_items}

        stale = await student.post(url, json={"response": response, "contextDigest": "0" * 64})
        assert stale.status_code == 409

        invalid = {
            **response,
            "items": [dict(response_items[0], citation_ids=["R99-E99"]), *response_items[1:]],
        }
        rejected = await student.post(
            url, json={"response": invalid, "contextDigest": handoff["contextDigest"]}
        )
        assert rejected.status_code == 422
        assert "未通过证据校验" in rejected.json()["message"]

        imported = await student.post(
            url, json={"response": response, "contextDigest": handoff["contextDigest"]}
        )
        assert imported.status_code == 200, imported.text
        saved = imported.json()["data"]
        assert saved["analysisMode"] == "ai_evidence_manual"
        assert saved["aiProvider"] == "deepseek_web"
        assert saved["aiModel"] == "deepseek-web-manual"
        assert saved["summary"] == response["summary"]
        assert all(item["aiStatus"] == "validated" for item in saved["items"])
        assert all(item["aiOrigin"] == "deepseek_web_manual" for item in saved["items"])
