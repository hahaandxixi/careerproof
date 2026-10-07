"""Independent OPS-01C boundary probes using synthetic HTTP and owned schemas."""

import json
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.models.identity import User
from app.models.portfolio import ProjectVersion, ResumeVersion
from app.tests.test_durable_matching import (
    analysis_answer,
    classify_request,
    retry_handler,
    synthetic_provider,
)
from app.tests.test_durable_matching import (
    durable_db as durable_db,
)
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import create_job, match_report, upload_materials


def configure_synthetic(monkeypatch, provider):
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr(settings, "semantic_retrieval_enabled", False)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)


async def test_planning_unknown_and_error_receipts_are_accounted_without_fake_completion(
    durable_db, monkeypatch,  # noqa: F811 - imported pytest fixture
):
    app, factory, _runtime = durable_db
    calls, outcomes = [], []
    configure_synthetic(monkeypatch, synthetic_provider(retry_handler(calls, outcomes)))
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, "review-planning-owner@example.com")
        job = await create_job(owner)
        await register(student, "review-planning-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        previous = await match_report(student, job, resume, version)
        report = await match_report(
            student, job, resume, version,
            externalAiConsent=True, usePreviousReport=True,
        )

    # The authorized historical report forces a real planning request even
    # when the selected code evidence is already source-exact.
    assert [classify_request(call) for call in calls] == [
        "planning_1", "planning_1", "analysis", "analysis", "repair",
    ]
    async with factory() as session:
        task_id = UUID(report["taskId"])
        attempts = list(await session.scalars(
            select(AiRequestAttempt).where(AiRequestAttempt.analysis_task_id == task_id)
            .order_by(AiRequestAttempt.physical_sequence),
        ))
        assert [row.physical_sequence for row in attempts] == [1, 2, 3, 4, 5]
        assert [row.state for row in attempts] == [
            "usage_unknown", "booked", "booked", "booked", "booked",
        ]
        assert attempts[0].usage_input_tokens is None
        assert attempts[0].usage_output_tokens is None
        ledger = list(await session.scalars(
            select(AiUsageLog).where(AiUsageLog.analysis_task_id == task_id)
            .order_by(AiUsageLog.request_seq),
        ))
        assert [row.request_seq for row in ledger] == [2, 3, 4, 5]
        assert [(row.input_tokens, row.output_tokens) for row in ledger] == [
            (100, 10), (30, 5), (200, 80), (150, 60),
        ]
        assert all(row.attempt_id is not None for row in ledger)
        saved = await session.scalar(select(MatchReport).where(
            MatchReport.analysis_task_id == task_id,
        ))
        metadata = saved.analysis_metadata
        summary = metadata["attemptSummary"]
        assert summary["unknownAttemptCount"] == 1
        assert summary["trustedReceiptCount"] == 4
        assert summary["usageKnown"] is False
        assert summary["usageBooked"] is False
        assert metadata["usageKnown"] is False
        assert metadata["usageBooked"] is False
        assert metadata["usage"]["input_tokens"] == 480
        assert metadata["usage"]["output_tokens"] == 155
        assert await session.get(MatchReport, UUID(previous["id"])) is not None


@pytest.mark.parametrize("revocation", ["owner", "resume_status", "project_status"])
async def test_authorization_lost_while_http_is_in_flight_keeps_fees_not_report(
    durable_db, monkeypatch, revocation,  # noqa: F811 - imported pytest fixture
):
    app, factory, _runtime = durable_db
    calls, ids = [], {}

    async def handler(request):
        calls.append(request)
        source = json.loads(json.loads(request.content)["messages"][1]["content"])
        requirement_id = source["requirements"][0]["requirement_id"]
        async with factory() as session:
            if revocation == "owner":
                owner_row = await session.get(User, ids["owner"])
                owner_row.is_active = False
            elif revocation == "resume_status":
                resume_row = await session.get(ResumeVersion, ids["resume"])
                resume_row.parse_status = "failed"
            else:
                project_row = await session.get(ProjectVersion, ids["project"])
                project_row.analysis_status = "failed"
            await session.commit()
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps(
                analysis_answer(requirement_id, citation_ids=["R1-E1"]),
                ensure_ascii=False,
            )}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 20},
        })

    configure_synthetic(monkeypatch, synthetic_provider(handler))
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, f"review-late-{revocation}-owner@example.com")
        job = await create_job(owner)
        student_user = await register(
            student, f"review-late-{revocation}-student@example.com", "student",
        )
        resume, _project, version = await upload_materials(student)
        ids.update(owner=UUID(student_user["id"]), resume=UUID(resume["versionId"]),
                   project=UUID(version["versionId"]))
        accepted = await student.post("/api/v1/matches", json={
            "jobId": job["id"], "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]], "externalAiConsent": True,
        })
        assert accepted.status_code == 202, accepted.text
        task_id = UUID(accepted.json()["data"]["taskId"])

    assert len(calls) == 1
    async with factory() as session:
        task = await session.get(AnalysisTask, task_id)
        assert task.status == TaskStatus.FAILED
        assert await session.scalar(select(MatchReport.id).where(
            MatchReport.analysis_task_id == task_id,
        )) is None
        attempts = list(await session.scalars(select(AiRequestAttempt).where(
            AiRequestAttempt.analysis_task_id == task_id,
        )))
        assert len(attempts) == 1
        assert attempts[0].state == "booked"
        ledger = list(await session.scalars(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id == task_id,
        )))
        assert len(ledger) == 1
        assert ledger[0].attempt_id == attempts[0].id
        assert (ledger[0].input_tokens, ledger[0].output_tokens) == (120, 20)
