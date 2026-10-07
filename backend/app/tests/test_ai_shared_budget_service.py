"""Owned-schema capacity contracts, not proof of provider wire integration."""

import asyncio
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.ai_budget import AiBudgetCutover, AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus, UserRole
from app.models.identity import User
from app.services.ai_budget import (
    GATE_ID,
    BudgetAdmissionError,
    BudgetPolicy,
    Capacity,
    SharedBudgetService,
    approve_output,
)
from app.tests.test_durable_matching import durable_db as durable_db

NOW = datetime(2026, 10, 7, 15, 59, 59, tzinfo=UTC)
POLICY = BudgetPolicy(1, 1000, 500, 1000, 500)


@pytest.fixture
async def budget_data(durable_db):  # noqa: F811 - imported fixture
    _app, factory, runtime = durable_db
    owner, admin, first, second = (uuid4() for _ in range(4))
    async with factory() as session:
        session.add_all(
            [
                User(
                    id=owner,
                    email=f"budget-{owner}@synthetic.invalid",
                    password_hash="synthetic",
                    display_name="synthetic budget student",
                    role=UserRole.STUDENT,
                ),
                User(
                    id=admin,
                    email=f"budget-{admin}@synthetic.invalid",
                    password_hash="synthetic",
                    display_name="synthetic admin",
                    role=UserRole.ADMIN,
                ),
            ]
        )
        await session.flush()
        for task_id, task_type in ((first, "job_match"), (second, "application_verification")):
            session.add(
                AnalysisTask(
                    id=task_id,
                    created_by=owner,
                    task_type=task_type,
                    status=TaskStatus.RUNNING,
                    run_token=uuid4(),
                    input_snapshot={"externalAiConsent": True},
                )
            )
        session.add(
            AiBudgetCutover(
                id=GATE_ID,
                enabled=True,
                activated_by=admin,
                activated_at=NOW,
                inventory_digest="a" * 64,
                reason="isolated capacity fixture, no production activation",
            )
        )
        await session.commit()
    return factory, runtime, owner, first, second


async def new_attempt(session, owner, task_id, *, inputs=100, outputs=300, **changes):
    row = AiRequestAttempt(
        id=uuid4(),
        analysis_task_id=task_id,
        created_by=owner,
        run_token=uuid4(),
        step="analysis",
        physical_sequence=1,
        provider="synthetic",
        model="synthetic",
        state="not_sent",
        estimated_input_tokens=inputs,
        max_output_tokens=outputs,
        created_at=NOW,
        updated_at=NOW,
        usage_raw={},
    )
    for name, value in changes.items():
        setattr(row, name, value)
    session.add(row)
    await session.flush()
    return row


@pytest.mark.parametrize(
    "daily,report,inputs,requested,expected",
    [
        (Capacity(0, 0, frozenset()), Capacity(0, 0, frozenset()), 100, 700, 500),
        (Capacity(0, 450, frozenset()), Capacity(0, 0, frozenset()), 100, 300, 50),
        (Capacity(0, 0, frozenset()), Capacity(0, 490, frozenset()), 100, 300, 10),
        (Capacity(950, 0, frozenset()), Capacity(0, 0, frozenset()), 100, 300, "daily_input"),
        (Capacity(0, 0, frozenset()), Capacity(990, 0, frozenset()), 100, 300, "report_input"),
        (Capacity(0, 500, frozenset()), Capacity(0, 0, frozenset()), 100, 300, "output_token"),
    ],
)
def test_grant_is_bounded_by_daily_and_entire_report(daily, report, inputs, requested, expected):
    if isinstance(expected, str):
        with pytest.raises(BudgetAdmissionError, match=expected):
            approve_output(POLICY, daily, report, uuid4(), inputs, requested)
    else:
        assert approve_output(POLICY, daily, report, uuid4(), inputs, requested) == expected


async def test_hold_and_cross_run_grant_do_not_reset_report_capacity(budget_data):
    factory, _runtime, owner, task, other = budget_data
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    async with factory() as session:
        first = await new_attempt(session, owner, task)
        assert await service.reserve(session, first) == 300
        await session.commit()
    async with factory() as session:
        retry = await new_attempt(session, owner, task)
        assert await service.reserve(session, retry) == 200
        assert retry.max_output_tokens == 200
        await session.commit()
    async with factory() as session:
        attempt = await new_attempt(session, owner, other)
        with pytest.raises(BudgetAdmissionError, match="daily_report_limit"):
            await service.reserve(session, attempt)
        await session.rollback()
    async with factory() as session:
        usage = await service.capacity(session, owner, day=date(2026, 10, 7))
        assert (usage.inputs, usage.outputs, usage.task_ids) == (200, 500, frozenset([task]))


async def test_disabled_gate_or_unreserved_old_attempt_cannot_admit(budget_data):
    factory, _runtime, owner, task, other = budget_data
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    async with factory() as session:
        gate = await session.get(AiBudgetCutover, GATE_ID)
        gate.enabled = False
        row = await new_attempt(session, owner, task)
        with pytest.raises(BudgetAdmissionError, match="not_enabled"):
            await service.reserve(session, row)
        await session.rollback()
    async with factory() as session:
        await new_attempt(session, owner, task)
        await session.commit()
    async with factory() as session:
        row = await new_attempt(session, owner, other)
        with pytest.raises(BudgetAdmissionError, match="inventory_incomplete"):
            await service.reserve(session, row)
        await session.rollback()


async def test_midnight_transfer_moves_only_unsent_hold(budget_data):
    factory, _runtime, owner, task, _other = budget_data
    clock = [NOW]
    service = SharedBudgetService(clock=lambda: clock[0], policy=POLICY)
    async with factory() as session:
        row = await new_attempt(session, owner, task)
        await service.reserve(session, row)
        attempt_id = row.id
        await session.commit()
    clock[0] = datetime(2026, 10, 7, 16, 0, 1, tzinfo=UTC)
    async with factory() as session:
        attempt, hold = await service.lock_attempt(session, attempt_id, include_today=True)
        await service.transfer_before_intent(session, attempt, hold)
        assert hold.output_bound == attempt.max_output_tokens == 300
        await session.commit()
    async with factory() as session:
        old = await service.capacity(session, owner, day=date(2026, 10, 7))
        new = await service.capacity(session, owner, day=date(2026, 10, 8))
        assert (old.inputs, old.outputs, len(old.task_ids)) == (0, 0, 0)
        assert (new.inputs, new.outputs, new.task_ids) == (100, 300, frozenset([task]))


async def test_late_actual_over_bound_stays_original_day_and_blocks_new_admission(budget_data):
    factory, _runtime, owner, task, _other = budget_data
    clock = [NOW]
    service = SharedBudgetService(clock=lambda: clock[0], policy=POLICY)
    async with factory() as session:
        row = await new_attempt(session, owner, task)
        await service.reserve(session, row)
        row.state, row.send_intent_at, row.sending_day = "in_flight", NOW, date(2026, 10, 7)
        attempt_id = row.id
        await session.commit()
    clock[0] = datetime(2026, 10, 8, 16, tzinfo=UTC)
    async with factory() as session:
        attempt, hold = await service.lock_attempt(session, attempt_id)
        service.settle(attempt, hold, inputs=1100, outputs=700)
        service.settle(attempt, hold, inputs=1100, outputs=700)
        await session.commit()
    async with factory() as session:
        original = await service.capacity(session, owner, day=date(2026, 10, 7))
        today = await service.capacity(session, owner, day=service.today())
        assert (original.inputs, original.outputs) == (1100, 700)
        assert (today.inputs, today.outputs) == (0, 0)
        retry = await new_attempt(session, owner, task)
        with pytest.raises(BudgetAdmissionError, match="report_input"):
            await service.reserve(session, retry)
        await session.rollback()


async def test_pre_budget_known_unknown_and_not_sent_strict_backfill(budget_data):
    factory, _runtime, owner, task, _other = budget_data
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    async with factory() as session:
        known = await new_attempt(
            session,
            owner,
            task,
            state="received_unbooked",
            send_intent_at=NOW,
            sending_day=date(2026, 10, 7),
            usage_input_tokens=12,
            usage_output_tokens=7,
            usage_cache_hit_tokens=0,
            usage_raw={"prompt_tokens": 12, "completion_tokens": 7},
        )
        unknown = await new_attempt(
            session,
            owner,
            task,
            state="usage_unknown",
            send_intent_at=NOW,
            sending_day=date(2026, 10, 7),
        )
        closed = await new_attempt(session, owner, task, ended_at=NOW)
        await session.commit()
        ids = [known.id, unknown.id, closed.id]
    async with factory() as session:
        before = [dict(row.__dict__) for row in await session.scalars(select(AiRequestAttempt))]
        assert await service.backfill_pre_budget_attempts(session) == 3
        await session.commit()
    async with factory() as session:
        after = [dict(row.__dict__) for row in await session.scalars(select(AiRequestAttempt))]
        for snapshots in (before, after):
            for item in snapshots:
                item.pop("_sa_instance_state")
        assert before == after
        rows = list(
            await session.scalars(
                select(AiBudgetReservation).order_by(
                    AiBudgetReservation.created_at,
                )
            )
        )
        mapped = {row.attempt_id: row for row in rows}
        assert [mapped[key].state for key in ids] == ["settled", "held", "released"]
        assert all(row.source == "pre_budget_attempt" for row in rows)
        usage = await service.capacity(session, owner, day=date(2026, 10, 7))
        assert (usage.inputs, usage.outputs) == (112, 307)
        assert await service.backfill_pre_budget_attempts(session) == 0


async def test_backfill_missing_day_rejects_without_capacity_rows(budget_data):
    factory, _runtime, owner, task, _other = budget_data
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    async with factory() as session:
        await new_attempt(session, owner, task, state="usage_unknown")
        await session.commit()
    async with factory() as session:
        with pytest.raises(BudgetAdmissionError, match="send_day_missing"):
            await service.backfill_pre_budget_attempts(session)
        await session.rollback()
    async with factory() as session:
        assert list(await session.scalars(select(AiBudgetReservation))) == []


async def test_pg_cross_chain_last_slot_real_concurrent_sessions(budget_data):
    factory, runtime, owner, first, second = budget_data
    if not (runtime.database_url or "").startswith("postgresql+asyncpg://"):
        pytest.skip("Requires actual PostgreSQL row locks")
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    ready = asyncio.Event()
    reached = 0

    async def compete(task):
        nonlocal reached
        async with factory() as session:
            row = await new_attempt(session, owner, task)
            reached += 1
            if reached == 2:
                ready.set()
            await ready.wait()
            try:
                grant = await service.reserve(session, row)
                await session.commit()
                return grant
            except BudgetAdmissionError as exc:
                await session.rollback()
                return str(exc)

    results = await asyncio.wait_for(asyncio.gather(compete(first), compete(second)), 10)
    assert sorted(map(str, results)) == ["300", "daily_report_limit"]
    async with factory() as session:
        assert len(list(await session.scalars(select(AiBudgetReservation)))) == 1


async def test_committed_session_cannot_reuse_stale_day_lock_marker(budget_data):
    factory, _runtime, owner, task, _other = budget_data
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    async with factory() as session:
        row = await new_attempt(session, owner, task)
        await service.reserve(session, row)
        attempt_id = row.id
        await session.commit()
        attempt, hold = await service.lock_attempt(session, attempt_id, include_today=True)
        await session.commit()
        await session.execute(select(AiRequestAttempt.id).where(AiRequestAttempt.id == attempt_id))
        with pytest.raises(BudgetAdmissionError, match="server_day_changed_after_capacity_lock"):
            await service.transfer_before_intent(session, attempt, hold)
