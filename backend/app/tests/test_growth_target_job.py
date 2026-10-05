"""Explicit private target changes never replace an enterprise application."""

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask
from app.models.evidence_growth import EvidenceGrowthTask
from app.services.report_comparison import compare_views
from app.tests.test_evidence_growth import newer, plan
from app.tests.test_real_matching import (
    create_job,
    match_report,
    matching_db,  # noqa: F401
    register,
    upload_materials,
)
from app.tests.test_report_comparison import pair


@pytest.mark.parametrize("change", ["materials", "job", "both"])
async def test_explicit_target_change_real_reports_and_original_application(matching_db, change):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(hr, "target-job-hr@example.com")
        original_job = await create_job(hr)
        target_job = (
            await create_job(hr, skills=("SQL",)) if change != "materials" else original_job
        )
        await register(student, "target-job-student@example.com", "student")
        resume, project, version = await upload_materials(student)
        base = await match_report(student, original_job, resume, version)
        application = await student.post(
            "/api/v1/applications", json={"reportId": base["id"], "shareConsent": True}
        )
        assert application.status_code == 201, application.text
        application_url = f"/api/v1/applications/{application.json()['data']['id']}/view"
        original = deepcopy((await hr.post(application_url)).json()["data"]["report"])
        created = await student.post(
            f"/api/v1/match-reports/{base['id']}/growth-tasks", json=plan(base)
        )
        assert created.status_code == 201, created.text
        task = created.json()["data"]
        assert task["targetJobId"] == original_job["id"]
        url = f"/api/v1/growth-tasks/{task['id']}"
        selected = (
            await newer(student, project) if change != "job" else version["versionId"]
        )
        attached = await student.put(url + "/materials", json={
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [selected],
            "targetJobId": target_job["id"],
        })
        assert attached.status_code == 200, attached.text
        assert attached.json()["data"]["targetJobId"] == target_job["id"]
        assert (await student.get(url)).json()["data"]["targetJobId"] == target_job["id"]
        accepted = await student.post(url + "/analyze", json={"externalAiConsent": False})
        assert accepted.status_code == 202, accepted.text
        result = (await student.get(url)).json()["data"]
        assert result["status"] == "compared", result
        comparison = result["comparison"]
        assert comparison["baseJobId"] == original_job["id"]
        assert comparison["targetJobId"] == target_job["id"]
        assert ("job" in comparison["contextChanges"]) == (change != "materials")
        assert ("materials" in comparison["contextChanges"]) == (change != "job")
        if change != "materials":
            assert "requirements" in comparison["contextChanges"]
            assert {item["status"] for item in comparison["items"]} == {"added", "removed"}
            assert (
                await student.get(
                    f"/api/v1/match-reports/{base['id']}/comparison/{result['targetReportId']}",
                )
            ).status_code == 409
        repeated = await student.post(url + "/analyze", json={"externalAiConsent": False})
        assert repeated.json()["data"]["analysisTaskId"] == result["analysisTaskId"]
        assert (await student.put(url + "/materials", json={
            "resumeVersionId": resume["versionId"], "projectVersionIds": [selected],
            "targetJobId": original_job["id"],
        })).status_code == 409
        assert (await hr.post(application_url)).json()["data"]["report"] == original
        async with factory() as session:
            persisted = await session.get(EvidenceGrowthTask, UUID(task["id"]))
            analysis = await session.get(AnalysisTask, persisted.analysis_task_id)
            assert analysis.input_snapshot["jobId"] == target_job["id"]
            assert persisted.target_job_id == UUID(target_job["id"])
            if change != "materials":
                # A corrupted selection must not grant arbitrary cross-job comparison.
                persisted.target_job_id = UUID(original_job["id"])
                await session.commit()
        if change != "materials":
            assert (await student.get(url)).status_code == 409


async def test_invalid_or_unchanged_target_leaves_saved_selection_intact(matching_db):  # noqa: F811
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as other,
    ):
        await register(hr, "target-invalid-hr@example.com")
        job = await create_job(hr)
        draft = await create_job(hr, skills=("SQL",))
        unpublished = await hr.patch(f"/api/v1/jobs/{draft['id']}", json={"status": "draft"})
        assert unpublished.status_code == 200
        await register(student, "target-invalid-owner@example.com", "student")
        await register(other, "target-invalid-other@example.com", "student")
        resume, _, version = await upload_materials(student)
        base = await match_report(student, job, resume, version)
        task = (await student.post(
            f"/api/v1/match-reports/{base['id']}/growth-tasks", json=plan(base)
        )).json()["data"]
        url = f"/api/v1/growth-tasks/{task['id']}"
        material = {
            "resumeVersionId": resume["versionId"], "projectVersionIds": [version["versionId"]]
        }
        for target, expected in [(job["id"], 409), (draft["id"], 404), (str(uuid4()), 404)]:
            response = await student.put(
                url + "/materials", json={**material, "targetJobId": target}
            )
            assert response.status_code == expected, response.text
        assert (await student.put(url + "/materials", json=material)).status_code == 409
        denied = await other.put(
            url + "/materials", json={**material, "targetJobId": draft["id"]}
        )
        assert denied.status_code == 404
        async with factory() as session:
            saved = await session.scalar(
                select(EvidenceGrowthTask).where(EvidenceGrowthTask.id == UUID(task["id"]))
            )
            assert saved.materials == []
            assert saved.target_job_id is None
            assert saved.analysis_task_id is None
        assert (await hr.patch(
            f"/api/v1/jobs/{draft['id']}", json={"status": "published"}
        )).status_code == 200
        selected = await student.put(
            url + "/materials", json={**material, "targetJobId": draft["id"]}
        )
        assert selected.status_code == 200, selected.text
        assert (await hr.patch(
            f"/api/v1/jobs/{draft['id']}", json={"status": "draft"}
        )).status_code == 200
        refused = await student.post(url + "/analyze", json={"externalAiConsent": False})
        assert refused.status_code == 404, refused.text
        reread = (await student.get(url)).json()["data"]
        assert reread["targetJobId"] == draft["id"]
        assert reread["analysisTaskId"] is None


def test_explicit_job_permission_never_relaxes_candidate_boundary():
    base, target = pair()
    target.job_id = uuid4()
    target.candidate_id = "someone-else"
    with pytest.raises(AppError) as error:
        compare_views(base, target, {}, {}, allow_job_change=True)
    assert error.value.status_code == 409


async def test_growth_failure_cannot_bypass_reselection_via_generic_retry(
    matching_db, monkeypatch,  # noqa: F811
):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(hr, "growth-retry-hr@example.com")
        job = await create_job(hr)
        await register(student, "growth-retry-student@example.com", "student")
        resume, project, version = await upload_materials(student)
        base = await match_report(student, job, resume, version)
        created = (await student.post(
            f"/api/v1/match-reports/{base['id']}/growth-tasks", json=plan(base)
        )).json()["data"]
        url = f"/api/v1/growth-tasks/{created['id']}"
        updated = await newer(student, project)
        material = {"resumeVersionId": resume["versionId"], "projectVersionIds": [updated]}
        assert (await student.put(url + "/materials", json=material)).status_code == 200
        calls = []

        async def fail(*args, **kwargs):
            calls.append(True)
            raise RuntimeError("synthetic growth analysis failure")

        monkeypatch.setattr("app.services.analysis.run_isolated", fail)
        assert (await student.post(url + "/analyze", json={})).status_code == 202
        first = (await student.get(url)).json()["data"]
        assert first["status"] == "analysis_failed"
        retry_url = f"/api/v1/analysis-tasks/{first['analysisTaskId']}/retry"
        assert (await student.post(retry_url)).status_code == 409
        assert len(calls) == 1
        assert (await student.put(url + "/materials", json=material)).status_code == 200
        # The old failure must remain preserved even after its growth task reselects.
        assert (await student.post(retry_url)).status_code == 409
        assert (await student.post(url + "/analyze", json={})).status_code == 202
        second = (await student.get(url)).json()["data"]
        assert second["analysisTaskId"] != first["analysisTaskId"]
        async with factory() as session:
            failed = await session.get(AnalysisTask, UUID(first["analysisTaskId"]))
            assert failed.status.value == "failed"
            assert failed.error_message
        assert len(calls) == 2
