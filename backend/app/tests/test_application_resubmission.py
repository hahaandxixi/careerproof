"""Re-consent creates a new application; withdrawn access is never revived."""

import asyncio
from copy import deepcopy
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.models.recruitment import Application
from app.tests.test_applications_api import close, setup

pytest_plugins = ["app.tests.test_real_matching"]


@pytest.mark.parametrize("new_report", [False, True])
async def test_reconsent_keeps_old_snapshot_and_revocation(matching_db, tmp_path, monkeypatch,
                                                         new_report):
    hr, student, other, job, rid, _, _, factory = await setup(
        matching_db, tmp_path, monkeypatch
    )
    try:
        payload = {"reportId": str(rid), "shareConsent": True}
        original = (await student.post("/api/v1/applications", json=payload)).json()["data"]
        old_id = original["id"]
        old_notice = (await hr.get("/api/v1/notifications")).json()["data"]["items"][0]["id"]
        await hr.post(f"/api/v1/applications/{old_id}/view")
        await hr.post(f"/api/v1/applications/{old_id}/reply",
                      json={"kind": "continue", "text": "请补充合成运行记录"})
        await student.post(f"/api/v1/applications/{old_id}/withdraw")
        async with factory() as session:
            old = await session.get(Application, UUID(old_id))
            snapshot = deepcopy(old.report_snapshot)
            old_version = old.version
            old_consent = old.consent_at
            report = await session.get(MatchReport, rid)
            if new_report:
                task = AnalysisTask(created_by=(await session.get(
                    AnalysisTask, report.analysis_task_id)).created_by,
                    task_type="job_match", status=TaskStatus.COMPLETED)
                session.add(task)
                await session.flush()
                report = MatchReport(analysis_task_id=task.id, job_id=report.job_id,
                                     candidate_ref=report.candidate_ref,
                                     job_snapshot=deepcopy(report.job_snapshot),
                                     materials_snapshot=deepcopy(report.materials_snapshot),
                                     summary="合成新版报告", overall_score=60)
                session.add(report)
                await session.flush()
                payload["reportId"] = str(report.id)
            else:
                report.summary = "本次重新分享的报告"
            await session.commit()

        refused = await student.post("/api/v1/applications",
                                     json={**payload, "shareConsent": False})
        assert refused.status_code == 422
        created = await student.post("/api/v1/applications", json=payload)
        assert created.status_code == 201, created.text
        current = created.json()["data"]
        assert current["id"] != old_id
        assert current["status"] == "submitted"
        assert current["reportId"] == payload["reportId"]
        assert current["replyText"] is None
        assert [e["type"] for e in current["events"]] == ["submitted"]
        assert (await student.post("/api/v1/applications", json=payload)).json()[
            "data"]["id"] == current["id"]
        assert (await hr.get(f"/api/v1/notifications/{old_notice}/target")).status_code == 404
        notices = (await hr.get("/api/v1/notifications")).json()["data"]["items"]
        assert sum(n["accessible"] for n in notices) == 1
        assert (await hr.get(f"/api/v1/jobs/{job['id']}/applications")).json()[
            "data"]["items"][0]["id"] == current["id"]
        for path in (f"/api/v1/applications/{old_id}",):
            assert (await hr.get(path)).status_code == 404
        for endpoint in ("view", "resume-download"):
            assert (await hr.post(f"/api/v1/applications/{old_id}/{endpoint}")).status_code == 404
        assert (await hr.post(
            f"/api/v1/applications/{old_id}/reply",
            json={"kind": "continue", "text": "旧链接不得恢复"},
        )).status_code == 404
        opened = (await hr.post(f"/api/v1/applications/{current['id']}/view")).json()["data"]
        assert opened["report"]["summary"] != snapshot["summary"]
        async with factory() as session:
            old = await session.get(Application, UUID(old_id))
            assert old.status == "withdrawn"
            assert old.report_snapshot == snapshot
            assert old.version == old_version and old.consent_at == old_consent
            assert old.reply_text == "请补充合成运行记录"
        # Repeating the old withdraw does not revoke the newly created application.
        await student.post(f"/api/v1/applications/{old_id}/withdraw")
        mine = (await student.get("/api/v1/applications/mine")).json()["data"]["items"]
        assert {i["id"]: i["status"] for i in mine} == {
            old_id: "withdrawn", current["id"]: "viewed"
        }
        # A different report cannot silently replace this active consent.
        if new_report:
            assert (await student.post("/api/v1/applications", json={
                "reportId": str(rid), "shareConsent": True
            })).status_code == 409
    finally:
        await close(hr, student, other)


async def test_reconsent_does_not_bypass_closed_job_or_daily_limit(
    matching_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, _, _, factory = await setup(
        matching_db, tmp_path, monkeypatch
    )
    try:
        payload = {"reportId": str(rid), "shareConsent": True}
        old_id = (await student.post("/api/v1/applications", json=payload)).json()["data"]["id"]
        await student.post(f"/api/v1/applications/{old_id}/withdraw")
        await hr.patch(f"/api/v1/jobs/{job['id']}", json={"status": "closed"})
        assert (await student.post("/api/v1/applications", json=payload)).status_code == 409
        await hr.patch(f"/api/v1/jobs/{job['id']}", json={"status": "published"})
        async with factory() as session:
            old = await session.get(Application, UUID(old_id))
            for _ in range(19):
                session.add(Application(job_id=old.job_id, student_id=old.student_id,
                    report_id=old.report_id, report_snapshot=deepcopy(old.report_snapshot),
                    consent_at=old.consent_at, consent_version=old.consent_version,
                    status="withdrawn"))
            await session.commit()
        assert (await student.post("/api/v1/applications", json=payload)).status_code == 429
    finally:
        await close(hr, student, other)


async def test_postgres_concurrent_reconsent_creates_one_active_application(
    matching_db, tmp_path, monkeypatch
):
    _, factory = matching_db
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    hr, student, other, job, rid, _, _, factory = await setup(
        matching_db, tmp_path, monkeypatch
    )
    try:
        payload = {"reportId": str(rid), "shareConsent": True}
        old_id = (await student.post("/api/v1/applications", json=payload)).json()["data"]["id"]
        await student.post(f"/api/v1/applications/{old_id}/withdraw")
        responses = await asyncio.gather(*(
            student.post("/api/v1/applications", json=payload) for _ in range(4)
        ))
        assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
        assert len({r.json()["data"]["id"] for r in responses}) == 1
        async with factory() as session:
            rows = list(await session.scalars(select(Application).where(
                Application.job_id == UUID(job["id"]))))
            assert len(rows) == 2
            assert sum(r.status != "withdrawn" for r in rows) == 1
    finally:
        await close(hr, student, other)
