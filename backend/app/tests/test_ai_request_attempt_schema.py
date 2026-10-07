"""OPS-01B schema contract for ai_request_attempts and the ledger attempt_id link."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.enums import UserRole
from app.models.identity import User

CONTRACT_COLUMNS = {
    "analysis_task_id": False,
    "created_by": False,
    "run_token": False,
    "step": False,
    "physical_sequence": False,
    "provider": False,
    "model": False,
    "state": False,
    "sending_day": True,
    "estimated_input_tokens": False,
    "max_output_tokens": False,
    "usage_input_tokens": True,
    "usage_output_tokens": True,
    "usage_cache_hit_tokens": True,
    "latency_ms": True,
    "usage_raw": False,
    "response_digest": True,
    "send_intent_at": True,
    "receipt_at": True,
    "booked_at": True,
    "ended_at": True,
    "reason": True,
}

VALID_STATES = ("not_sent", "in_flight", "received_unbooked", "booked", "usage_unknown")


@pytest.fixture
def session(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'attempt-schema.db'}")

    @sa.event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [
        Base.metadata.tables[name]
        for name in ("users", "analysis_tasks", "ai_request_attempts", "ai_usage_logs")
    ]
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as active:
        user = User(
            email="attempt-schema@example.com",
            password_hash="hash",
            display_name="Student",
            role=UserRole.STUDENT,
        )
        active.add(user)
        active.flush()
        task = AnalysisTask(created_by=user.id, task_type="job_match")
        active.add(task)
        active.commit()
        yield active
    engine.dispose()


def make_attempt(task, **overrides):
    values = dict(
        analysis_task_id=task.id,
        created_by=task.created_by,
        run_token=uuid4(),
        step="verify",
        physical_sequence=1,
        provider="deepseek",
        model="deepseek-chat",
        estimated_input_tokens=100,
        max_output_tokens=200,
    )
    values.update(overrides)
    return AiRequestAttempt(**values)


def test_attempt_columns_match_contract(session):
    inspector = sa.inspect(session.connection())
    columns = {column["name"]: column for column in inspector.get_columns("ai_request_attempts")}
    for name, nullable in CONTRACT_COLUMNS.items():
        assert name in columns, f"missing contract column {name}"
        assert columns[name]["nullable"] is nullable, f"wrong nullability on {name}"
    for name, length in (
        ("step", 64), ("provider", 64), ("model", 100), ("state", 32), ("reason", 100),
        ("response_digest", 64),
    ):
        assert columns[name]["type"].length == length, f"wrong length on {name}"


def test_defaults_state_not_sent_and_empty_usage_raw(session):
    task = session.scalar(select(AnalysisTask).limit(1))
    attempt = make_attempt(task)
    session.add(attempt)
    session.commit()
    assert attempt.state == "not_sent"
    assert attempt.usage_raw == {}
    assert attempt.id is not None and attempt.created_at is not None


def test_every_contract_state_persists_and_others_are_rejected(session):
    task = session.scalar(select(AnalysisTask).limit(1))
    for index, state in enumerate(VALID_STATES):
        session.add(make_attempt(task, run_token=uuid4(), physical_sequence=index + 1, state=state))
    session.commit()
    assert session.scalar(
        select(sa.func.count()).select_from(AiRequestAttempt)
    ) == len(VALID_STATES)
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(make_attempt(task, run_token=uuid4(), physical_sequence=99, state="cancelled"))
        session.flush()


def test_physical_sequence_must_be_positive(session):
    task = session.scalar(select(AnalysisTask).limit(1))
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(make_attempt(task, physical_sequence=0))
        session.flush()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(make_attempt(task, physical_sequence=-1))
        session.flush()


def test_run_token_and_physical_sequence_are_unique_together(session):
    task = session.scalar(select(AnalysisTask).limit(1))
    run_token = uuid4()
    session.add(make_attempt(task, run_token=run_token, physical_sequence=1))
    session.commit()
    session.add(make_attempt(task, run_token=run_token, physical_sequence=2))
    session.commit()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(make_attempt(task, run_token=run_token, physical_sequence=2))
        session.flush()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(make_attempt(task, run_token=run_token, physical_sequence=1))
        session.flush()


@pytest.mark.parametrize(
    "field", ("estimated_input_tokens", "max_output_tokens", "usage_input_tokens",
              "usage_output_tokens", "usage_cache_hit_tokens", "latency_ms")
)
def test_token_and_latency_fields_reject_negatives(session, field):
    task = session.scalar(select(AnalysisTask).limit(1))
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(make_attempt(task, **{field: -1}))
        session.flush()


def test_nullable_usage_fields_allow_not_yet_known_values(session):
    task = session.scalar(select(AnalysisTask).limit(1))
    attempt = make_attempt(task, sending_day=date(2026, 10, 7))
    session.add(attempt)
    session.commit()
    stored = session.scalar(select(AiRequestAttempt).where(AiRequestAttempt.id == attempt.id))
    assert stored.sending_day == date(2026, 10, 7)
    assert stored.usage_input_tokens is None
    assert stored.usage_output_tokens is None
    assert stored.usage_cache_hit_tokens is None
    assert stored.latency_ms is None


def test_ended_not_sent_stays_not_sent_with_reason(session):
    task = session.scalar(select(AnalysisTask).limit(1))
    ended_at = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    attempt = make_attempt(task, ended_at=ended_at, reason="downgrade_guard_probe")
    session.add(attempt)
    session.commit()
    stored = session.scalar(select(AiRequestAttempt).where(AiRequestAttempt.id == attempt.id))
    assert stored.state == "not_sent"
    assert stored.ended_at == ended_at
    assert stored.reason == "downgrade_guard_probe"


def test_task_and_user_deletes_are_restricted(session):
    task = session.scalar(select(AnalysisTask).limit(1))
    user = session.get(User, task.created_by)
    session.add(make_attempt(task))
    session.commit()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.delete(task)
        session.flush()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.delete(user)
        session.flush()


def test_ledger_attempt_id_link_and_null_compat(session):
    task = session.scalar(select(AnalysisTask).limit(1))
    attempt = make_attempt(task)
    session.add(attempt)
    session.commit()
    legacy_first = AiUsageLog(analysis_task_id=task.id, model="deepseek-chat")
    legacy_second = AiUsageLog(analysis_task_id=task.id, model="deepseek-chat")
    linked = AiUsageLog(
        analysis_task_id=task.id,
        model="deepseek-chat",
        run_token=attempt.run_token,
        request_seq=attempt.physical_sequence,
        attempt_id=attempt.id,
    )
    session.add_all([legacy_first, legacy_second, linked])
    session.commit()
    assert legacy_first.attempt_id is None and legacy_second.attempt_id is None
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(AiUsageLog(
            analysis_task_id=task.id, model="deepseek-chat", attempt_id=attempt.id
        ))
        session.flush()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.delete(attempt)
        session.flush()
