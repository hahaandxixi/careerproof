"""Synthetic persistence and consent tests; never call a paid model."""

import asyncio
import hashlib
import threading
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.models.analysis import AnalysisTask, MatchItem, MatchReport
from app.models.audit import AuditLog
from app.models.enums import TaskStatus
from app.models.identity import EnterpriseMembership, StudentProfile
from app.models.portfolio import Resume, ResumeVersion
from app.models.recruitment import Application, ApplicationEvent, Job
from app.services.applications import _reply_references, reply_context_for_requirement
from app.tests.test_jobs_api import job_payload, organization, register
from app.tests.test_real_matching import matching_db  # noqa: F401

pytest_plugins = ["app.tests.test_jobs_api"]


async def setup(jobs_db, tmp_path, monkeypatch):
    app, factory = jobs_db
    monkeypatch.setattr(settings, "storage_base_dir", tmp_path)
    enterprise = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    student = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    outsider = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await register(enterprise, "hr@example.com")
    user = await register(student, "student@example.com", "student")
    await register(outsider, "other@example.com")
    org = await organization(enterprise)
    job = (await enterprise.post("/api/v1/jobs", json=job_payload(org))).json()["data"]
    raw = "合成学生简历：Python".encode()
    (tmp_path / "resume.txt").write_bytes(raw)
    async with factory() as session:
        profile = await session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == UUID(user["id"]))
        )
        resume = Resume(student_id=profile.id, title="CP01｜Python 后端｜测试简历")
        task = AnalysisTask(
            created_by=UUID(user["id"]), task_type="job_match", status=TaskStatus.COMPLETED
        )
        session.add_all([resume, task])
        await session.flush()
        version = ResumeVersion(
            resume_id=resume.id,
            version_number=1,
            storage_key="resume.txt",
            mime_type="text/plain",
            content_hash=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            parse_status="completed",
            original_filename="合成简历.txt",
        )
        session.add(version)
        await session.flush()
        report = MatchReport(
            analysis_task_id=task.id,
            job_id=UUID(job["id"]),
            candidate_ref=str(profile.id),
            summary="合成证据报告",
            overall_score=50,
            job_snapshot={"title": job["title"], "category": "software"},
            materials_snapshot=[
                {
                    "kind": "resume",
                    "id": str(version.id),
                    "title": resume.title,
                    "versionNumber": 1,
                    "contentHash": version.content_hash,
                }
            ],
        )
        session.add(report)
        await session.flush()
        session.add(
            MatchItem(
                report_id=report.id,
                requirement_id=UUID(job["requirements"][0]["id"]),
                rule_base_score=0.5,
                weight=1,
                final_score=50,
                verdict="claimed_only",
                explanation="仅见简历声明",
                formula_version="synthetic",
                evidence_snapshot={
                    "skill": "Excel",
                    "requirementTitle": "能够使用Excel分析数据",
                    "claimed": True,
                },
            )
        )
        await session.commit()
        return enterprise, student, outsider, job, report.id, resume.id, raw, factory


async def close(*clients):
    for client in clients:
        await client.aclose()


def test_legacy_unique_title_reply_reference_remains_readable():
    requirement_id = str(uuid4())
    snapshot = {"items": [{
        "requirementId": requirement_id,
        "requirementTitle": "唯一要求",
        "evidenceList": [{"citationId": "R1-E1"}],
    }]}
    reference = [{"requirementId": requirement_id, "citationIds": ["R1-E1"]}]
    assert _reply_references(snapshot, "【唯一要求】\n报告引用编号：R1-E1", reference) == reference


def test_bracketed_requirement_title_keeps_reply_reference_and_block_boundary():
    first_id, second_id = uuid4(), uuid4()
    snapshot = {"items": [
        {"requirementId": str(first_id), "requirementTitle": "【核心】Java后端",
         "evidenceList": [{"citationId": "R1-E1"}]},
        {"requirementId": str(second_id), "requirementTitle": "测试",
         "evidenceList": [{"citationId": "R2-E1"}]},
    ]}
    text = (
        "【第1项：【核心】Java后端】\n请解释本人贡献。\n报告引用编号：R1-E1\n\n"
        "【第2项：测试】\n请补充运行记录。\n报告引用编号：R2-E1"
    )
    references = [
        {"requirementId": str(first_id), "citationIds": ["R1-E1"]},
        {"requirementId": str(second_id), "citationIds": ["R2-E1"]},
    ]
    assert _reply_references(snapshot, text, references) == references
    item = SimpleNamespace(
        id=uuid4(), report_id=uuid4(), report_snapshot=snapshot,
        reply_text=text, reply_references=references, reply_kind="continue",
    )
    context = reply_context_for_requirement(item, first_id)
    assert context is not None
    assert "本人贡献" in context["text"]
    assert "运行记录" not in context["text"]


async def test_explicit_consent_owner_scope_idempotency_and_snapshot(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, resume_id, raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        assert (
            await student.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": False}
            )
        ).status_code == 422
        assert (
            await other.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
            )
        ).status_code == 403
        created = await student.post(
            "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
        )
        assert created.status_code == 201, created.text
        aid = created.json()["data"]["id"]
        frozen_basis = created.json()["data"]["comparisonBasis"]
        assert len(frozen_basis) == 64
        assert (
            await student.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
            )
        ).json()["data"]["id"] == aid
        assert (await other.get(f"/api/v1/jobs/{job['id']}/applications")).status_code == 404
        assert (await other.post(f"/api/v1/applications/{aid}/view")).status_code == 404
        assert (await hr.get(f"/api/v1/match-reports/{rid}")).status_code == 404
        listed = (await hr.get(f"/api/v1/jobs/{job['id']}/applications")).json()["data"]["items"]
        assert (
            len(listed) == 1
            and "report" not in listed[0]
            and listed[0]["dimensions"][0]["verdict"] == "claimed_only"
        )
        async with factory() as session:
            report = await session.get(MatchReport, rid)
            report.summary = "后续修改不覆盖投递快照"
            await session.commit()
        opened = (await hr.post(f"/api/v1/applications/{aid}/view")).json()["data"]
        assert opened["report"]["summary"] == "合成证据报告"
        assert opened["comparisonBasis"] == frozen_basis
        await hr.post(f"/api/v1/applications/{aid}/view")
        assert [e["type"] for e in opened["events"]] == ["submitted", "viewed"]
        async with factory() as session:
            events = list(
                await session.scalars(
                    select(ApplicationEvent).where(ApplicationEvent.application_id == UUID(aid))
                )
            )
            assert len(events) == 2
    finally:
        await close(hr, student, other)


async def test_download_reply_and_withdraw_revoke_every_enterprise_path(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, resume_id, raw, _ = await setup(jobs_db, tmp_path, monkeypatch)
    try:
        aid = (
            await student.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
            )
        ).json()["data"]["id"]
        assert (await hr.post(f"/api/v1/applications/{aid}/resume-download")).status_code == 409
        assert (
            await hr.post(
                f"/api/v1/applications/{aid}/reply",
                json={"kind": "interview", "text": "合成面试邀请"},
            )
        ).status_code == 409
        await hr.post(f"/api/v1/applications/{aid}/view")
        file = await hr.post(f"/api/v1/applications/{aid}/resume-download")
        assert (
            file.status_code == 200
            and file.content == raw
            and "filename*=UTF-8" in file.headers["content-disposition"]
        )
        assert (
            await hr.post(
                f"/api/v1/applications/{aid}/reply", json={"kind": "hired", "text": "非法状态"}
            )
        ).status_code == 422
        replied = await hr.post(
            f"/api/v1/applications/{aid}/reply",
            json={"kind": "continue", "text": "请补充运行记录，合成测试用。"},
        )
        assert replied.status_code == 200, replied.text
        mine = (await student.get("/api/v1/applications/mine")).json()["data"]["items"][0]
        assert mine["status"] == "replied" and mine["replyText"] == "请补充运行记录，合成测试用。"
        assert [e["type"] for e in mine["events"]] == [
            "submitted",
            "viewed",
            "downloaded",
            "replied",
        ]
        assert (await hr.post(f"/api/v1/applications/{aid}/withdraw")).status_code == 403
        assert (await student.post(f"/api/v1/applications/{aid}/withdraw")).status_code == 200
        for endpoint in ("view", "resume-download"):
            assert (await hr.post(f"/api/v1/applications/{aid}/{endpoint}")).status_code == 404
        assert (await hr.get(f"/api/v1/jobs/{job['id']}/applications")).json()["data"][
            "items"
        ] == []
        assert (
            await hr.post(
                f"/api/v1/applications/{aid}/reply", json={"kind": "continue", "text": "不可发送"}
            )
        ).status_code == 404
        resubmitted = await student.post(
            "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
        )
        assert resubmitted.status_code == 201, resubmitted.text
        assert resubmitted.json()["data"]["id"] != aid
        assert (await hr.post(f"/api/v1/applications/{aid}/view")).status_code == 404
    finally:
        await close(hr, student, other)


async def test_reply_links_only_to_its_frozen_requirement_and_citations(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, _resume_id, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        created = await student.post(
            "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
        )
        aid = created.json()["data"]["id"]
        async with factory() as session:
            application = await session.get(Application, UUID(aid))
            snapshot = deepcopy(application.report_snapshot)
            first = snapshot["items"][0]
            first["evidenceList"] = [{"citationId": "R1-E1"}]
            second = deepcopy(first)
            second["requirementId"] = str(uuid4())
            second["evidenceList"] = [{"citationId": "R2-E1"}]
            snapshot["items"].append(second)
            application.report_snapshot = snapshot
            await session.commit()
        await hr.post(f"/api/v1/applications/{aid}/view")
        requirement_id = snapshot["items"][0]["requirementId"]
        title = first.get("requirementTitle") or first.get("skill") or "岗位要求"
        text_body = f"【第1项：{title}】\n请解释你负责的部分。\n报告引用编号：R1-E1"
        path = f"/api/v1/applications/{aid}/reply"
        for reference, text_value in (
            ({"requirementId": str(uuid4()), "citationIds": []}, text_body),
            ({"requirementId": requirement_id, "citationIds": ["R2-E1"]}, text_body),
            ({"requirementId": requirement_id, "citationIds": ["R1-E1"]}, "没有要求标题"),
            (
                {"requirementId": requirement_id, "citationIds": ["R1-E1"]},
                f"【{title}】\n报告引用编号：R1-E1",
            ),
            (
                {"requirementId": requirement_id, "citationIds": ["R1-E1"]},
                f"【第2项：{title}】\n报告引用编号：R1-E1",
            ),
            (
                {"requirementId": second["requirementId"], "citationIds": ["R2-E1"]},
                f"【第1项：{title}】\nR2-E1\n【第2项：{title}】\n没有引用",
            ),
            (
                {"requirementId": requirement_id, "citationIds": ["R1-E1"]},
                f"【第1项：{title}】\n请核对报告引用编号：R1-E10",
            ),
        ):
            rejected = await hr.post(path, json={
                "kind": "continue", "text": text_value, "references": [reference]
            })
            assert rejected.status_code == 422
        sent = await hr.post(path, json={
            "kind": "continue", "text": text_body,
            "references": [{"requirementId": requirement_id, "citationIds": ["R1-E1"]}],
        })
        assert sent.status_code == 200, sent.text
        expected = [{"requirementId": requirement_id, "citationIds": ["R1-E1"]}]
        assert sent.json()["data"]["replyReferences"] == expected
        mine = (await student.get("/api/v1/applications/mine")).json()["data"]["items"][0]
        assert mine["reportId"] == str(rid) and mine["replyReferences"] == expected
        detail = (await student.get(f"/api/v1/applications/{aid}")).json()["data"]
        assert detail["replyReferences"] == expected
        async with factory() as session:
            application = await session.get(Application, UUID(aid))
            assert application.report_snapshot == snapshot
            assert application.reply_references == expected
            application.reply_references = [
                {"requirementId": str(uuid4()), "citationIds": ["R1-E1"]}
            ]
            await session.commit()
        reread = (await student.get(f"/api/v1/applications/{aid}")).json()["data"]
        assert reread["replyReferences"] == []
        async with factory() as session:
            application = await session.get(Application, UUID(aid))
            application.reply_references = expected
            application.reply_text = f"【第1项：{title}】\n请核对报告引用编号：R1-E10"
            await session.commit()
        stale = (await student.get(f"/api/v1/applications/{aid}")).json()["data"]
        assert stale["replyReferences"] == []
        async with factory() as session:
            application = await session.get(Application, UUID(aid))
            application.reply_text = text_body
            await session.commit()
        await student.post(f"/api/v1/applications/{aid}/withdraw")
        withdrawn = (await student.get("/api/v1/applications/mine")).json()["data"]["items"][0]
        assert withdrawn["replyReferences"] == expected
        assert (await hr.get(f"/api/v1/applications/{aid}")).status_code == 404
    finally:
        await close(hr, student, other)


async def test_missing_or_tampered_download_does_not_record_success(jobs_db, tmp_path, monkeypatch):
    hr, student, other, job, rid, resume_id, raw, _ = await setup(jobs_db, tmp_path, monkeypatch)
    try:
        aid = (
            await student.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
            )
        ).json()["data"]["id"]
        await hr.post(f"/api/v1/applications/{aid}/view")
        (tmp_path / "resume.txt").write_bytes(b"tampered")
        assert (await hr.post(f"/api/v1/applications/{aid}/resume-download")).status_code == 409
        (tmp_path / "resume.txt").unlink()
        assert (await hr.post(f"/api/v1/applications/{aid}/resume-download")).status_code == 404
        mine = (await student.get("/api/v1/applications/mine")).json()["data"]["items"][0]
        assert mine["status"] == "viewed" and "downloaded" not in [
            e["type"] for e in mine["events"]
        ]
    finally:
        await close(hr, student, other)


async def test_postgres_withdraw_wins_while_slow_resume_read_is_blocked(
    matching_db,  # noqa: F811
    tmp_path,
    monkeypatch,
):
    """While the resume read blocks, the delivery row lock must already be released.

    On PostgreSQL a withdraw that has to wait for the download's row lock cannot commit
    while the read is in progress; on the old lock-spanning implementation this withdraw
    times out, and after the read the download would still return the file.
    """
    hr, student, other, job, rid, resume_id, raw, factory = await setup(
        matching_db, tmp_path, monkeypatch
    )
    try:
        if factory.kw["bind"].dialect.name != "postgresql":
            pytest.skip("Requires an explicitly configured isolated PostgreSQL schema")
        aid = (
            await student.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
            )
        ).json()["data"]["id"]
        await hr.post(f"/api/v1/applications/{aid}/view")
        entered = threading.Event()
        release = threading.Event()

        def slow_read(path):
            entered.set()
            assert release.wait(timeout=15), "slow read was never released"
            return path.read_bytes()

        monkeypatch.setattr("app.services.applications._read_resume_bytes", slow_read)
        download = asyncio.create_task(hr.post(f"/api/v1/applications/{aid}/resume-download"))
        try:
            async def wait_for_file_read():
                while not entered.is_set():
                    assert not download.done(), "download never entered the file read"
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_file_read(), timeout=5)
            withdraw = asyncio.create_task(student.post(f"/api/v1/applications/{aid}/withdraw"))
            withdrawn = await asyncio.wait_for(withdraw, timeout=5)
            assert withdrawn.status_code == 200, withdrawn.text
            release.set()
            # The student withdrew while the file was still being read: the enterprise gets
            # no file, and no downloaded event or status may survive the denied delivery.
            response = await asyncio.wait_for(download, timeout=5)
        finally:
            release.set()
            if not download.done():
                download.cancel()
            await asyncio.gather(download, return_exceptions=True)
        assert response.status_code == 404, response.text
        assert raw not in response.content
        async with factory() as session:
            application = await session.get(Application, UUID(aid))
            assert application.status == "withdrawn"
            assert "downloaded" not in list(
                await session.scalars(
                    select(ApplicationEvent.event_type).where(
                        ApplicationEvent.application_id == UUID(aid)
                    )
                )
            )
        assert (await hr.post(f"/api/v1/applications/{aid}/resume-download")).status_code == 404
    finally:
        await close(hr, student, other)


async def test_archiving_is_recoverable_owner_scoped_and_preserves_report(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, resume_id, raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        path = f"/api/v1/materials/resume/{resume_id}/archive"
        assert (await hr.patch(path, json={"archived": True})).status_code == 403
        assert (await student.patch(path, json={"archived": True})).status_code == 200
        assert (await student.get("/api/v1/resumes")).json()["data"] == []
        archived = (await student.get("/api/v1/resumes?includeArchived=true")).json()["data"]
        assert len(archived) == 1 and archived[0]["isArchived"] is True
        assert (await student.get(f"/api/v1/match-reports/{rid}")).status_code == 200
        assert (tmp_path / "resume.txt").read_bytes() == raw
        assert (await student.patch(path, json={"archived": False})).status_code == 200
        assert len((await student.get("/api/v1/resumes")).json()["data"]) == 1
        async with factory() as session:
            actions = list(
                await session.scalars(
                    select(AuditLog.action).where(AuditLog.resource_id == str(resume_id))
                )
            )
            assert actions == ["material.archive", "material.restore"]
    finally:
        await close(hr, student, other)


async def test_closed_job_and_other_student_report_cannot_be_submitted(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, resume_id, raw, _ = await setup(jobs_db, tmp_path, monkeypatch)
    second = AsyncClient(transport=ASGITransport(app=jobs_db[0]), base_url="http://test")
    try:
        await register(second, "second@example.com", "student")
        assert (
            await second.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
            )
        ).status_code == 404
        await hr.patch(f"/api/v1/jobs/{job['id']}", json={"status": "closed"})
        assert (
            await student.post(
                "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
            )
        ).status_code == 409
    finally:
        await close(hr, student, other, second)


async def test_daily_limit_and_membership_revocation_fail_closed(jobs_db, tmp_path, monkeypatch):
    hr, student, other, job, rid, resume_id, raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        async with factory() as session:
            report = await session.get(MatchReport, rid)
            current_job = await session.get(Job, UUID(job["id"]))
            for index in range(20):
                prior_job = Job(
                    enterprise_id=current_job.enterprise_id,
                    created_by=current_job.created_by,
                    title=f"合成限额岗位 {index}",
                    company_name=current_job.company_name,
                    status="published",
                )
                session.add(prior_job)
                await session.flush()
                session.add(
                    Application(
                        job_id=prior_job.id,
                        student_id=UUID(report.candidate_ref),
                        report_id=rid,
                        report_snapshot={"summary": "合成限额记录"},
                        consent_at=datetime.now(UTC),
                        consent_version="application-report-v1",
                    )
                )
            await session.commit()
        payload = {"reportId": str(rid), "shareConsent": True}
        limited = await student.post("/api/v1/applications", json=payload)
        assert limited.status_code == 429
        assert len((await student.get("/api/v1/applications/mine")).json()["data"]["items"]) == 20
        # An existing consent remains readable only while the caller is a current member.
        prior = (await student.get("/api/v1/applications/mine")).json()["data"]["items"][0]
        aid = prior["id"]
        assert (await hr.post(f"/api/v1/applications/{aid}/view")).status_code == 200
        async with factory() as session:
            membership = await session.scalar(
                select(EnterpriseMembership).where(
                    EnterpriseMembership.enterprise_id == current_job.enterprise_id
                )
            )
            membership.is_active = False
            await session.commit()
        assert (await hr.get(f"/api/v1/jobs/{prior['jobId']}/applications")).status_code == 404
        assert (await hr.post(f"/api/v1/applications/{aid}/view")).status_code == 404
        assert (await hr.post(f"/api/v1/applications/{aid}/resume-download")).status_code == 404
        assert (
            await hr.post(
                f"/api/v1/applications/{aid}/reply",
                json={"kind": "continue", "text": "权限已撤销，不可发送"},
            )
        ).status_code == 404
    finally:
        await close(hr, student, other)
