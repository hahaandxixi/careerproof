"""OPS-01C: the main matching flow accounts every physical provider request.

The fixture uses temporary SQLite by default or a unique disposable PostgreSQL
schema when CAREERPROOF_TEST_DATABASE_URL is explicitly configured. The provider
is always a synthetic DeepSeekProvider over httpx.MockTransport; no real model,
no network, production rows never touched.
"""

import asyncio
import json
import os
import re
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.core.database import Base, get_session
from app.main import create_app
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask, MatchReport
from app.models.enums import TaskStatus, UserRole
from app.models.identity import User
from app.services import analysis as analysis_service
from app.services import portfolio as portfolio_service
from app.services.ai_request_attempts import AttemptContext, AttemptService
from app.tests.budget_fixture_helpers import activate_owned_test_budget
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import (  # noqa: F401
    create_job,
    match_report,
    upload_materials,
)


@pytest.fixture
async def durable_db(tmp_path, monkeypatch, request):
    """Own cp_test schema with pre-write namespace verification, or temp SQLite."""
    database_url = os.environ.get("CAREERPROOF_TEST_DATABASE_URL")
    schema_name = None
    if database_url:
        if not database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("The integration database must use postgresql+asyncpg")
        schema_name = f"cp_test_{uuid4().hex}"
        assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema_name)
        engine = create_async_engine(
            database_url,
            connect_args={"server_settings": {"search_path": f"{schema_name},public"}},
        )
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'durable.db'}")

        @event.listens_for(engine.sync_engine, "connect")
        def configure_sqlite(connection, _record):
            connection.create_function(
                "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
            )
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    app = create_app()
    schema_created = False
    try:
        if schema_name:
            async with engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            schema_created = True
        async with engine.begin() as connection:
            if schema_name:
                assert await connection.scalar(text("SELECT current_schema()")) == schema_name
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[
                        table
                        for table in Base.metadata.sorted_tables
                        if table.name != "knowledge_chunks"
                    ],
                    checkfirst=False,
                )
            )
            if schema_name:
                for table in (
                    table.name for table in Base.metadata.sorted_tables
                    if table.name != "knowledge_chunks"
                ):
                    assert await connection.scalar(
                        text(
                            "SELECT n.nspname FROM pg_class c "
                            "JOIN pg_namespace n ON n.oid=c.relnamespace "
                            "WHERE c.oid=to_regclass(:table)"
                        ),
                        {"table": table},
                    ) == schema_name, table
        factory = async_sessionmaker(engine, expire_on_commit=False)
        # Capacity/admin unit cases explicitly construct their own gate. Other
        # workflow cases exercise actual audited activation before model calls.
        if "budget_data" not in request.fixturenames:
            await activate_owned_test_budget(factory, schema=schema_name)

        async def session_override():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        monkeypatch.setattr(analysis_service, "async_session_factory", factory)
        monkeypatch.setattr(portfolio_service, "async_session_factory", factory)
        monkeypatch.setattr("app.api.v1.analysis.async_session_factory", factory)
        monkeypatch.setattr(settings, "storage_base_dir", tmp_path / "materials")
        yield app, factory, SimpleNamespace(schema=schema_name, database_url=database_url)
    finally:
        app.dependency_overrides.clear()
        if schema_created:
            # Only this fixture's generated schema is removed; never target public.
            assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema_name)
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await engine.dispose()


def synthetic_provider(handler) -> DeepSeekProvider:
    provider = DeepSeekProvider(
        api_key="synthetic-only",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
        max_attempts=3,
    )
    provider._retry_delay = lambda response, attempt: 0
    return provider


def analysis_answer(requirement_id: str, *, citation_ids: list[str]) -> dict:
    return {
        "summary": "当前材料展示了求和函数的局部实现片段。",
        "items": [
            {
                "requirement_id": requirement_id,
                "explanation": "片段包含函数声明与求和实现，运行结果未展示。",
                "citation_ids": citation_ids,
                "information_gap": "运行结果与本人贡献仍需核验。",
                "suggestion": "补充可定位的运行记录并核对输出。",
                "confidence": 0.5,
                "rating": {
                    "level": 1 if citation_ids else None,
                    "reason": "存在相关实现线索。",
                    "criteria": [
                        {
                            "criterion": "relevance",
                            "supported": bool(citation_ids),
                            "citation_ids": citation_ids,
                            "reason": "实现片段可见。",
                        },
                        {
                            "criterion": "operation",
                            "supported": False,
                            "citation_ids": [],
                            "reason": "缺少实质操作展示。",
                        },
                        {
                            "criterion": "task",
                            "supported": False,
                            "citation_ids": [],
                            "reason": "缺少完整任务实现。",
                        },
                    ],
                },
            }
        ],
    }


def classify_request(request: httpx.Request) -> str:
    body = json.loads(request.content)
    if "tools" in body:
        return "planning_1"
    source = json.loads(body["messages"][1]["content"])
    return "repair" if "validationFeedback" in source else "analysis"


def retry_handler(calls: list, outcomes: list):
    """Planning (if reached): 503 without usage then a decline; analysis: a 429
    that still carries trusted usage then a citation conflict; repair: valid.
    Each entry in outcomes is (state, (input_tokens, output_tokens) | None)."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        kind = classify_request(request)
        body = json.loads(request.content)
        if kind == "planning_1":
            if not any(classify_request(prior) == "planning_1" for prior in calls[:-1]):
                outcomes.append(("unknown", None))
                return httpx.Response(503, json={"error": {"code": "1305"}})
            outcomes.append(("booked", (100, 10)))
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "无需补检索"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                },
            )
        source = json.loads(body["messages"][1]["content"])
        requirement_id = source["requirements"][0]["requirement_id"]
        if kind == "analysis":
            if not any(classify_request(prior) == "analysis" for prior in calls[:-1]):
                # A retryable HTTP status whose error body still carries a
                # parsable usage object stays a trusted physical receipt.
                outcomes.append(("booked", (30, 5)))
                return httpx.Response(
                    429, json={"usage": {"prompt_tokens": 30, "completion_tokens": 5}}
                )
            outcomes.append(("booked", (200, 80)))
            answer = analysis_answer(requirement_id, citation_ids=["R1-E9"])
        else:
            outcomes.append(("booked", (150, 60)))
            answer = analysis_answer(requirement_id, citation_ids=["R1-E1"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(answer, ensure_ascii=False)}}
                ],
                "usage": {
                    "prompt_tokens": outcomes[-1][1][0],
                    "completion_tokens": outcomes[-1][1][1],
                },
            },
        )

    return handler


async def test_every_physical_matching_request_is_durable_attempted_and_booked(
    durable_db, monkeypatch
):
    app, factory, _runtime = durable_db
    calls: list = []
    outcomes: list = []
    provider = synthetic_provider(retry_handler(calls, outcomes))
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, "durable-owner@example.com")
        job = await create_job(owner)
        await register(student, "durable-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        report = await match_report(student, job, resume, version, externalAiConsent=True)

    expected_steps = [classify_request(call) for call in calls]
    expected_states = [state for state, _usage in outcomes]
    expected_usage = [usage for _state, usage in outcomes]
    assert report["analysisMode"] == "ai_evidence"
    assert report["aiFallbackUsed"] is False
    assert report["aiProvider"] == "deepseek"
    assert report["items"][0]["aiStatus"] == "validated"
    assert report["items"][0]["aiCitationIds"] == ["R1-E1"]

    async with factory() as session:
        task_id = UUID(report["taskId"])
        task = await session.get(AnalysisTask, task_id)
        attempts = list(
            await session.scalars(
                select(AiRequestAttempt)
                .where(AiRequestAttempt.analysis_task_id == task_id)
                .order_by(AiRequestAttempt.physical_sequence)
            )
        )
        assert len(attempts) == len(calls) >= 3
        assert [row.physical_sequence for row in attempts] == list(
            range(1, len(attempts) + 1)
        )
        assert [row.step for row in attempts] == expected_steps
        assert [row.state for row in attempts] == expected_states
        assert {row.provider for row in attempts} == {"deepseek"}
        assert {row.model for row in attempts} == {"deepseek-flash"}
        assert len({row.run_token for row in attempts}) == 1
        assert attempts[0].created_by == UUID(report["candidateId"])
        assert task.input_snapshot["usageAccountingMode"] == "attempt_v1"

        ledger = list(
            await session.scalars(
                select(AiUsageLog).where(AiUsageLog.analysis_task_id == task_id)
            )
        )
        trusted_rows = [
            (row, usage)
            for row, state, usage in zip(attempts, expected_states, expected_usage, strict=True)
            if state == "booked"
        ]
        assert sorted(row.physical_sequence for row, _usage in trusted_rows) == sorted(
            row.request_seq for row in ledger
        )
        # Every trusted physical request books exactly one ledger row, keyed to
        # its attempt; the legacy aggregate finalize row never appears.
        ledger_by_seq = {row.request_seq: row for row in ledger}
        for row, (expected_input, expected_output) in trusted_rows:
            booked = ledger_by_seq[row.physical_sequence]
            assert booked.attempt_id == row.id
            assert (booked.input_tokens, booked.output_tokens) == (
                expected_input,
                expected_output,
            )
            assert booked.run_token == row.run_token

        report_row = await session.scalar(
            select(MatchReport).where(MatchReport.analysis_task_id == task_id)
        )
        metadata = report_row.analysis_metadata
        summary = metadata["attemptSummary"]
        unknown_count = expected_states.count("usage_unknown")
        assert summary["accountingMode"] == "attempt_v1"
        assert summary["attemptCount"] == len(attempts)
        assert summary["trustedReceiptCount"] == len(ledger)
        assert summary["unknownAttemptCount"] == unknown_count
        assert summary["usageKnown"] is (unknown_count == 0)
        assert summary["usageBooked"] is True
        assert metadata["usageBooked"] is True
        assert metadata["usageKnown"] is (unknown_count == 0)
        assert metadata["usage"]["input_tokens"] == summary["inputTokens"] == sum(
            usage[0] for usage in expected_usage if usage
        )
        assert metadata["usage"]["output_tokens"] == summary["outputTokens"] == sum(
            usage[1] for usage in expected_usage if usage
        )
        assert metadata["usage"]["latency_ms"] == summary["latencyMs"] == sum(
            row.latency_ms for row, _usage in trusted_rows
        )


def invalid_output_handler(calls: list, outcomes: list):
    """Analysis and its repair both violate citation boundaries; the workflow
    must fall back to rules while every persisted receipt still settles."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        source = json.loads(body["messages"][1]["content"])
        requirement_id = source["requirements"][0]["requirement_id"]
        outcomes.append(("booked", (200, 80) if "validationFeedback" not in source else (120, 40)))
        answer = analysis_answer(requirement_id, citation_ids=["R1-E9"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(answer, ensure_ascii=False)}}
                ],
                "usage": {
                    "prompt_tokens": outcomes[-1][1][0],
                    "completion_tokens": outcomes[-1][1][1],
                },
            },
        )

    return handler


async def run_durable_match(app, factory, monkeypatch, handler, *, email, **match_extra):
    provider = synthetic_provider(handler)
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, f"{email}-owner@example.com")
        job = await create_job(owner)
        student_user = await register(student, f"{email}-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        report = await match_report(
            student, job, resume, version, externalAiConsent=True, **match_extra
        )
    return report, student_user["id"]


async def test_fallback_after_invalid_repair_still_books_persisted_receipts(
    durable_db, monkeypatch
):
    app, factory, _runtime = durable_db
    calls: list = []
    outcomes: list = []
    report, _owner = await run_durable_match(
        app, factory, monkeypatch, invalid_output_handler(calls, outcomes),
        email="fallback",
    )
    assert report["analysisMode"] == "rules"
    assert report["aiFallbackUsed"] is True
    expected_states = [state for state, _usage in outcomes]
    async with factory() as session:
        task_id = UUID(report["taskId"])
        attempts = list(
            await session.scalars(
                select(AiRequestAttempt)
                .where(AiRequestAttempt.analysis_task_id == task_id)
                .order_by(AiRequestAttempt.physical_sequence)
            )
        )
        assert [row.step for row in attempts] == [classify_request(call) for call in calls]
        assert [row.state for row in attempts] == expected_states
        ledger = list(
            await session.scalars(
                select(AiUsageLog).where(AiUsageLog.analysis_task_id == task_id)
            )
        )
        # No legacy aggregate row: the fallback settled from durable receipts.
        assert sorted(row.request_seq for row in ledger) == [
            row.physical_sequence for row in attempts
        ]
        assert all(row.attempt_id is not None for row in ledger)
        report_row = await session.scalar(
            select(MatchReport).where(MatchReport.analysis_task_id == task_id)
        )
        metadata = report_row.analysis_metadata
        assert metadata["usageKnown"] is True
        assert metadata["usageBooked"] is True
        assert metadata["attemptSummary"]["trustedReceiptCount"] == len(ledger)
        assert metadata["usage"]["input_tokens"] == sum(usage[0] for _s, usage in outcomes)
        assert metadata["usage"]["output_tokens"] == sum(usage[1] for _s, usage in outcomes)


async def test_booking_failure_recovers_without_extra_http(durable_db, monkeypatch):
    app, factory, _runtime = durable_db
    calls: list = []
    outcomes: list = []
    original_reconcile = AttemptService.reconcile

    async def broken_reconcile(self):
        raise RuntimeError("synthetic ledger outage")

    monkeypatch.setattr(AttemptService, "reconcile", broken_reconcile)
    report, owner_id = await run_durable_match(
        app, factory, monkeypatch, retry_handler(calls, outcomes), email="bookfail",
    )
    # The booking outage must not resend HTTP nor fail the task.
    assert len(calls) == len(outcomes)
    assert report["analysisMode"] == "ai_evidence"

    async with factory() as session:
        task_id = UUID(report["taskId"])
        attempts = list(
            await session.scalars(
                select(AiRequestAttempt)
                .where(AiRequestAttempt.analysis_task_id == task_id)
                .order_by(AiRequestAttempt.physical_sequence)
            )
        )
        assert attempts and all(
            row.state == "received_unbooked" for row in attempts
        )
        ledger = list(
            await session.scalars(
                select(AiUsageLog).where(AiUsageLog.analysis_task_id == task_id)
            )
        )
        assert ledger == []
        report_row = await session.scalar(
            select(MatchReport).where(MatchReport.analysis_task_id == task_id)
        )
        metadata = report_row.analysis_metadata
        assert metadata["usageKnown"] is True
        assert metadata["usageBooked"] is False

    # Recoverable gap: an independent reconciliation books without new HTTP.
    monkeypatch.setattr(AttemptService, "reconcile", original_reconcile)
    service = AttemptService(factory, AttemptContext(
        task_id, UUID(owner_id), attempts[0].run_token,
        "analysis", "deepseek", "deepseek-flash",
    ))
    assert await service.reconcile() == len(attempts)
    assert len(calls) == len(outcomes)
    async with factory() as session:
        ledger = list(
            await session.scalars(
                select(AiUsageLog).where(AiUsageLog.analysis_task_id == task_id)
            )
        )
        assert len(ledger) == len(attempts)


async def test_report_save_failure_keeps_booked_receipts(durable_db, monkeypatch):
    app, factory, _runtime = durable_db
    calls: list = []
    outcomes: list = []

    def broken_asdict(value):
        raise RuntimeError("synthetic report save failure")

    monkeypatch.setattr(analysis_service, "asdict", broken_asdict)
    with pytest.raises(AssertionError):
        # match_report asserts completion; the report save failure must turn
        # the task FAILED instead of publishing a partial report.
        await run_durable_match(
            app, factory, monkeypatch, retry_handler(calls, outcomes), email="savefail",
        )
    # Nothing was resent after the failure; every trusted receipt stayed booked.
    assert len(calls) == len(outcomes)

    async with factory() as session:
        owner = await session.scalar(
            select(User).where(User.email == "savefail-student@example.com")
        )
        task = await session.scalar(
            select(AnalysisTask).where(
                AnalysisTask.created_by == owner.id,
                AnalysisTask.task_type == "job_match",
            )
        )
        assert task.status == TaskStatus.FAILED
        attempts = list(
            await session.scalars(
                select(AiRequestAttempt)
                .where(AiRequestAttempt.analysis_task_id == task.id)
                .order_by(AiRequestAttempt.physical_sequence)
            )
        )
        assert attempts and all(row.state == "booked" for row in attempts)
        ledger = list(
            await session.scalars(
                select(AiUsageLog).where(AiUsageLog.analysis_task_id == task.id)
            )
        )
        assert sorted(row.request_seq for row in ledger) == [
            row.physical_sequence for row in attempts
        ]
        reports = await session.scalar(
            select(MatchReport).where(MatchReport.analysis_task_id == task.id)
        )
        assert reports is None


async def test_owner_deactivation_and_material_replacement_send_nothing(
    durable_db, monkeypatch
):
    app, factory, _runtime = durable_db
    for scenario in ("owner_deactivated", "materials_replaced"):
        student_email = f"authz-{scenario}-student@example.com"
        calls: list = []
        outcomes: list = []
        original_progress = analysis_service.update_task_progress

        async def mutate_then_progress(
            session, tid, tok, *, progress, step,
            _scenario=scenario, _student_email=student_email,
            _original_progress=original_progress,
        ):
            result = await _original_progress(session, tid, tok, progress=progress, step=step)
            if progress == 55:
                async with factory() as mutation_session:
                    if _scenario == "owner_deactivated":
                        owner = await mutation_session.scalar(
                            select(User).where(User.email == _student_email)
                        )
                        owner.is_active = False
                    else:
                        task_row = await mutation_session.get(AnalysisTask, tid)
                        task_row.input_snapshot = {
                            **task_row.input_snapshot,
                            "materials": [
                                {**material, "versionNumber": 9999, "contentHash": "f" * 64}
                                for material in task_row.input_snapshot["materials"]
                            ],
                        }
                    await mutation_session.commit()
            return result

        monkeypatch.setattr(analysis_service, "update_task_progress", mutate_then_progress)
        # POST only: after deactivation the student session cannot read the API,
        # so all assertions read the database with the owner's own rows.
        provider = synthetic_provider(retry_handler(calls, outcomes))
        monkeypatch.setattr(settings, "ai_external_enabled", True)
        monkeypatch.setattr(settings, "ai_provider", "deepseek")
        monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
        monkeypatch.setattr(
            "app.agents.evidence_workflow.get_ai_provider",
            lambda _provider=provider: _provider,
        )
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://test") as owner_client,
            AsyncClient(transport=transport, base_url="http://test") as student_client,
        ):
            await register(owner_client, f"authz-{scenario}-owner@example.com")
            job = await create_job(owner_client)
            await register(student_client, student_email, "student")
            resume, _project, version = await upload_materials(student_client)
            accepted = await student_client.post(
                "/api/v1/matches",
                json={
                    "jobId": job["id"],
                    "resumeVersionId": resume["versionId"],
                    "projectVersionIds": [version["versionId"]],
                    "externalAiConsent": True,
                },
            )
            assert accepted.status_code == 202, accepted.text
            task_id = UUID(accepted.json()["data"]["taskId"])
        monkeypatch.setattr(analysis_service, "update_task_progress", original_progress)
        # Zero HTTP: durable admission refuses before any provider request.
        assert calls == [], scenario
        async with factory() as session:
            attempts = list(
                await session.scalars(
                    select(AiRequestAttempt)
                    .where(AiRequestAttempt.analysis_task_id == task_id)
                    .order_by(AiRequestAttempt.physical_sequence)
                )
            )
            ledger = list(
                await session.scalars(
                    select(AiUsageLog).where(AiUsageLog.analysis_task_id == task_id)
                )
            )
            assert ledger == [], scenario
            report_row = await session.scalar(
                select(MatchReport).where(MatchReport.analysis_task_id == task_id)
            )
            assert report_row is None, scenario
            task = await session.get(AnalysisTask, task_id)
            assert task.status == TaskStatus.FAILED
            if scenario == "owner_deactivated":
                # prepare() refuses before any row exists when the owner is gone.
                assert attempts == []
            else:
                # The prepared row is closed as not_sent; never relabelled.
                assert len(attempts) == 1
                assert attempts[0].state == "not_sent"
                assert attempts[0].ended_at is not None
                assert attempts[0].reason == "send_admission_failed"


async def test_concurrent_duplicate_booking_writes_one_ledger_row(durable_db):
    _app, factory, _runtime = durable_db
    user_id, task_id, token = uuid4(), uuid4(), uuid4()
    async with factory() as session:
        session.add(User(
            id=user_id, email=f"{user_id}@example.test", password_hash="synthetic",
            display_name="Synthetic OPS", role=UserRole.STUDENT, is_active=True,
        ))
        await session.flush()
        session.add(AnalysisTask(
            id=task_id, created_by=user_id, task_type="job_match",
            status=TaskStatus.RUNNING, run_token=token,
            input_snapshot={"externalAiConsent": True},
        ))
        await session.commit()
    service = AttemptService(factory, AttemptContext(
        task_id, user_id, token, "analysis", "deepseek", "deepseek-flash",
    ))
    attempt_id = await service.prepare(estimated_input_tokens=10, max_output_tokens=20)
    await service.mark_intent(attempt_id)
    await service.receive(
        attempt_id, {"usage": {"prompt_tokens": 11, "completion_tokens": 3}}, 7
    )
    written = await asyncio.gather(service.reconcile(), service.reconcile())
    assert sum(written) == 1
    async with factory() as session:
        rows = list(
            await session.scalars(
                select(AiUsageLog).where(AiUsageLog.analysis_task_id == task_id)
            )
        )
        assert len(rows) == 1
        assert (rows[0].input_tokens, rows[0].output_tokens) == (11, 3)
        attempt = await session.get(AiRequestAttempt, attempt_id)
        assert attempt.state == "booked"


class _ProbeTransport(httpx.AsyncBaseTransport):
    """Async transport that probes PostgreSQL row locks while the analysis
    HTTP request is pending — the exact window a borrowed session would leak."""

    def __init__(self, probe, calls, probe_results):
        self._probe = probe
        self._calls = calls
        self._probe_results = probe_results

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._calls.append(request)
        kind = classify_request(request)
        body = json.loads(request.content)
        if kind == "planning_1":
            source = json.loads(body["messages"][1]["content"])
            requirement_id = source["requirements"][0]["requirement_id"]
            tool_call = {
                "function": {
                    "name": "get_previous_report_context",
                    "arguments": json.dumps({"requirement_id": requirement_id}),
                }
            }
            return httpx.Response(200, json={
                "choices": [{"message": {"tool_calls": [tool_call]}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 5},
            })
        source = json.loads(body["messages"][1]["content"])
        requirement_id = source["requirements"][0]["requirement_id"]
        if kind == "analysis" and not self._probe_results:
            self._probe_results.append(await self._probe())
            answer = analysis_answer(requirement_id, citation_ids=["R1-E1"])
            usage = {"prompt_tokens": 200, "completion_tokens": 80}
        else:
            answer = analysis_answer(requirement_id, citation_ids=["R1-E1"])
            usage = {"prompt_tokens": 150, "completion_tokens": 60}
        return httpx.Response(200, json={
            "choices": [
                {"message": {"content": json.dumps(answer, ensure_ascii=False)}}
            ],
            "usage": usage,
        })


@pytest.mark.skipif(
    not os.environ.get("CAREERPROOF_TEST_DATABASE_URL"),
    reason="The borrowed-transaction probe needs the PostgreSQL integration database",
)
async def test_history_read_releases_borrowed_transaction_during_http(
    durable_db, monkeypatch
):
    app, factory, runtime = durable_db
    calls: list = []
    probe_results: list = []

    async def probe_locked_rows():
        engine = create_async_engine(
            runtime.database_url,
            connect_args={"server_settings": {"search_path": f"{runtime.schema},public"}},
        )
        try:
            async with engine.connect() as connection:
                return (await connection.execute(text(
                    "SELECT c.relname, l.mode, a.state FROM pg_locks l "
                    "JOIN pg_class c ON c.oid = l.relation "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "LEFT JOIN pg_stat_activity a ON a.pid = l.pid "
                    "WHERE n.nspname = :schema AND l.granted"
                ), {"schema": runtime.schema})).all()
        finally:
            await engine.dispose()

    async def noop_heartbeat(task_id, token, session_factory):
        return None

    monkeypatch.setattr(analysis_service, "heartbeat_task", noop_heartbeat)
    provider = DeepSeekProvider(
        api_key="synthetic-only",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        transport=_ProbeTransport(probe_locked_rows, calls, probe_results),
        max_attempts=3,
    )
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(owner, "probe-owner@example.com")
        job = await create_job(owner)
        await register(student, "probe-student@example.com", "student")
        resume, _project, version = await upload_materials(student)
        # A first rules-only report becomes the frozen history source.
        first = await match_report(student, job, resume, version)
        second = await match_report(
            student, job, resume, version,
            externalAiConsent=True, usePreviousReport=True,
        )

    assert len(probe_results) == 1
    # While the analysis HTTP was pending, no connection held a granted lock on
    # any relation of this schema: the main session and the history read session
    # had both released their transactions before the request was sent.
    assert probe_results[0] == []
    history_events = [
        event for event in second["aiToolCalls"]
        if event["tool"] == "get_previous_report_context"
    ]
    assert history_events and history_events[0]["status"] == "completed"
    assert history_events[0]["previousReportId"] == first["id"]
    async with factory() as session:
        task_id = UUID(second["taskId"])
        attempts = list(
            await session.scalars(
                select(AiRequestAttempt)
                .where(AiRequestAttempt.analysis_task_id == task_id)
                .order_by(AiRequestAttempt.physical_sequence)
            )
        )
        assert [row.step for row in attempts] == [classify_request(call) for call in calls]
        assert all(row.state == "booked" for row in attempts)
