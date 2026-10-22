"""Expose only saved process reasons through the already-authorized report read."""

from copy import deepcopy
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.analysis import AnalysisTask, MatchReport
from app.models.recruitment import Application
from app.tests.test_applications_api import close, setup
from app.tests.test_jobs_api import job_payload, organization, register

pytest_plugins = ["app.tests.test_jobs_api"]
PROCESS_KEYS = ("planningSkippedReason", "skippedReason", "fallbackReason", "failureStage")


async def test_saved_process_reasons_follow_report_ownership(jobs_db):
    app, factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "trace-enterprise@example.com")
        org = await organization(client)
        job = (await client.post("/api/v1/jobs", json=job_payload(org))).json()["data"]
        owner = await register(client, "trace-owner@example.com", "student")
        async with factory() as session:
            task = AnalysisTask(created_by=UUID(owner["id"]), task_type="job_match")
            session.add(task)
            await session.flush()
            report = MatchReport(
                analysis_task_id=task.id,
                job_id=UUID(job["id"]),
                candidate_ref=owner["id"],
                summary="Synthetic process display",
                analysis_metadata={
                    "planningSkippedReason": "report_budget_reserved",
                    "fallbackReason": 123,
                    "private_detail": "must-not-be-exported",
                },
            )
            session.add(report)
            await session.commit()
            report_id = report.id
        response = await client.get(f"/api/v1/match-reports/{report_id}")
        assert response.status_code == 200
        process = response.json()["data"]["aiProcess"]
        assert process == {
            "planningSkippedReason": "report_budget_reserved",
            "skippedReason": None,
            "fallbackReason": None,
            "failureStage": None,
        }
        assert "must-not-be-exported" not in response.text
        await register(client, "trace-other@example.com", "student")
        assert (await client.get(f"/api/v1/match-reports/{report_id}")).status_code == 404


@pytest.mark.parametrize("metadata, expected", [
    ({}, dict.fromkeys(PROCESS_KEYS)),
    ({
        "planningSkippedReason": ["report_budget_reserved"],
        "skippedReason": False,
        "fallbackReason": {"detail": "do-not-export"},
        "failureStage": 42,
    }, dict.fromkeys(PROCESS_KEYS)),
    ({"skippedReason": "consent_not_granted"}, {
        **dict.fromkeys(PROCESS_KEYS), "skippedReason": "consent_not_granted",
    }),
    ({"fallbackUsed": True, "fallbackReason": "timeout", "failureStage": "request"}, {
        **dict.fromkeys(PROCESS_KEYS), "fallbackReason": "timeout", "failureStage": "request",
    }),
])
async def test_historical_or_typed_saved_reasons_are_projected_without_inference(
    jobs_db, metadata, expected,
):
    app, factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner:
        await register(owner, "process-org@example.com")
        org = await organization(owner)
        job = (await owner.post("/api/v1/jobs", json=job_payload(org))).json()["data"]
        user = await register(owner, "process-student@example.com", "student")
        async with factory() as session:
            task = AnalysisTask(created_by=UUID(user["id"]), task_type="job_match")
            session.add(task)
            await session.flush()
            report = MatchReport(
                analysis_task_id=task.id, job_id=UUID(job["id"]),
                candidate_ref=user["id"], summary="Synthetic saved report",
                analysis_metadata=metadata,
            )
            session.add(report)
            await session.commit()
            report_id = report.id
        response = await owner.get(f"/api/v1/match-reports/{report_id}")
        assert response.status_code == 200, response.text
        assert response.json()["data"]["aiProcess"] == expected
        assert response.json()["data"]["aiFallbackUsed"] == metadata.get("fallbackUsed", False)
        assert "do-not-export" not in response.text
        async with factory() as session:
            stored = await session.get(MatchReport, report_id)
            assert stored.analysis_metadata == metadata


@pytest.mark.parametrize("legacy_without_process", [True, False])
async def test_enterprise_uses_frozen_process_without_retrofilling_or_live_report_lookup(
    jobs_db, tmp_path, monkeypatch, legacy_without_process,
):
    hr, student, other, _job, report_id, _resume_id, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch,
    )
    try:
        async with factory() as session:
            report = await session.get(MatchReport, report_id)
            report.analysis_metadata = {"planningSkippedReason": "report_budget_reserved"}
            await session.commit()
        submitted = await student.post("/api/v1/applications", json={
            "reportId": str(report_id), "shareConsent": True,
        })
        assert submitted.status_code == 201, submitted.text
        application_id = UUID(submitted.json()["data"]["id"])
        async with factory() as session:
            application = await session.get(Application, application_id)
            snapshot = deepcopy(application.report_snapshot)
            assert snapshot["aiProcess"]["planningSkippedReason"] == "report_budget_reserved"
            if legacy_without_process:
                # Simulate an already persisted pre-field snapshot, never retrofit it.
                snapshot.pop("aiProcess")
                application.report_snapshot = snapshot
            before = deepcopy(snapshot)
            report = await session.get(MatchReport, report_id)
            report.analysis_metadata = {"skippedReason": "consent_not_granted"}
            await session.commit()
        latest = await student.get(f"/api/v1/match-reports/{report_id}")
        assert latest.json()["data"]["aiProcess"]["skippedReason"] == "consent_not_granted"
        opened = await hr.post(f"/api/v1/applications/{application_id}/view")
        assert opened.status_code == 200, opened.text
        fixed = opened.json()["data"]["report"]
        assert fixed == before
        if legacy_without_process:
            assert "aiProcess" not in fixed
        else:
            assert fixed["aiProcess"]["planningSkippedReason"] == "report_budget_reserved"
            assert fixed["aiProcess"]["skippedReason"] is None
        assert (await other.post(f"/api/v1/applications/{application_id}/view")).status_code == 404
        async with factory() as session:
            application = await session.get(Application, application_id)
            assert application.report_snapshot == before
    finally:
        await close(hr, student, other)
