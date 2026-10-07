"""B-08 fault-injection tests: trustworthy usage survives lease loss, cancel and commit failure.

Synthetic provider transport only (httpx.MockTransport); never a real model call.
"""

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select, update

from app.models.analysis import AgentStep, AiUsageLog, AnalysisTask
from app.models.enums import TaskStatus
from app.models.identity import User
from app.services import application_verification as verification
from app.services.analysis import _daily_ai_budget
from app.tests.test_application_verification import (  # noqa: F401
    case,
    completion,
    inject_provider,
    model_answer,
)
from app.tests.test_real_matching import matching_db  # noqa: F401


async def usage_rows(factory, task_id):
    async with factory() as session:
        return list(await session.scalars(
            select(AiUsageLog).where(AiUsageLog.analysis_task_id == UUID(task_id))
        ))


async def reap(factory, task_id):
    """Deterministically do what recover_interrupted_tasks does to an abandoned lease."""
    async with factory() as session:
        await session.execute(
            update(AnalysisTask)
            .where(AnalysisTask.id == UUID(task_id))
            .values(status=TaskStatus.FAILED, run_token=None, error_message="任务执行已中断")
        )
        await session.commit()


async def test_usage_survives_lease_invalidation(case, monkeypatch):  # noqa: F811
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(_request):
        entered.set()
        await release.wait()
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    execute_task = asyncio.create_task(case.execute(started))
    claim_token = None
    try:
        deadline = asyncio.get_running_loop().time() + 10
        while True:
            async with case.factory() as session:
                task = await session.get(AnalysisTask, UUID(started["taskId"]))
                if task.status == TaskStatus.RUNNING and task.run_token:
                    claim_token = task.run_token
                    break
            assert asyncio.get_running_loop().time() < deadline, "task never claimed"
            await asyncio.sleep(0.01)
        await asyncio.wait_for(entered.wait(), timeout=5)
        await reap(case.factory, started["taskId"])
    finally:
        release.set()
    await asyncio.wait_for(execute_task, timeout=10)
    rows = await usage_rows(case.factory, started["taskId"])
    assert len(rows) == 1, f"expected exactly one usage row, got {len(rows)}"
    assert rows[0].input_tokens == 123 and rows[0].output_tokens == 45
    assert rows[0].cache_hit_tokens == 17
    assert rows[0].run_token == claim_token and rows[0].request_seq == 1
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.FAILED
        assert (task.input_snapshot or {}).get("analysis") is None


async def test_usage_survives_finalize_commit_failure(case, monkeypatch):  # noqa: F811
    async def handler(_request):
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    real_factory = case.factory

    @asynccontextmanager
    async def instrumented():
        async with real_factory() as session:
            real_commit = session.commit

            async def commit():
                if any(isinstance(obj, AgentStep) for obj in session.new):
                    raise RuntimeError("synthetic finalize commit failure")
                await real_commit()

            session.commit = commit
            yield session

    case.factory = instrumented
    started = await case.start()
    with pytest.raises(RuntimeError, match="synthetic finalize commit failure"):
        await case.execute(started)
    rows = await usage_rows(real_factory, started["taskId"])
    assert len(rows) == 1 and rows[0].input_tokens == 123
    async with real_factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.RUNNING


async def test_duplicate_accounting_is_idempotent(case, monkeypatch):  # noqa: F811
    async def handler(_request):
        return completion(model_answer(case.snapshot))

    provider = inject_provider(monkeypatch, handler)
    started = await case.start()
    await case.execute(started)
    rows = await usage_rows(case.factory, started["taskId"])
    assert len(rows) == 1
    written = await verification.persist_verification_usage(
        case.factory, UUID(started["taskId"]), rows[0].run_token, provider
    )
    assert written == 0
    assert len(await usage_rows(case.factory, started["taskId"])) == 1


async def test_usage_survives_cancellation_after_response(case, monkeypatch):  # noqa: F811
    final_recheck = asyncio.Event()
    release = asyncio.Event()
    handler_calls = 0
    real_authorized = verification._authorized

    async def stalled_authorized(*args, **kwargs):
        # Durable admission also takes a fresh lock. Inject cancellation only
        # after the synthetic HTTP handler actually returned a response.
        if kwargs.get("lock") and handler_calls:
            final_recheck.set()
            await asyncio.wait_for(release.wait(), timeout=15)
        return await real_authorized(*args, **kwargs)

    async def handler(_request):
        nonlocal handler_calls
        handler_calls += 1
        return completion(model_answer(case.snapshot))

    provider = inject_provider(monkeypatch, handler)
    # Patch after start: the create route also rechecks authorization with
    # lock=True, and only the execute-phase recheck after the model response
    # may stall here.
    started = await case.start()
    monkeypatch.setattr(verification, "_authorized", stalled_authorized)
    execute_task = asyncio.create_task(case.execute(started))
    await asyncio.wait_for(final_recheck.wait(), timeout=5)
    # Cancellation is injected only after the model answered with valid usage.
    assert handler_calls == 1, "final recheck must come after the only model response"
    assert provider.usage_records and provider.usage_records[0].usage_present
    execute_task.cancel()
    with suppress(asyncio.CancelledError):
        await execute_task
    release.set()
    await reap(case.factory, started["taskId"])
    rows = await usage_rows(case.factory, started["taskId"])
    assert len(rows) == 1 and rows[0].input_tokens == 123
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.FAILED
        assert (task.input_snapshot or {}).get("analysis") is None


async def test_usage_booking_finishes_after_outer_task_cancellation(case, monkeypatch):  # noqa: F811
    response_seen = asyncio.Event()
    booking_entered = asyncio.Event()
    release_booking = asyncio.Event()
    booking_committed = asyncio.Event()

    async def handler(_request):
        response_seen.set()
        return completion(model_answer(case.snapshot))

    provider = inject_provider(monkeypatch, handler)
    persist = verification.persist_verification_usage

    async def delayed_persist(*args, **kwargs):
        booking_entered.set()
        await release_booking.wait()
        result = await persist(*args, **kwargs)
        booking_committed.set()
        return result

    monkeypatch.setattr(verification, "persist_verification_usage", delayed_persist)
    started = await case.start()
    execute_task = asyncio.create_task(case.execute(started))
    try:
        await asyncio.wait_for(booking_entered.wait(), timeout=5)
        assert response_seen.is_set()
        assert provider.usage_records[0].usage_present
        execute_task.cancel()
        with suppress(asyncio.CancelledError):
            await execute_task
    finally:
        release_booking.set()

    await asyncio.wait_for(booking_committed.wait(), timeout=5)
    rows = await usage_rows(case.factory, started["taskId"])
    assert len(rows) == 1 and rows[0].input_tokens == 123
    await reap(case.factory, started["taskId"])
    async with case.factory() as session:
        task = await session.get(AnalysisTask, UUID(started["taskId"]))
        assert task.status == TaskStatus.FAILED
        assert (task.input_snapshot or {}).get("analysis") is None


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"prompt_tokens": "123", "completion_tokens": 45},
        {"prompt_tokens": 5.7, "completion_tokens": 45},
        {"prompt_tokens": True, "completion_tokens": 45},
        {"prompt_tokens": -1, "completion_tokens": 45},
        {"prompt_tokens": 123, "completion_tokens": "45"},
    ],
    ids=["missing", "string-input", "float-input", "bool-input", "negative-input", "string-output"],
)
async def test_untrustworthy_usage_writes_no_ledger_row(case, monkeypatch, usage):  # noqa: F811
    async def handler(_request):
        body = json.loads(completion(model_answer(case.snapshot)).content)
        if usage is None:
            body.pop("usage")
        else:
            body["usage"] = usage
        return httpx.Response(200, json=body)

    inject_provider(monkeypatch, handler)
    started = await case.start()
    await case.execute(started)
    result = await case.result(started)
    assert result["status"] == "completed"
    assert await usage_rows(case.factory, started["taskId"]) == []
    # Durable mode keeps missing/invalid receipt totals unknown rather than
    # exposing a display-only zero as if it were a trustworthy response fact.
    assert result["usage"] is None
    assert result["usageKnown"] is False


async def test_valid_usage_marks_usage_known(case, monkeypatch):  # noqa: F811
    async def handler(_request):
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    await case.execute(started)
    result = await case.result(started)
    assert result["usageKnown"] is True
    assert len(await usage_rows(case.factory, started["taskId"])) == 1


async def test_daily_budget_counts_distinct_tasks_and_sums_rows(case, monkeypatch):  # noqa: F811
    async def handler(_request):
        return completion(model_answer(case.snapshot))

    inject_provider(monkeypatch, handler)
    started = await case.start()
    await case.execute(started)
    async with case.factory() as session:
        session.add(AiUsageLog(
            analysis_task_id=UUID(started["taskId"]),
            model="deepseek-flash", input_tokens=10, output_tokens=5,
            cache_hit_tokens=0, latency_ms=1,
            unit_price_snapshot={"provider": "deepseek", "priceVerified": False},
        ))
        user = await session.scalar(select(User).where(User.email == "hr@example.com"))
        await session.commit()
    async with case.factory() as session:
        allowed, reason, stats = await _daily_ai_budget(session, user.id)
        await session.commit()
    assert allowed and reason is None
    assert stats["reportCount"] == 1, "two usage rows of one task must count as one report"
    assert stats["inputTokens"] == 133 and stats["outputTokens"] == 50
