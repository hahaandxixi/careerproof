"""Budgeted production entry points, with actual synthetic upload/snapshot flows."""

import json
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.config import settings
from app.models.ai_budget import AiBudgetCutover, AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.services.ai_budget import GATE_ID
from app.tests.test_application_verification import case as case
from app.tests.test_application_verification import completion, inject_provider, model_answer
from app.tests.test_durable_matching import durable_db as durable_db
from app.tests.test_durable_matching import synthetic_provider
from app.tests.test_durable_matching_review import matching_case, submit_case, valid_response
from app.tests.test_real_matching import matching_db as matching_db


async def close_gate(factory):
    async with factory() as session:
        gate = await session.get(AiBudgetCutover, GATE_ID)
        gate.enabled = False
        await session.commit()


async def legacy_output(factory, owner, outputs):
    async with factory() as session:
        task = AnalysisTask(
            id=uuid4(),
            created_by=owner,
            task_type="job_match",
            status=TaskStatus.COMPLETED,
            input_snapshot={"externalAiConsent": False},
        )
        session.add(task)
        await session.flush()
        session.add(
            AiUsageLog(
                analysis_task_id=task.id,
                model="synthetic-legacy",
                input_tokens=10,
                output_tokens=outputs,
                cache_hit_tokens=0,
                unit_price_snapshot={},
                latency_ms=1,
            )
        )
        await session.commit()


async def test_matching_disabled_gate_cannot_send_or_fabricate_usage(durable_db, monkeypatch):  # noqa: F811
    app, factory, _runtime = durable_db
    calls = []

    def handler(request):
        calls.append(request)
        return valid_response(request)

    provider = synthetic_provider(handler)
    async with matching_case(app, monkeypatch, provider, "budget-gate-closed") as candidate:
        await close_gate(factory)
        task_id = await submit_case(candidate)
    assert calls == []
    async with factory() as session:
        assert list(await session.scalars(select(AiRequestAttempt))) == []
        assert list(await session.scalars(select(AiBudgetReservation))) == []
        assert list(await session.scalars(select(AiUsageLog))) == []
        report = await session.scalar(
            select(MatchReport).where(MatchReport.analysis_task_id == task_id)
        )
        assert report.analysis_metadata["usageKnown"] is False
        assert report.analysis_metadata["usage"] is None


async def test_matching_small_daily_remainder_is_granted_on_actual_wire(durable_db, monkeypatch):  # noqa: F811
    app, factory, _runtime = durable_db
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return valid_response(request)

    provider = synthetic_provider(handler)
    async with matching_case(app, monkeypatch, provider, "budget-wire-remainder") as candidate:
        monkeypatch.setattr(settings, "ai_daily_output_token_limit", 1000)
        await legacy_output(factory, candidate.owner_id, 800)
        task_id = await submit_case(candidate)
    assert len(calls) == 1 and calls[0]["max_tokens"] == 200
    async with factory() as session:
        attempt = await session.scalar(
            select(AiRequestAttempt).where(
                AiRequestAttempt.analysis_task_id == task_id,
            )
        )
        hold = await session.scalar(
            select(AiBudgetReservation).where(
                AiBudgetReservation.attempt_id == attempt.id,
            )
        )
        assert attempt.max_output_tokens == hold.output_bound == 200
        assert attempt.state == "booked" and hold.state == "settled"
        assert (hold.actual_input_tokens, hold.actual_output_tokens) == (120, 20)


async def test_verification_disabled_gate_is_zero_http_with_explicit_failure(case, monkeypatch):  # noqa: F811
    calls = []

    def handler(request):
        calls.append(request)
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    await close_gate(case.factory)
    started = await case.start()
    await case.execute(started)
    result = await case.result(started)
    assert calls == [] and result["analysis"] is None
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.FAILED
        assert "budget_cutover_not_enabled" in str(task.input_snapshot)
        assert list(await session.scalars(select(AiRequestAttempt))) == []
        assert list(await session.scalars(select(AiBudgetReservation))) == []


async def test_verification_legacy_consumption_grants_only_daily_remainder(case, monkeypatch):  # noqa: F811
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    monkeypatch.setattr(settings, "ai_daily_output_token_limit", 1000)
    started = await case.start()
    task_id = UUID(started["taskId"])
    async with case.factory() as session:
        owner = (await session.get(AnalysisTask, task_id)).created_by
    await legacy_output(case.factory, owner, 800)
    await case.execute(started)
    result = await case.result(started)
    assert result["status"] == "completed" and result["analysis"] is not None
    assert len(calls) == 1 and calls[0]["max_tokens"] == 200
    async with case.factory() as session:
        attempt = await session.scalar(
            select(AiRequestAttempt).where(
                AiRequestAttempt.analysis_task_id == task_id,
            )
        )
        hold = await session.scalar(
            select(AiBudgetReservation).where(
                AiBudgetReservation.attempt_id == attempt.id,
            )
        )
        assert attempt.max_output_tokens == hold.output_bound == 200
        assert attempt.state == "booked" and hold.state == "settled"
        assert (hold.actual_input_tokens, hold.actual_output_tokens) == (123, 45)
