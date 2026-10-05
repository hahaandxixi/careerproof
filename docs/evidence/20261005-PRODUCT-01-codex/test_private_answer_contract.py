"""Independent API checks; run only after the ZCode writer has handed off.

Uses matching_db temporary SQLite or an explicitly selected random cp_test schema.
No browser, live closure database, external model, or private resume is used.
"""

from copy import deepcopy
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.analysis import MatchItem
from app.models.evidence_growth import EvidenceGrowthTask
from app.tests.conftest import disable_external_ai_for_tests  # noqa: F401
from app.tests.test_evidence_growth import plan
from app.tests.test_real_matching import (
    create_job,
    match_report,
    matching_db,  # noqa: F401
    register,
    upload_materials,
)


async def test_private_draft_frozen_citation_and_stale_save_preserve_original(matching_db):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as other,
    ):
        await register(hr, "draft-audit-hr@example.com")
        job = await create_job(hr)
        await register(student, "draft-audit-owner@example.com", "student")
        await register(other, "draft-audit-other@example.com", "student")
        resume, _, version = await upload_materials(student)
        report = await match_report(student, job, resume, version)
        item = report["items"][0]
        citation = next(e["citationId"] for e in item["evidenceList"] if e.get("citationId"))
        response = await student.post(
            f"/api/v1/match-reports/{report['id']}/growth-tasks", json=plan(report)
        )
        assert response.status_code == 201
        task = response.json()["data"]
        path = f"/api/v1/growth-tasks/{task['id']}/answer-draft"
        selected = {"reportId": report["id"], "requirementId": item["requirementId"],
                    "citationId": citation}
        # A task fixes its source at creation. Simulate later report drift only
        # in this disposable test schema, never in closure or production.
        async with factory() as session:
            row = await session.get(EvidenceGrowthTask, UUID(task["id"]))
            frozen = deepcopy(row.base_snapshot)
            match = await session.scalar(select(MatchItem).where(
                MatchItem.report_id == UUID(report["id"]),
                MatchItem.requirement_id == UUID(item["requirementId"]),
            ))
            match.evidence_snapshot = None
            match.evidence_id = None
            await session.commit()
        options = await student.get(path + "/references")
        assert options.status_code == 200
        assert any(all(ref[key] == value for key, value in selected.items())
                   for ref in options.json()["data"])
        initial = await student.put(path, json={
            "text": "本人待核对回答\n保留换行", "references": [selected], "expectedRevision": 0,
        })
        assert initial.status_code == 200
        first = initial.json()["data"]
        assert first["revision"] == 1
        saved = await student.put(path, json={
            "text": "本人第二版", "references": [selected], "expectedRevision": 1,
        })
        assert saved.status_code == 200
        assert saved.json()["data"]["revision"] == 2
        stale = await student.put(path, json={
            "text": "过时窗口不应覆盖", "references": [], "expectedRevision": 1,
        })
        assert stale.status_code == 409
        reread = await student.get(path)
        assert reread.status_code == 200
        assert reread.json()["data"]["text"] == "本人第二版"
        assert reread.json()["data"]["revision"] == 2
        for client, denied in ((other, 404), (hr, 403)):
            assert (await client.get(path)).status_code == denied
            assert (await client.get(path + "/references")).status_code == denied
            assert (await client.put(path, json={
                "text": "无权覆盖", "references": [], "expectedRevision": 2,
            })).status_code == denied
        async with factory() as session:
            row = await session.get(EvidenceGrowthTask, UUID(task["id"]))
            assert row.base_snapshot == frozen
            assert row.analysis_task_id is None
            assert row.status == "planned"

async def test_completed_target_with_drifted_fixed_job_cannot_be_used_as_answer_source(matching_db):
    """A completed status alone cannot bless a target rejected by the growth chain."""
    from uuid import uuid4

    from app.models.analysis import AnalysisTask
    from app.tests.test_evidence_growth import newer

    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(hr, "draft-target-audit-hr@example.com")
        job = await create_job(hr)
        await register(student, "draft-target-audit-owner@example.com", "student")
        resume, project, version = await upload_materials(student)
        base = await match_report(student, job, resume, version)
        created = await student.post(
            f"/api/v1/match-reports/{base['id']}/growth-tasks", json=plan(base)
        )
        assert created.status_code == 201, created.text
        task = created.json()["data"]
        path = f"/api/v1/growth-tasks/{task['id']}"
        updated_version = await newer(student, project)
        attached = await student.put(path + "/materials", json={
            "resumeVersionId": resume["versionId"], "projectVersionIds": [updated_version],
        })
        assert attached.status_code == 200, attached.text
        analyzed = await student.post(path + "/analyze", json={"externalAiConsent": False})
        assert analyzed.status_code == 202, analyzed.text
        completed = await student.get(path)
        assert completed.status_code == 200, completed.text
        current = completed.json()["data"]
        assert current["status"] == "compared"
        target_id = current["targetReportId"]
        target = (await student.get(f"/api/v1/match-reports/{target_id}")).json()["data"]
        item = next(i for i in target["items"] if i["requirementId"] == task["requirementId"])
        citation = next(e["citationId"] for e in item["evidenceList"] if e.get("citationId"))
        selected = {"reportId": target_id, "requirementId": task["requirementId"],
                    "citationId": citation}
        saved = await student.put(path + "/answer-draft", json={
            "text": "目标引用待核对", "references": [selected], "expectedRevision": 0,
        })
        assert saved.status_code == 200, saved.text
        # Change the fixed analysis association in a disposable test schema only.
        # The canonical growth reader must now reject the mismatched job.
        async with factory() as session:
            analysis = await session.get(AnalysisTask, UUID(current["analysisTaskId"]))
            drift = deepcopy(analysis.input_snapshot)
            drift["jobId"] = str(uuid4())
            analysis.input_snapshot = drift
            await session.commit()
        assert (await student.get(path)).status_code == 409
        options = await student.get(path + "/answer-draft/references")
        assert options.status_code in {200, 409}, options.text
        if options.status_code == 200:
            assert all(ref["reportId"] != target_id for ref in options.json()["data"])
        reread = await student.get(path + "/answer-draft")
        assert reread.status_code == 200, reread.text
        recorded = reread.json()["data"]
        assert recorded["text"] == "目标引用待核对" and recorded["revision"] == 1
        assert recorded["references"][0]["reportId"] == target_id
        assert recorded["references"][0]["available"] is False
        rejected = await student.put(path + "/answer-draft", json={
            "text": "不可覆盖为有效来源", "references": [selected], "expectedRevision": 1,
        })
        assert rejected.status_code in {409, 422}, rejected.text
