"""Fresh administrator authority, immutable decisions, and conservative cutover."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models.ai_budget import AiBudgetAdjustment, AiBudgetCutover, AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus, UserRole
from app.models.identity import User
from app.services.ai_budget import GATE_ID, BudgetAdmissionError, SharedBudgetService
from app.services.ai_request_attempts import AttemptContext, AttemptService
from app.tests.test_ai_shared_budget_service import NOW, POLICY, new_attempt
from app.tests.test_ai_shared_budget_service import budget_data as budget_data
from app.tests.test_durable_matching import durable_db as durable_db


async def admin_id(factory):
    async with factory() as session:
        return await session.scalar(select(User.id).where(User.role == UserRole.ADMIN))


async def disable_fixture_gate(factory):
    async with factory() as session:
        gate = await session.get(AiBudgetCutover, GATE_ID)
        gate.enabled = False
        gate.inventory_digest = gate.activated_at = gate.activated_by = None
        gate.reason = ""
        await session.commit()


async def unknown_capacity(factory, owner, task, service):
    async with factory() as session:
        row = await new_attempt(
            session,
            owner,
            task,
            state="usage_unknown",
            send_intent_at=NOW,
            sending_day=date(2026, 10, 7),
        )
        attempt_id = row.id
        await session.commit()
    async with factory() as session:
        assert await service.backfill_pre_budget_attempts(session) == 1
        await session.commit()
    return attempt_id


async def test_unknown_adjustment_is_authorized_idempotent_and_never_a_receipt(
    budget_data,  # noqa: F811
):
    factory, _runtime, owner, task, _other = budget_data
    actor = await admin_id(factory)
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    attempt_id = await unknown_capacity(factory, owner, task, service)
    args = dict(
        attempt_id=attempt_id,
        operation_id="synthetic-audit-01",
        reason="explicit capacity decision; provider usage still unknown",
        input_tokens=20,
        output_tokens=30,
    )
    async with factory() as session:
        with pytest.raises(BudgetAdmissionError, match="administrator"):
            await service.adjust_unknown(session, actor_id=owner, **args)
        await session.rollback()
    async with factory() as session:
        result = await service.adjust_unknown(session, actor_id=actor, **args)
        await session.commit()
    async with factory() as session:
        assert await service.adjust_unknown(session, actor_id=actor, **args) == result
        await session.commit()
    async with factory() as session:
        audits = list(await session.scalars(select(AiBudgetAdjustment)))
        assert len(audits) == 1
        assert (audits[0].before_input_tokens, audits[0].before_output_tokens) == (100, 300)
        assert (audits[0].after_input_tokens, audits[0].after_output_tokens) == (20, 30)
        row = await session.get(AiRequestAttempt, attempt_id)
        assert row.state == "usage_unknown" and row.usage_input_tokens is None
        hold = await session.scalar(select(AiBudgetReservation))
        assert hold.state == "adjusted"
        context = AttemptContext(task, owner, row.run_token, row.step, row.provider, row.model)
    receipts = AttemptService(factory, context, budget=service)
    await receipts.receive(attempt_id, {"usage": {"prompt_tokens": 12, "completion_tokens": 7}}, 10)
    assert await receipts.book_one(attempt_id) == 1
    async with factory() as session:
        usage = await service.capacity(session, owner, day=date(2026, 10, 7))
        assert (usage.inputs, usage.outputs) == (12, 7)
        audit = await session.get(AiBudgetAdjustment, result)
        assert (audit.after_input_tokens, audit.after_output_tokens) == (20, 30)


async def test_disabled_admin_and_operation_reuse_do_not_rewrite_decision(budget_data):  # noqa: F811
    factory, _runtime, owner, task, _other = budget_data
    actor = await admin_id(factory)
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    attempt_id = await unknown_capacity(factory, owner, task, service)
    args = dict(
        attempt_id=attempt_id,
        operation_id="synthetic-once",
        reason="audited policy",
        input_tokens=0,
        output_tokens=0,
    )
    async with factory() as session:
        await service.adjust_unknown(session, actor_id=actor, **args)
        await session.commit()
    async with factory() as session:
        with pytest.raises(BudgetAdmissionError, match="operation_conflict"):
            await service.adjust_unknown(session, actor_id=actor, **{**args, "output_tokens": 1})
        await session.rollback()
    async with factory() as session:
        admin = await session.get(User, actor)
        admin.is_active = False
        await session.commit()
    async with factory() as session:
        with pytest.raises(BudgetAdmissionError, match="administrator"):
            await service.adjust_unknown(session, actor_id=actor, **args)
        await session.rollback()
    async with factory() as session:
        assert len(list(await session.scalars(select(AiBudgetAdjustment)))) == 1
        assert (await session.get(AiRequestAttempt, attempt_id)).state == "usage_unknown"


@pytest.mark.parametrize(
    "status,expected",
    [
        (TaskStatus.RUNNING, "must_drain"),
        (TaskStatus.FAILED, "legacy_external_run"),
        (TaskStatus.COMPLETED, "legacy_external_run"),
    ],
)
async def test_cutover_does_not_treat_old_terminal_unknown_run_as_zero(
    budget_data,  # noqa: F811 - imported fixture
    status,
    expected,  # noqa: F811
):
    factory, _runtime, _owner, _task, _other = budget_data
    actor = await admin_id(factory)
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    await disable_fixture_gate(factory)
    async with factory() as session:
        for row in await session.scalars(select(AnalysisTask)):
            row.status = status
        await session.commit()
    async with factory() as session:
        with pytest.raises(BudgetAdmissionError, match=expected):
            await service.activate(
                session, actor_id=actor, reason="synthetic cutover investigation"
            )
        await session.rollback()
    async with factory() as session:
        assert not (await session.get(AiBudgetCutover, GATE_ID)).enabled
        assert list(await session.scalars(select(AiBudgetReservation))) == []


async def test_empty_provenance_activation_requires_fresh_admin_and_keeps_first_audit(
    budget_data,  # noqa: F811
):
    factory, _runtime, owner, _task, _other = budget_data
    actor = await admin_id(factory)
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    await disable_fixture_gate(factory)
    async with factory() as session:
        for row in await session.scalars(select(AnalysisTask)):
            row.status = TaskStatus.COMPLETED
            row.input_snapshot = {"externalAiConsent": False}
        await session.commit()
    async with factory() as session:
        with pytest.raises(BudgetAdmissionError, match="administrator"):
            await service.activate(session, actor_id=owner, reason="unauthorized")
        await session.rollback()
    async with factory() as session:
        digest = await service.activate(
            session, actor_id=actor, reason="synthetic empty inventory audit"
        )
        assert len(digest) == 64
        await session.commit()
    async with factory() as session:
        assert (
            await service.activate(session, actor_id=actor, reason="cannot overwrite first")
            == digest
        )
        await session.commit()
    async with factory() as session:
        gate = await session.get(AiBudgetCutover, GATE_ID)
        assert gate.enabled and gate.reason == "synthetic empty inventory audit"
        assert gate.activated_by == actor


@pytest.mark.parametrize("valid_receipt", [True, False])
async def test_cutover_backfills_original_day_or_aborts_invalid_receipt(
    budget_data,  # noqa: F811 - imported fixture
    valid_receipt,  # noqa: F811
):
    factory, _runtime, owner, task, other = budget_data
    actor = await admin_id(factory)
    service = SharedBudgetService(clock=lambda: NOW, policy=POLICY)
    await disable_fixture_gate(factory)
    async with factory() as session:
        modern = await session.get(AnalysisTask, task)
        modern.status = TaskStatus.FAILED
        modern.input_snapshot = {"externalAiConsent": True, "usageAccountingMode": "attempt_v1"}
        offline = await session.get(AnalysisTask, other)
        offline.status = TaskStatus.COMPLETED
        offline.input_snapshot = {"externalAiConsent": False}
        row = await new_attempt(
            session,
            owner,
            task,
            state="received_unbooked",
            send_intent_at=NOW,
            sending_day=date(2026, 10, 7),
            usage_input_tokens=12,
            usage_output_tokens=7,
            usage_cache_hit_tokens=0,
            usage_raw={"prompt_tokens": 12, "completion_tokens": 7} if valid_receipt else {},
        )
        attempt_id = row.id
        await session.commit()
    async with factory() as session:
        if valid_receipt:
            assert (
                len(await service.activate(session, actor_id=actor, reason="audited old receipt"))
                == 64
            )
            await session.commit()
        else:
            with pytest.raises(BudgetAdmissionError, match="receipt_invalid"):
                await service.activate(session, actor_id=actor, reason="invalid old receipt")
            await session.rollback()
    async with factory() as session:
        gate = await session.get(AiBudgetCutover, GATE_ID)
        assert gate.enabled is valid_receipt
        hold = await session.scalar(select(AiBudgetReservation))
        if valid_receipt:
            assert hold.state == "settled" and hold.source == "pre_budget_attempt"
            assert hold.reservation_day == date(2026, 10, 7)
            assert (hold.actual_input_tokens, hold.actual_output_tokens) == (12, 7)
            assert (await session.get(AiRequestAttempt, attempt_id)).state == "received_unbooked"
        else:
            assert hold is None
