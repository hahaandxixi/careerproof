"""Independent OPS-01C boundary probes using synthetic HTTP and owned schemas."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.models.identity import User
from app.models.portfolio import ProjectVersion, ResumeVersion
from app.services import analysis as analysis_service
from app.services.ai_request_attempts import AttemptService
from app.services.task_lifecycle import recover_interrupted_tasks
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


@asynccontextmanager
async def matching_case(app, monkeypatch, provider, label):
    configure_synthetic(monkeypatch, provider)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
    ):
        await register(owner, f"{label}-owner@example.com")
        job = await create_job(owner)
        user = await register(student, f"{label}-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        yield SimpleNamespace(student=student, job=job, resume=resume, version=version,
                              owner_id=UUID(user["id"]))


async def submit_case(case, **extra):
    accepted = await case.student.post("/api/v1/matches", json={
        "jobId": case.job["id"], "resumeVersionId": case.resume["versionId"],
        "projectVersionIds": [case.version["versionId"]], "externalAiConsent": True,
        **extra,
    })
    assert accepted.status_code == 202, accepted.text
    return UUID(accepted.json()["data"]["taskId"])


def valid_response(request, *, inputs=120, outputs=20):
    source = json.loads(json.loads(request.content)["messages"][1]["content"])
    requirement_id = source["requirements"][0]["requirement_id"]
    return httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(
            analysis_answer(requirement_id, citation_ids=["R1-E1"]), ensure_ascii=False,
        )}}],
        "usage": {"prompt_tokens": inputs, "completion_tokens": outputs},
    })


async def assert_one_fee_no_report(factory, task_id):
    async with factory() as session:
        assert await session.scalar(select(MatchReport.id).where(
            MatchReport.analysis_task_id == task_id,
        )) is None
        attempts = list(await session.scalars(select(AiRequestAttempt).where(
            AiRequestAttempt.analysis_task_id == task_id,
        )))
        ledger = list(await session.scalars(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id == task_id,
        )))
        assert len(attempts) == len(ledger) == 1
        assert attempts[0].state == "booked"
        assert ledger[0].attempt_id == attempts[0].id
        assert (ledger[0].input_tokens, ledger[0].output_tokens) == (120, 20)
        return attempts[0]


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


@pytest.mark.parametrize("booking_failure", [False, True])
async def test_cancel_after_receipt_preserves_cancel_and_recovers_only_fees(
    durable_db, monkeypatch, booking_failure,  # noqa: F811 - imported pytest fixture
):
    app, factory, _runtime = durable_db
    calls = []
    original_phase, original_book = AttemptService._phase, AttemptService.book_one

    async def cancel_after_receipt(self, name, attempt_id):
        await original_phase(self, name, attempt_id)
        if name == "receipt_committed":
            raise asyncio.CancelledError("synthetic cancellation after durable receipt")

    async def failed_book(self, attempt_id):
        raise RuntimeError("synthetic ledger failure during cancellation")

    def handler(request):
        calls.append(request)
        return valid_response(request)

    provider = synthetic_provider(handler)
    monkeypatch.setattr(AttemptService, "_phase", cancel_after_receipt)
    if booking_failure:
        monkeypatch.setattr(AttemptService, "book_one", failed_book)
    label = f"review-cancel-{booking_failure}"
    from app.api.v1 import analysis as analysis_api

    cancellations = []
    original_execute = analysis_api.execute_match_task

    async def observe_cancellation(*args, **kwargs):
        try:
            return await original_execute(*args, **kwargs)
        except asyncio.CancelledError as exc:
            cancellations.append(str(exc))
            raise

    monkeypatch.setattr(analysis_api, "execute_match_task", observe_cancellation)
    async with matching_case(app, monkeypatch, provider, label) as case:
        await submit_case(case)
    assert cancellations == ["synthetic cancellation after durable receipt"]
    assert len(calls) == 1
    context = provider.durable_observer.service.context
    async with factory() as session:
        attempt = await session.scalar(select(AiRequestAttempt).where(
            AiRequestAttempt.analysis_task_id == context.task_id,
        ))
        assert attempt.state == ("received_unbooked" if booking_failure else "booked")
        assert await session.scalar(select(MatchReport.id).where(
            MatchReport.analysis_task_id == context.task_id,
        )) is None
        task = await session.get(AnalysisTask, context.task_id)
        task.heartbeat_at = datetime.now(UTC) - timedelta(seconds=settings.task_lease_seconds + 2)
        await session.commit()
    assert await recover_interrupted_tasks(factory) == 1
    monkeypatch.setattr(AttemptService, "book_one", original_book)
    assert await provider.durable_observer.service.reconcile() == int(booking_failure)
    assert await provider.durable_observer.service.reconcile() == 0
    await assert_one_fee_no_report(factory, context.task_id)
    assert len(calls) == 1


async def test_expired_claim_during_http_books_old_run_without_publishing(
    durable_db, monkeypatch,  # noqa: F811 - imported pytest fixture
):
    app, factory, _runtime = durable_db
    calls = []

    async def no_heartbeat(*_args):
        return None

    async def handler(request):
        calls.append(request)
        context = provider.durable_observer.service.context
        async with factory() as session:
            task = await session.get(AnalysisTask, context.task_id)
            task.heartbeat_at = datetime.now(UTC) - timedelta(
                seconds=settings.task_lease_seconds + 2,
            )
            await session.commit()
        assert await recover_interrupted_tasks(factory) == 1
        return valid_response(request)

    provider = synthetic_provider(handler)
    monkeypatch.setattr(analysis_service, "heartbeat_task", no_heartbeat)
    async with matching_case(app, monkeypatch, provider, "review-expired") as case:
        task_id = await submit_case(case)
    attempt = await assert_one_fee_no_report(factory, task_id)
    async with factory() as session:
        task = await session.get(AnalysisTask, task_id)
        assert task.status == TaskStatus.FAILED and task.run_token is None
        assert attempt.run_token == provider.durable_observer.service.context.run_token
    assert len(calls) == 1
    assert await provider.durable_observer.service.reconcile() == 0


async def test_report_transaction_before_commit_failure_keeps_prior_ledger_commit(
    durable_db, monkeypatch,  # noqa: F811 - imported pytest fixture
):
    app, factory, _runtime = durable_db
    calls, failed = [], []

    def handler(request):
        calls.append(request)
        return valid_response(request)

    def fail_report_commit(session):
        reports = [row for row in session.identity_map.values() if isinstance(row, MatchReport)]
        if reports and not failed:
            assert reports[0].id is not None  # Real flush has already happened.
            failed.append(reports[0].analysis_task_id)
            raise RuntimeError("synthetic failure of flushed report transaction before_commit")

    provider = synthetic_provider(handler)
    async with matching_case(app, monkeypatch, provider, "review-commit-failure") as case:
        event.listen(Session, "before_commit", fail_report_commit)
        try:
            task_id = await submit_case(case)
        finally:
            event.remove(Session, "before_commit", fail_report_commit)
    assert failed == [task_id]
    await assert_one_fee_no_report(factory, task_id)
    async with factory() as session:
        task = await session.get(AnalysisTask, task_id)
        assert task.status == TaskStatus.FAILED
    assert len(calls) == 1


@pytest.mark.parametrize("change", [
    "resume_status", "project_status", "selected_resume", "selected_projects", "history_id",
])
async def test_pre_send_readiness_and_fixed_selection_mutations_send_nothing(
    durable_db, monkeypatch, change,  # noqa: F811 - imported pytest fixture
):
    app, factory, _runtime = durable_db
    calls = []

    def handler(request):
        calls.append(request)
        return valid_response(request)

    provider = synthetic_provider(handler)
    original_progress = analysis_service.update_task_progress
    async with matching_case(app, monkeypatch, provider, f"review-binding-{change}") as case:
        async def mutate_ready_snapshot(session, task_id, token, *, progress, step):
            result = await original_progress(session, task_id, token, progress=progress, step=step)
            if progress == 55:
                async with factory() as mutation:
                    if change == "resume_status":
                        row = await mutation.get(ResumeVersion, UUID(case.resume["versionId"]))
                        row.parse_status = "failed"
                    elif change == "project_status":
                        row = await mutation.get(ProjectVersion, UUID(case.version["versionId"]))
                        row.analysis_status = "failed"
                    else:
                        row = await mutation.get(AnalysisTask, task_id)
                        field, value = {
                            "selected_resume": ("resumeVersionId", str(uuid4())),
                            "selected_projects": ("projectVersionIds", []),
                            "history_id": ("previousReportId", str(uuid4())),
                        }[change]
                        row.input_snapshot = {**row.input_snapshot, field: value}
                    await mutation.commit()
            return result

        monkeypatch.setattr(analysis_service, "update_task_progress", mutate_ready_snapshot)
        task_id = await submit_case(case)
    assert calls == []
    async with factory() as session:
        task = await session.get(AnalysisTask, task_id)
        assert task.status == TaskStatus.FAILED
        assert await session.scalar(select(MatchReport.id).where(
            MatchReport.analysis_task_id == task_id,
        )) is None
        assert await session.scalar(select(AiUsageLog.id).where(
            AiUsageLog.analysis_task_id == task_id,
        )) is None
        attempts = list(await session.scalars(select(AiRequestAttempt).where(
            AiRequestAttempt.analysis_task_id == task_id,
        )))
        assert len(attempts) == 1
        assert attempts[0].state == "not_sent" and attempts[0].ended_at is not None


async def test_each_planning_round_has_its_own_durable_step(
    durable_db, monkeypatch,  # noqa: F811 - imported pytest fixture
):
    app, factory, _runtime = durable_db
    calls, planning = [], []

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        if "tools" not in body:
            return valid_response(request)
        planning.append(request)
        assert provider.durable_observer.service.context.step == f"planning_{len(planning)}"
        source = json.loads(body["messages"][1]["content"])
        requirement_id = source["requirements"][0]["requirement_id"]
        message = {"content": "无需补检索"} if len(planning) == 2 else {
            "tool_calls": [{"function": {
                "name": "get_previous_report_context",
                "arguments": json.dumps({"requirement_id": requirement_id}),
            }}],
        }
        return httpx.Response(200, json={
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 40 + 10 * len(planning), "completion_tokens": 10},
        })

    provider = synthetic_provider(handler)
    monkeypatch.setattr(settings, "ai_max_retrieval_calls", 2)
    # Force two legal planner opportunities; the actual planner, history
    # authorization, HTTP hooks and durable writes still execute unchanged.
    monkeypatch.setattr("app.agents.evidence_workflow.eligible_retrieval_contexts",
                        lambda _result, contexts: contexts)
    async with matching_case(app, monkeypatch, provider, "review-planning-rounds") as case:
        previous = await match_report(case.student, case.job, case.resume, case.version)
        task_id = await submit_case(case, usePreviousReport=True)
    assert len(planning) == 2 and len(calls) == 3
    async with factory() as session:
        attempts = list(await session.scalars(select(AiRequestAttempt).where(
            AiRequestAttempt.analysis_task_id == task_id,
        ).order_by(AiRequestAttempt.physical_sequence)))
        assert [row.step for row in attempts] == ["planning_1", "planning_2", "analysis"]
        assert [row.physical_sequence for row in attempts] == [1, 2, 3]
        assert all(row.state == "booked" for row in attempts)
        report = await session.scalar(select(MatchReport).where(
            MatchReport.analysis_task_id == task_id,
        ))
        assert report.analysis_metadata["usageKnown"] is True
        assert report.analysis_metadata["usageBooked"] is True
        task = await session.get(AnalysisTask, task_id)
        assert task.input_snapshot["previousReportId"] == previous["id"]
