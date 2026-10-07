import os
import re
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.enums import TaskStatus, UserRole
from app.models.identity import User
from app.services.ai_request_attempts import (
    AttemptAdmissionError,
    AttemptContext,
    AttemptService,
    ReceiptConflictError,
)


@pytest.fixture
async def durable_case(tmp_path):
    database_url = os.environ.get("CAREERPROOF_TEST_DATABASE_URL")
    schema = f"cp_test_{uuid4().hex}" if database_url else None
    if database_url:
        assert database_url.startswith("postgresql+asyncpg://")
        engine = create_async_engine(database_url, connect_args={
            "server_settings": {"search_path": f"{schema},public"},
        })
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'attempts.sqlite'}")

        @event.listens_for(engine.sync_engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    schema_created = False
    try:
        if schema:
            async with engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as connection:
            if schema:
                assert await connection.scalar(text("SELECT current_schema()")) == schema
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=[
                User.__table__, AnalysisTask.__table__,
                AiRequestAttempt.__table__, AiUsageLog.__table__,
            ], checkfirst=False))
            if schema:
                for table in ("users", "analysis_tasks", "ai_request_attempts", "ai_usage_logs"):
                    assert await connection.scalar(text(
                        "SELECT n.nspname FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE c.oid=to_regclass(:table)"
                    ), {"table": table}) == schema
        factory = async_sessionmaker(engine, expire_on_commit=False)
        user_id, task_id, token = uuid4(), uuid4(), uuid4()
        async with factory() as session:
            session.add(User(id=user_id, email=f"{user_id}@example.test", password_hash="synthetic",
                             display_name="Synthetic OPS", role=UserRole.STUDENT, is_active=True))
            await session.flush()
            session.add(AnalysisTask(id=task_id, created_by=user_id, task_type="verification",
                                     status=TaskStatus.RUNNING, run_token=token,
                                     input_snapshot={"externalAiConsent": True}))
            await session.commit()
        context = AttemptContext(
            task_id, user_id, token, "verification", "deepseek", "deepseek-flash",
        )
        yield factory, context, AttemptService(factory, context)
    finally:
        if schema_created:
            assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema)
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def sent(service):
    attempt_id = await service.prepare(estimated_input_tokens=100, max_output_tokens=20)
    await service.mark_intent(attempt_id)
    return attempt_id


async def end_claim(factory, context):
    async with factory() as session:
        task = await session.get(AnalysisTask, context.task_id)
        task.status, task.run_token = TaskStatus.FAILED, None
        await session.commit()


async def test_recovery_books_receipt_once_without_restoring_old_result(durable_case):
    factory, context, service = durable_case
    attempt_id = await sent(service)
    await service.receive(attempt_id, {"usage": {"prompt_tokens": 7, "completion_tokens": 2}}, 3)
    await end_claim(factory, context)
    assert await service.reconcile() == 1
    assert await service.reconcile() == 0
    summary = await service.summary()
    assert summary["usageKnown"] and summary["usageBooked"]
    async with factory() as session:
        task = await session.get(AnalysisTask, context.task_id)
        rows = list(await session.scalars(select(AiUsageLog)))
        assert task.status == TaskStatus.FAILED and task.run_token is None
        assert "analysis" not in task.input_snapshot
        assert len(rows) == 1 and rows[0].attempt_id == attempt_id
        assert (rows[0].input_tokens, rows[0].output_tokens) == (7, 2)


async def test_late_receipt_can_settle_unknown_old_claim(durable_case):
    factory, context, service = durable_case
    attempt_id = await sent(service)
    await end_claim(factory, context)
    assert await service.reconcile() == 0
    assert not (await service.summary())["usageKnown"]
    await service.receive(attempt_id, {"usage": {"prompt_tokens": 0, "completion_tokens": 0}}, 3)
    assert await service.reconcile() == 1
    assert (await service.summary())["usageKnown"]


async def test_no_receipt_is_unknown_and_never_a_zero_ledger(durable_case):
    factory, context, service = durable_case
    await sent(service)
    await end_claim(factory, context)
    await service.reconcile()
    async with factory() as session:
        row = await session.scalar(select(AiRequestAttempt))
        assert row.state == "usage_unknown" and row.usage_input_tokens is None
        assert list(await session.scalars(select(AiUsageLog))) == []
    assert (await service.summary())["unknownAttemptCount"] == 1


async def test_prepared_unsent_is_closed_without_billing_after_claim_loss(durable_case):
    factory, context, service = durable_case
    attempt_id = await service.prepare(estimated_input_tokens=100, max_output_tokens=20)
    await end_claim(factory, context)
    with pytest.raises(AttemptAdmissionError):
        await service.mark_intent(attempt_id)
    async with factory() as session:
        row = await session.get(AiRequestAttempt, attempt_id)
        assert row.state == "not_sent" and row.ended_at is not None
    assert (await service.summary())["intentCount"] == 0


async def test_conflicting_receipt_and_wrong_owner_do_not_rewrite_facts(durable_case):
    factory, context, service = durable_case
    attempt_id = await sent(service)
    payload = {"usage": {"prompt_tokens": 7, "completion_tokens": 2}}
    await service.receive(attempt_id, payload, 3)
    await service.receive(attempt_id, payload, 999)
    with pytest.raises(ReceiptConflictError):
        await service.receive(
            attempt_id, {"usage": {"prompt_tokens": 8, "completion_tokens": 2}}, 3,
        )
    wrong = AttemptService(factory, replace(context, created_by=uuid4()))
    with pytest.raises(ReceiptConflictError):
        await wrong.book_one(attempt_id)
    assert await service.book_one(attempt_id) == 1
    async with factory() as session:
        row = await session.get(AiRequestAttempt, attempt_id)
        assert row.usage_input_tokens == 7 and row.latency_ms == 3


async def test_legacy_claim_cannot_switch_to_attempt_accounting(durable_case):
    factory, context, service = durable_case
    async with factory() as session:
        session.add(AiUsageLog(analysis_task_id=context.task_id, model=context.model,
                              run_token=context.run_token, request_seq=1,
                              input_tokens=7, output_tokens=2, cache_hit_tokens=0, latency_ms=3))
        await session.commit()
    with pytest.raises(AttemptAdmissionError, match="legacy_claim"):
        await service.prepare(estimated_input_tokens=100, max_output_tokens=20)


async def test_invalid_persisted_receipt_is_not_booked(durable_case):
    factory, context, service = durable_case
    attempt_id = await sent(service)
    await service.receive(attempt_id, {"usage": {"prompt_tokens": 7, "completion_tokens": 2}}, 3)
    async with factory() as session:
        row = await session.get(AiRequestAttempt, attempt_id)
        row.usage_input_tokens = 8
        await session.commit()
    with pytest.raises(ReceiptConflictError, match="not_trustworthy"):
        await service.book_one(attempt_id)
    async with factory() as session:
        assert list(await session.scalars(select(AiUsageLog))) == []
