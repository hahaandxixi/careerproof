"""Real provider observer/attempt integration, synthetic HTTP and isolated tables."""

import asyncio
import json
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import select

from app.models.ai_budget import AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask
from app.services.ai_budget import BudgetAdmissionError, BudgetPolicy, SharedBudgetService
from app.services.ai_request_attempts import AttemptContext, AttemptService, DurableRequestObserver
from app.tests.test_ai_shared_budget_service import NOW
from app.tests.test_ai_shared_budget_service import budget_data as budget_data
from app.tests.test_durable_matching import durable_db as durable_db
from app.tests.test_durable_matching import synthetic_provider


async def service_for(factory, owner, task_id, provider, budget, *, phase=None):
    async with factory() as session:
        task = await session.get(AnalysisTask, task_id)
        context = AttemptContext(
            task_id, owner, task.run_token, "analysis", provider.name, provider.model
        )
    return AttemptService(factory, context, budget=budget, phase_hook=phase)


def request_for(provider, maximum=1000):
    return {
        "model": provider.model,
        "messages": [{"role": "user", "content": "synthetic only"}],
        "max_tokens": maximum,
    }


def response(request):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        },
        request=request,
    )


async def test_wire_grant_receipt_settlement_and_six_books_once(budget_data):  # noqa: F811
    factory, _runtime, owner, task, _other = budget_data
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return response(request)

    provider = synthetic_provider(handler)
    budget = SharedBudgetService(clock=lambda: NOW, policy=BudgetPolicy(1, 10000, 300, 10000, 300))
    service = await service_for(factory, owner, task, provider, budget)
    provider.durable_observer = DurableRequestObserver(service)
    await provider._completion(request_for(provider))
    assert len(calls) == 1 and calls[0]["max_tokens"] == 300
    async with factory() as session:
        attempt = await session.scalar(select(AiRequestAttempt))
        hold = await session.scalar(select(AiBudgetReservation))
        assert attempt.max_output_tokens == hold.output_bound == 300
        assert attempt.state == "received_unbooked" and hold.state == "settled"
        assert (hold.actual_input_tokens, hold.actual_output_tokens) == (12, 7)
        attempt_id = attempt.id
    written = await asyncio.gather(*(service.book_one(attempt_id) for _ in range(6)))
    assert sum(written) == 1
    assert await service.reconcile() == 0
    async with factory() as session:
        assert len(list(await session.scalars(select(AiUsageLog)))) == 1
        usage = await budget.capacity(session, owner, day=date(2026, 10, 7))
        assert (usage.inputs, usage.outputs) == (12, 7)
    assert len(calls) == 1


async def test_unknown_503_retry_cannot_spend_held_output_twice(budget_data):  # noqa: F811
    factory, _runtime, owner, task, _other = budget_data
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(503, json={"error": "synthetic unavailable"}, request=request)

    provider = synthetic_provider(handler)
    provider._max_attempts = 2
    budget = SharedBudgetService(clock=lambda: NOW, policy=BudgetPolicy(1, 10000, 300, 10000, 300))
    service = await service_for(factory, owner, task, provider, budget)
    provider.durable_observer = DurableRequestObserver(service)
    with pytest.raises(BudgetAdmissionError, match="output_token_limit"):
        await provider._completion(request_for(provider))
    assert len(calls) == 1
    async with factory() as session:
        attempts = list(await session.scalars(select(AiRequestAttempt)))
        holds = list(await session.scalars(select(AiBudgetReservation)))
        assert len(attempts) == len(holds) == 1
        assert attempts[0].state == "usage_unknown"
        assert attempts[0].usage_input_tokens is None
        assert holds[0].state == "held" and holds[0].output_bound == 300
        assert list(await session.scalars(select(AiUsageLog))) == []


async def test_credible_error_receipt_releases_only_unused_upper_bound_before_retry(
    budget_data,  # noqa: F811 - imported fixture
):
    factory, _runtime, owner, task, _other = budget_data
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(
                503,
                json={
                    "error": "synthetic error with credible usage",
                    "usage": {"prompt_tokens": 12, "completion_tokens": 7},
                },
                request=request,
            )
        return response(request)

    provider = synthetic_provider(handler)
    provider._max_attempts = 2
    budget = SharedBudgetService(clock=lambda: NOW, policy=BudgetPolicy(1, 10000, 300, 10000, 300))
    service = await service_for(factory, owner, task, provider, budget)
    provider.durable_observer = DurableRequestObserver(service)
    await provider._completion(request_for(provider))
    assert [call["max_tokens"] for call in calls] == [300, 293]
    assert await service.reconcile() == 2
    assert await service.reconcile() == 0
    async with factory() as session:
        usage = await budget.capacity(session, owner, day=date(2026, 10, 7))
        assert (usage.inputs, usage.outputs, usage.task_ids) == (24, 14, frozenset([task]))
        attempts = list(
            await session.scalars(
                select(AiRequestAttempt).order_by(
                    AiRequestAttempt.physical_sequence,
                )
            )
        )
        assert [item.state for item in attempts] == ["booked", "booked"]
    assert len(calls) == 2


@pytest.mark.parametrize("new_day_full", [False, True])
async def test_real_observer_midnight_admits_or_closes_zero_http(budget_data, new_day_full):  # noqa: F811
    factory, _runtime, owner, task, other = budget_data
    clock = [NOW]
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return response(request)

    provider = synthetic_provider(handler)
    budget = SharedBudgetService(
        clock=lambda: clock[0], policy=BudgetPolicy(1, 10000, 300, 10000, 300)
    )

    async def midnight(name, _attempt_id):
        if name == "prepared":
            clock[0] = datetime(2026, 10, 7, 16, 0, 1, tzinfo=UTC)
            if new_day_full:
                competitor = await service_for(factory, owner, other, provider, budget)
                await competitor.prepare(estimated_input_tokens=100, max_output_tokens=300)

    service = await service_for(factory, owner, task, provider, budget, phase=midnight)
    provider.durable_observer = DurableRequestObserver(service)
    if new_day_full:
        with pytest.raises(BudgetAdmissionError, match="daily_report_limit"):
            await provider._completion(request_for(provider))
        assert calls == []
    else:
        await provider._completion(request_for(provider))
        assert len(calls) == 1 and calls[0]["max_tokens"] == 300
    async with factory() as session:
        attempt = await session.scalar(
            select(AiRequestAttempt).where(
                AiRequestAttempt.analysis_task_id == task,
            )
        )
        hold = await session.scalar(
            select(AiBudgetReservation).where(
                AiBudgetReservation.attempt_id == attempt.id,
            )
        )
        assert attempt.state == ("not_sent" if new_day_full else "received_unbooked")
        assert hold.state == ("released" if new_day_full else "settled")
        if new_day_full:
            assert attempt.ended_at is not None and attempt.send_intent_at is None
        else:
            assert attempt.sending_day == hold.reservation_day == date(2026, 10, 8)
        old = await budget.capacity(session, owner, day=date(2026, 10, 7))
        assert (old.inputs, old.outputs, len(old.task_ids)) == (0, 0, 0)
