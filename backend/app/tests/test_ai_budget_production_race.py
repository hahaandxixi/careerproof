"""Real production entries racing for the owner's last daily-report slot.

Audited role premise (2026-10-09): a verification task is owned by the
enterprise requester (``_authorized`` requires ENTERPRISE) while a match task
is owned by a student (``_authorize_matching_snapshot`` requires STUDENT), and
one User carries exactly one role. No single owner can therefore legally span
both production entries, and this file never rewrites roles or owners. Each
chain instead races two distinct same-owner pending tasks into its own real
``execute`` entry; cross-owner budget isolation and the API role walls are
proven separately, and the shared-budget kernel's same-owner cross-chain race
remains covered by the service-layer PostgreSQL test
(test_ai_shared_budget_service.test_pg_cross_chain_last_slot_real_concurrent_sessions).

Orchestration contract per chain race:

* Both racing tasks are pending before either entry runs; each entry opens its
  own sessions through the fixture factory.
* Both chains commit their entry precheck transaction (claim/read) before any
  model work, so a both-arrived barrier right before
  ``AttemptService.prepare_for_send`` sits where no User/Task row lock is held.
  The barrier never waits inside ``_live_identity``'s transaction: the original
  ``_live_identity`` takes FOR NO KEY UPDATE on the same owner User row, and a
  barrier there would deadlock the race artificially.
* Each racer registers its PostgreSQL backend pid before attempting the
  original ``_live_identity`` lock; registration needs no row lock, so both
  racers can always arrive, and there is no pre-lock synchronization at all —
  the winner is decided purely by the real database lock race. Whichever side
  acquires the owner row lock first then waits — bounded, on the loser's
  registration event, never on sleeps — and confirms via pg_blocking_pids
  that the loser is really waiting on that lock, and only then continues into
  the original reserve/commit. Both racers therefore entered the original
  prepare and created independent sessions before the winner's commit; the
  loser is never released after that commit, and always executed its own real
  admission attempt against the committed winner hold before its natural
  lock-wait release and rejection.
* The winner's MockTransport blocks without returning; the loser finishes its
  rejection first, then a third independent session takes User, Task and
  AiDailyBudget rows FOR UPDATE NOWAIT to prove nothing is held across HTTP.
* Releasing the transport returns a trusted usage receipt: exactly one settle,
  one ledger row, and the original enterprise application snapshots unchanged.
"""

import asyncio
import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.agents import evidence_workflow
from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.models.ai_budget import AiBudgetReservation, AiDailyBudget
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask, MatchItem, MatchReport
from app.models.enums import TaskStatus, UserRole
from app.models.identity import StudentProfile, User
from app.models.recruitment import Application
from app.services import analysis as analysis_service
from app.services import application_verification as verification
from app.services.ai_budget import SharedBudgetService
from app.services.ai_request_attempts import AttemptContext, AttemptService
from app.services.task_runner import FastAPIBackgroundTaskRunner
from app.tests.test_application_verification import (
    case,  # noqa: F401
    completion,
    model_answer,
)
from app.tests.test_attempt_hard_stop import ORIGINAL_BACKGROUND_SUBMIT
from app.tests.test_durable_matching import classify_request
from app.tests.test_durable_matching_review import valid_response
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import (
    create_job,
    matching_db,  # noqa: F401 - required by the imported case fixture
    upload_materials,
)

SYNTHETIC_KEY = "sk-synthetic-production-race-000004"
OVERLAP_TIMEOUT_SECONDS = 15.0
CHAIN_TIMEOUT_SECONDS = 90.0
SYNTHETIC_USAGE = (123, 45)


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


async def require_postgres(fixture_case):
    if not os.environ.get("CAREERPROOF_TEST_DATABASE_URL"):
        pytest.skip(
            "The production-entry last-slot race needs real PostgreSQL row locks; "
            "set CAREERPROOF_TEST_DATABASE_URL to an isolated cp_test schema"
        )
    async with fixture_case.factory() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema)


def synthetic_provider(transport) -> DeepSeekProvider:
    return DeepSeekProvider(
        api_key=SYNTHETIC_KEY,
        base_url="https://api.deepseek.com",
        model=settings.deepseek_model,
        timeout_seconds=60,
        max_attempts=1,
        transport=transport,
    )


class HttpGate:
    """One shared MockTransport: the first physical HTTP blocks until released."""

    def __init__(self, respond):
        self.respond = respond
        self.calls = 0
        self.steps = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def handler(self, request):
        self.calls += 1
        self.steps.append(classify_request(request))
        self.entered.set()
        await asyncio.wait_for(self.release.wait(), 60)
        return self.respond(request)

    def provider(self) -> DeepSeekProvider:
        # A fresh provider per get_ai_provider() call mirrors production and
        # keeps each chain's durable observer bound to its own context.
        return synthetic_provider(httpx.MockTransport(self.handler))


class LastSlotRace:
    """Barrier before the original prepare; proof of a real owner-row lock wait."""

    def __init__(self, task_ids):
        self.task_ids = set(task_ids)
        self.both_arrived = asyncio.Event()
        self.both_registered = asyncio.Event()
        self.overlap = asyncio.Event()
        self.prepare_arrived = set()
        self.services = {}
        self.identity_pids = {}
        self.timeline = []

    def note(self, event, **detail):
        self.timeline.append({
            "loop": round(asyncio.get_running_loop().time(), 3),
            "utc": utc_now_text(),
            "event": event,
            **detail,
        })

    def install(self, monkeypatch):
        original_prepare = AttemptService.prepare_for_send
        original_identity = AttemptService._live_identity

        async def prepare_wrapper(service, **kwargs):
            task_id = service.context.task_id
            if task_id in self.task_ids and task_id not in self.prepare_arrived:
                self.prepare_arrived.add(task_id)
                self.services[task_id] = service
                self.note("prepare_arrived", task=str(task_id))
                if len(self.prepare_arrived) == len(self.task_ids):
                    self.both_arrived.set()
                await self.both_arrived.wait()
                self.note("prepare_entered_original", task=str(task_id))
            return await original_prepare(service, **kwargs)

        async def identity_wrapper(service, session):
            task_id = service.context.task_id
            intercept = (
                task_id in self.task_ids
                and service is self.services.get(task_id)
                and task_id not in self.identity_pids
            )
            if not intercept:
                return await original_identity(service, session)
            # Register this prepare session BEFORE attempting the original
            # identity lock, then attempt the lock immediately: the winner is
            # decided purely by the real database lock race, never by sleeps
            # or by any pre-lock synchronization.
            backend = await session.scalar(text("SELECT pg_backend_pid()"))
            self.identity_pids[task_id] = backend
            self.note("identity_session_registered_before_lock",
                      task=str(task_id), backend=backend)
            if len(self.identity_pids) == len(self.task_ids):
                self.both_registered.set()
            result = await original_identity(service, session)
            # This side now holds the owner User row lock (FOR NO KEY UPDATE).
            # Gate the original reserve/commit on the registration EVENT of
            # the other prepare session: the loser registers before its own
            # lock attempt and needs no row lock to do so, so it can always
            # arrive (no artificial deadlock). The loser was never released
            # after this winner's prepare/commit — both left the prepare-entry
            # barrier together, and this wait runs inside the winner's
            # still-open original transaction, before any reserve work.
            try:
                await asyncio.wait_for(
                    self.both_registered.wait(), OVERLAP_TIMEOUT_SECONDS
                )
            except TimeoutError:
                pytest.fail(
                    "the other racing prepare session never registered: "
                    + json.dumps(self.report(), ensure_ascii=False)
                )
            # Catalog fact (not sleep-ordering) that the loser is genuinely
            # waiting on this backend's row lock before reserve/commit run.
            await self.confirm_overlap(session)
            return result

        monkeypatch.setattr(AttemptService, "prepare_for_send", prepare_wrapper)
        monkeypatch.setattr(AttemptService, "_live_identity", identity_wrapper)

    async def confirm_overlap(self, session):
        if self.overlap.is_set():
            return
        mine = await session.scalar(text("SELECT pg_backend_pid()"))
        others = [pid for pid in self.identity_pids.values() if pid != mine]
        assert len(others) == 1, "both backends must be registered before overlap"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + OVERLAP_TIMEOUT_SECONDS
        while True:
            blockers = await session.scalar(
                text("SELECT pg_blocking_pids(:other)"), {"other": others[0]}
            )
            if blockers and mine in blockers:
                self.note(
                    "real_owner_lock_wait_proven",
                    holder=mine, waiter=others[0], blocked_by=list(blockers),
                )
                self.overlap.set()
                return
            if loop.time() > deadline:
                pytest.fail(
                    "racing prepares never overlapped on the owner User row: "
                    + json.dumps(self.report(), ensure_ascii=False)
                )
            await asyncio.sleep(0.01)

    def report(self):
        return {
            "taskIds": sorted(str(task) for task in self.task_ids),
            "identityBackends": {
                str(task): pid for task, pid in self.identity_pids.items()
            },
            "timeline": self.timeline,
        }


def print_race_evidence(label, payload):
    print(f"RACE-EVIDENCE {label} " + json.dumps(payload, ensure_ascii=False, default=str))


async def strict_nowait_unlocked(factory, statement, *, label):
    """A single NOWAIT attempt: any lock holder here fails the test."""
    async with factory() as session:
        try:
            await session.scalar(statement)
            await session.rollback()
        except OperationalError as exc:
            async with factory() as observer:
                blockers = list(await observer.execute(text(
                    "SELECT pid, wait_event_type, state, left(query, 160) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0"
                )))
            pytest.fail(
                f"{label} was still locked while the winner's HTTP was blocked; "
                f"probe observation is best-effort; "
                f"blockers={list(blockers)} error={exc}"
            )


async def task_row_unlocked_strict(factory, task_id, *, label):
    """The task row must be lockable NOWAIT while the winner's HTTP is blocked.

    A NOWAIT failure is a hard failure: after the failed attempt the probe
    transaction has ended, so pg_blocking_pids evidence is only a best-effort
    snapshot — an unknown (or even heartbeat-shaped) locker is never excused
    here. "lockable later" would never prove "not held across HTTP".
    """
    async with factory() as session:
        backend = await session.scalar(text("SELECT pg_backend_pid()"))
        try:
            await session.scalar(
                select(AnalysisTask.id).where(AnalysisTask.id == task_id)
                .with_for_update(nowait=True, key_share=True)
            )
            await session.rollback()
            return
        except OperationalError as exc:
            async with factory() as observer:
                activity = list(await observer.execute(text(
                    "SELECT pid, wait_event_type, state, left(query, 160) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0"
                )))
            pytest.fail(
                f"{label} task row was locked while the winner's HTTP was blocked; "
                f"probe={backend} lock-holders-now={list(activity)} error={exc}"
            )


async def prepare_two_matching_tasks(fixture_case, monkeypatch):
    """Two distinct pending match tasks for the case fixture's student owner."""
    with monkeypatch.context() as parsing:
        parsing.setattr(FastAPIBackgroundTaskRunner, "submit", ORIGINAL_BACKGROUND_SUBMIT)
        parsing.setattr(settings, "ai_external_enabled", False)
        resume, _project, version = await upload_materials(fixture_case.student)
    task_ids = []
    for _number in range(2):
        job = await create_job(fixture_case.hr)
        accepted = await fixture_case.student.post("/api/v1/matches", json={
            "jobId": job["id"],
            "resumeVersionId": resume["versionId"],
            "projectVersionIds": [version["versionId"]],
            "externalAiConsent": True,
        })
        assert accepted.status_code == 202, accepted.text
        task_ids.append(UUID(accepted.json()["data"]["taskId"]))
    async with fixture_case.factory() as session:
        tasks = {row.id: row for row in await session.scalars(
            select(AnalysisTask).where(AnalysisTask.id.in_(task_ids))
        )}
        owners = {row.created_by for row in tasks.values()}
        assert len(tasks) == 2 and len(owners) == 1
        assert all(row.status == TaskStatus.PENDING for row in tasks.values())
        student = await session.scalar(select(User).where(
            User.id == owners.pop(), User.role == UserRole.STUDENT
        ))
        assert student is not None
        return task_ids, student.id


async def build_second_verification_task(fixture_case):
    """A second application for the same job/HR, cloned from the first report.

    Items (requirementIds and synthetic citation ids) stay identical to the
    fixture_case snapshot, so one model answer validates for either winner; the
    empty materials list makes the binding cacheKey — and the task — distinct.
    """
    second = AsyncClient(transport=ASGITransport(app=fixture_case.app), base_url="http://test")
    try:
        user = await register(
            second, f"race-second-{uuid4().hex[:8]}@example.com", "student"
        )
        async with fixture_case.factory() as session:
            profile = await session.scalar(select(StudentProfile).where(
                StudentProfile.user_id == UUID(user["id"])
            ))
            source = await session.get(MatchReport, fixture_case.report_id)
            source_items = list(await session.scalars(select(MatchItem).where(
                MatchItem.report_id == source.id
            )))
            task = AnalysisTask(
                created_by=UUID(user["id"]),
                task_type="job_match",
                status=TaskStatus.COMPLETED,
            )
            session.add(task)
            await session.flush()
            report = MatchReport(
                analysis_task_id=task.id,
                job_id=source.job_id,
                candidate_ref=str(profile.id),
                summary=source.summary,
                overall_score=source.overall_score,
                job_snapshot=deepcopy(source.job_snapshot),
                materials_snapshot=[],
            )
            session.add(report)
            await session.flush()
            for item in source_items:
                session.add(MatchItem(
                    report_id=report.id,
                    requirement_id=item.requirement_id,
                    rule_base_score=item.rule_base_score,
                    weight=item.weight,
                    final_score=item.final_score,
                    verdict=item.verdict,
                    explanation=item.explanation,
                    formula_version=item.formula_version,
                    evidence_snapshot=deepcopy(item.evidence_snapshot),
                ))
            await session.commit()
            report_id = report.id
        submitted = await second.post(
            "/api/v1/applications", json={"reportId": str(report_id), "shareConsent": True}
        )
        assert submitted.status_code == 201, submitted.text
        application_id = submitted.json()["data"]["id"]
        opened = await fixture_case.hr.post(f"/api/v1/applications/{application_id}/view")
        assert opened.status_code == 200, opened.text
        snapshot = opened.json()["data"]["report"]
        snapshot["items"].sort(
            key=lambda value: {"Excel": 0, "SQL": 1, "Python": 2}[value["skill"]]
        )
        async with fixture_case.factory() as session:
            application = await session.get(Application, UUID(application_id))
            application.report_snapshot = deepcopy(snapshot)
            await session.commit()
        created = await fixture_case.hr.post(
            f"/api/v1/applications/{application_id}/verification",
            json={"externalAiConsent": True},
        )
        assert created.status_code == 202, created.text
        task_view = created.json()["data"]
        assert task_view["reused"] is False
        return UUID(task_view["taskId"]), application_id
    finally:
        await second.aclose()


async def race_state(factory, owner_id, task_ids):
    async with factory() as session:
        reservations = list(await session.scalars(select(AiBudgetReservation).where(
            AiBudgetReservation.created_by == owner_id,
        )))
        attempts = list(await session.scalars(select(AiRequestAttempt).where(
            AiRequestAttempt.analysis_task_id.in_(task_ids),
        )))
        ledger = list(await session.scalars(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id.in_(task_ids),
        )))
        tasks = {row.id: row for row in await session.scalars(select(AnalysisTask).where(
            AnalysisTask.id.in_(task_ids),
        ))}
    return reservations, attempts, ledger, tasks


async def assert_mid_block_invariants(fixture_case, owner_id, task_ids, *, label):
    reservations, attempts, ledger, tasks = await race_state(
        fixture_case.factory, owner_id, task_ids
    )
    assert len(reservations) == 1, f"{label}: exactly one hold during winner HTTP"
    hold = reservations[0]
    assert hold.state == "held"
    assert hold.actual_input_tokens is None and hold.actual_output_tokens is None
    assert len(attempts) == 1 and attempts[0].state == "in_flight"
    assert attempts[0].send_intent_at is not None and attempts[0].response_digest is None
    assert ledger == [], f"{label}: no ledger row may exist before the receipt"
    winner_task = hold.analysis_task_id
    loser_task = next(task for task in task_ids if task != winner_task)
    assert tasks[winner_task].status == TaskStatus.RUNNING
    return winner_task, loser_task


async def assert_no_locks_across_http(fixture_case, owner_id, task_ids):
    await strict_nowait_unlocked(fixture_case.factory, (
        select(User.id).where(User.id == owner_id)
        .with_for_update(nowait=True, key_share=True)
    ), label=f"user {owner_id}")
    await strict_nowait_unlocked(fixture_case.factory, (
        select(AiDailyBudget.id).where(AiDailyBudget.created_by == owner_id)
        .with_for_update(nowait=True)
    ), label=f"daily budget of {owner_id}")
    for task_id in task_ids:
        await task_row_unlocked_strict(
            fixture_case.factory, task_id, label=f"task {task_id}"
        )


async def assert_settled_exactly_once(
    fixture_case, owner_id, winner_task, *, cache_tokens, http_calls,
):
    """Per physical receipt: settled once, one ledger row, no duplicates.

    The matching chain may legitimately run an extra planning step (its
    eligibility depends on rule-analysis output), so the winner can hold
    several attempts — every one of them must still settle exactly once with
    the trusted actuals and book exactly one ledger row, and re-running the
    settlement path must write nothing further.
    """
    async with fixture_case.factory() as session:
        attempts = list(await session.scalars(select(AiRequestAttempt).where(
            AiRequestAttempt.analysis_task_id == winner_task,
        ).order_by(AiRequestAttempt.physical_sequence)))
        assert len(attempts) == http_calls >= 1, "every physical HTTP must have exactly one attempt"
        reservations = list(await session.scalars(select(AiBudgetReservation).where(
            AiBudgetReservation.created_by == owner_id,
        )))
        ledger = list(await session.scalars(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id == winner_task,
        )))
    assert all(row.state == "booked" for row in attempts)
    assert all(
        (row.usage_input_tokens, row.usage_output_tokens) == SYNTHETIC_USAGE
        for row in attempts
    )
    assert {row.analysis_task_id for row in reservations} == {winner_task}, (
        "the rejected chain must leave no reservation"
    )
    assert len(reservations) == len(attempts)
    by_attempt = {row.attempt_id: row for row in reservations}
    assert len(by_attempt) == len(reservations)
    for row in attempts:
        hold = by_attempt[row.id]
        assert hold.state == "settled" and hold.settled_at is not None
        assert (hold.actual_input_tokens, hold.actual_output_tokens) == SYNTHETIC_USAGE
    assert len(ledger) == len(attempts)
    assert {row.attempt_id for row in ledger} == {row.id for row in attempts}
    for row in ledger:
        assert (row.input_tokens, row.output_tokens, row.cache_hit_tokens) == (
            SYNTHETIC_USAGE[0], SYNTHETIC_USAGE[1], cache_tokens
        )
    # Re-running the winner's own settlement path must write nothing further.
    reference = attempts[0]
    context = AttemptContext(
        winner_task, owner_id, reference.run_token, reference.step,
        reference.provider, reference.model,
    )
    service = AttemptService(fixture_case.factory, context, budget=SharedBudgetService())
    assert await service.reconcile() == 0
    assert await service.reconcile() == 0
    async with fixture_case.factory() as session:
        ledger_again = list(await session.scalars(select(AiUsageLog).where(
            AiUsageLog.analysis_task_id == winner_task,
        )))
        settled_again = list(await session.scalars(select(AiBudgetReservation).where(
            AiBudgetReservation.created_by == owner_id,
        )))
    assert len(ledger_again) == len(attempts)
    assert all(
        (row.actual_input_tokens, row.actual_output_tokens) == SYNTHETIC_USAGE
        for row in settled_again
    )


def configure_race_settings(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_report_limit", 1)
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr(settings, "semantic_retrieval_enabled", False)
    # The global model gate defaults to one concurrent call, which would
    # serialize the two chains before admission and hide the race. Widen it
    # through the real setting (the lazy gate rebuilds from it on mismatch);
    # budget admission itself is never replaced.
    monkeypatch.setattr(settings, "ai_model_concurrency", 2)
    monkeypatch.setattr("app.agents.evidence_workflow._MODEL_SEMAPHORE", None)
    monkeypatch.setattr("app.agents.evidence_workflow._MODEL_SEMAPHORE_SIZE", None)
    rebuilt = evidence_workflow._model_semaphore()
    assert evidence_workflow._MODEL_SEMAPHORE_SIZE == 2
    assert rebuilt._value == 2, "the racing chains need two real gate slots"


async def wait_for_loser_rejection(chains):
    done, _pending = await asyncio.wait(
        chains, timeout=CHAIN_TIMEOUT_SECONDS, return_when=asyncio.FIRST_COMPLETED,
    )
    assert done, "the rejected chain must finish while the winner blocks in HTTP"
    finished = next(iter(done))
    exception = finished.exception() if finished.done() and not finished.cancelled() else None
    assert exception is None, f"the rejected chain crashed instead of degrading: {exception!r}"


async def test_matching_entry_same_owner_dual_task_last_slot_race(
    case, monkeypatch,  # noqa: F811
):
    await require_postgres(case)
    configure_race_settings(monkeypatch)
    task_ids, student_id = await prepare_two_matching_tasks(case, monkeypatch)
    async with case.factory() as session:
        digest_before = verification._digest((await session.get(
            Application, UUID(case.application_id)
        )).report_snapshot)

    gate = HttpGate(lambda request: valid_response(request, inputs=123, outputs=45))
    monkeypatch.setattr(
        "app.agents.evidence_workflow.get_ai_provider", lambda: gate.provider()
    )
    harness = LastSlotRace(task_ids)
    harness.install(monkeypatch)
    chains = [
        asyncio.create_task(analysis_service.execute_match_task(task_id))
        for task_id in task_ids
    ]
    try:
        await asyncio.wait_for(harness.overlap.wait(), CHAIN_TIMEOUT_SECONDS)
        await asyncio.wait_for(gate.entered.wait(), CHAIN_TIMEOUT_SECONDS)
        await wait_for_loser_rejection(chains)
        winner_task, loser_task = await assert_mid_block_invariants(
            case, student_id, task_ids, label="matching",
        )
        winner_chain = chains[task_ids.index(winner_task)]
        assert not winner_chain.done()
        async with case.factory() as session:
            stored = await session.get(AnalysisTask, loser_task)
            assert stored.status == TaskStatus.COMPLETED
            report = await session.scalar(select(MatchReport).where(
                MatchReport.analysis_task_id == loser_task,
            ))
            assert report is not None, "rejected chain degrades to a rule report"
            metadata = report.analysis_metadata
            assert metadata["mode"] == "rules" and metadata["fallbackUsed"] is True
            assert metadata["requestCount"] == 0
            print_race_evidence("matching-loser", {
                "taskId": str(loser_task),
                "fallbackReason": metadata["fallbackReason"],
                "failureStage": metadata["failureStage"],
                "skippedReason": metadata["skippedReason"],
            })
        await assert_no_locks_across_http(case, student_id, task_ids)
        assert gate.calls == 1
        gate.release.set()
        await asyncio.wait_for(winner_chain, CHAIN_TIMEOUT_SECONDS)
    finally:
        gate.release.set()
        for chain in chains:
            if not chain.done():
                chain.cancel()
                await asyncio.gather(chain, return_exceptions=True)
    print_race_evidence("matching", {
        "httpCalls": gate.calls, "httpSteps": gate.steps, **harness.report(),
    })

    async with case.factory() as session:
        winner_row = await session.get(AnalysisTask, winner_task)
        assert winner_row.status == TaskStatus.COMPLETED
        report = await session.scalar(select(MatchReport).where(
            MatchReport.analysis_task_id == winner_task,
        ))
        assert report.analysis_metadata["mode"] == "ai_evidence"
        assert report.analysis_metadata["fallbackUsed"] is False
        summary = report.analysis_metadata["attemptSummary"]
        assert summary["trustedReceiptCount"] == gate.calls and summary["usageBooked"] is True
        digest_after = verification._digest((await session.get(
            Application, UUID(case.application_id)
        )).report_snapshot)
    await assert_settled_exactly_once(
        case, student_id, winner_task, cache_tokens=0, http_calls=gate.calls,
    )
    assert digest_after == digest_before
    _reservations, attempts, ledger, _tasks = await race_state(
        case.factory, student_id, task_ids
    )
    winner_attempts, loser_attempts = split(attempts, winner_task)
    assert winner_attempts and loser_attempts == []
    assert {row.analysis_task_id for row in ledger} == {winner_task}


def split(rows, winner_task):
    winner = [row for row in rows if row.analysis_task_id == winner_task]
    loser = [row for row in rows if row.analysis_task_id != winner_task]
    return winner, loser


async def test_verification_entry_same_owner_dual_task_last_slot_race(
    case, monkeypatch,  # noqa: F811
):
    await require_postgres(case)
    configure_race_settings(monkeypatch)
    first = await case.start()
    second_task, second_application = await build_second_verification_task(case)
    task_ids = [UUID(first["taskId"]), second_task]
    application_ids = [case.application_id, second_application]
    async with case.factory() as session:
        tasks = {row.id: row for row in await session.scalars(
            select(AnalysisTask).where(AnalysisTask.id.in_(task_ids))
        )}
        owners = {row.created_by for row in tasks.values()}
        assert len(tasks) == 2 and len(owners) == 1
        assert all(row.status == TaskStatus.PENDING for row in tasks.values())
        hr_id = owners.pop()
        hr = await session.get(User, hr_id)
        assert hr.role == UserRole.ENTERPRISE
        digests_before = {
            application_id: verification._digest((await session.get(
                Application, UUID(application_id)
            )).report_snapshot)
            for application_id in application_ids
        }

    gate = HttpGate(lambda request: completion(model_answer(case.snapshot)))
    monkeypatch.setattr(verification, "get_ai_provider", lambda: gate.provider())
    harness = LastSlotRace(task_ids)
    harness.install(monkeypatch)
    chains = [
        asyncio.create_task(verification.execute_application_verification_task(
            task_id, session_factory=case.factory,
        ))
        for task_id in task_ids
    ]
    try:
        await asyncio.wait_for(harness.overlap.wait(), CHAIN_TIMEOUT_SECONDS)
        await asyncio.wait_for(gate.entered.wait(), CHAIN_TIMEOUT_SECONDS)
        await wait_for_loser_rejection(chains)
        winner_task, loser_task = await assert_mid_block_invariants(
            case, hr_id, task_ids, label="verification",
        )
        winner_chain = chains[task_ids.index(winner_task)]
        assert not winner_chain.done()
        loser_application = application_ids[task_ids.index(loser_task)]
        loser_view = (await case.hr.get(
            f"/api/v1/applications/{loser_application}/verification/{loser_task}"
        )).json()["data"]
        assert loser_view["status"] == "failed"
        assert loser_view["failureKind"] == "daily_report_limit"
        assert loser_view["analysis"] is None and loser_view["usage"] is None
        await assert_no_locks_across_http(case, hr_id, task_ids)
        assert gate.calls == 1
        gate.release.set()
        await asyncio.wait_for(winner_chain, CHAIN_TIMEOUT_SECONDS)
    finally:
        gate.release.set()
        for chain in chains:
            if not chain.done():
                chain.cancel()
                await asyncio.gather(chain, return_exceptions=True)
    print_race_evidence("verification", {
        "httpCalls": gate.calls, "httpSteps": gate.steps, **harness.report(),
    })

    winner_application = application_ids[task_ids.index(winner_task)]
    winner_view = (await case.hr.get(
        f"/api/v1/applications/{winner_application}/verification/{winner_task}"
    )).json()["data"]
    assert winner_view["status"] == "completed"
    assert winner_view["aiStatus"] == "validated" and winner_view["analysis"]
    assert winner_view["usage"]["inputTokens"] == SYNTHETIC_USAGE[0]
    async with case.factory() as session:
        digests_after = {
            application_id: verification._digest((await session.get(
                Application, UUID(application_id)
            )).report_snapshot)
            for application_id in application_ids
        }
    assert digests_after == digests_before
    await assert_settled_exactly_once(
        case, hr_id, winner_task, cache_tokens=17, http_calls=gate.calls,
    )


async def test_cross_role_owner_isolation_and_entry_role_walls(
    case, monkeypatch,  # noqa: F811
):
    """Different roles never share the last slot; neither can enter the other's chain.

    The student fills their own single daily slot through the real matching
    entry; the HR verification entry then still admits the HR's own task in
    the same schema and day, each capacity view contains only its owner's
    task, and the API role walls reject the cross-role requesters outright.
    """
    await require_postgres(case)
    configure_race_settings(monkeypatch)
    task_ids, student_id = await prepare_two_matching_tasks(case, monkeypatch)

    calls = []

    def handler(request):
        calls.append(request)
        return valid_response(request, inputs=123, outputs=45)

    provider = synthetic_provider(httpx.MockTransport(handler))
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)
    await asyncio.wait_for(
        analysis_service.execute_match_task(task_ids[0]), CHAIN_TIMEOUT_SECONDS
    )
    assert calls, "the matching entry must reach the model at least once"
    started = await case.start()
    hr_task = UUID(started["taskId"])
    async with case.factory() as session:
        hr_id = (await session.get(AnalysisTask, hr_task)).created_by
        assert hr_id != student_id
    verification_calls = []

    def verification_handler(request):
        verification_calls.append(request)
        return completion(model_answer(case.snapshot))

    verification_provider = synthetic_provider(
        httpx.MockTransport(verification_handler)
    )
    monkeypatch.setattr(
        verification, "get_ai_provider", lambda: verification_provider
    )
    await asyncio.wait_for(verification.execute_application_verification_task(
        hr_task, session_factory=case.factory,
    ), CHAIN_TIMEOUT_SECONDS)
    assert len(verification_calls) == 1

    # Role walls: the same owner cannot legally span both production entries.
    student_attempt = await case.student.post(
        case.path, json={"externalAiConsent": True}
    )
    assert student_attempt.status_code == 404
    hr_match = await case.hr.post("/api/v1/matches", json={
        "jobId": case.job["id"],
        "resumeVersionId": uuid4().hex,
        "projectVersionIds": [],
        "externalAiConsent": True,
    })
    assert hr_match.status_code == 403, hr_match.text

    budget = SharedBudgetService()
    today = budget.today()
    async with case.factory() as session:
        student_capacity = await budget.capacity(session, student_id, day=today)
        hr_capacity = await budget.capacity(session, hr_id, day=today)
        daily_rows = list(await session.scalars(select(AiDailyBudget).where(
            AiDailyBudget.budget_day == today,
        )))
    assert student_capacity.task_ids == frozenset(task_ids[:1])
    assert hr_capacity.task_ids == frozenset([hr_task])
    assert not (student_capacity.task_ids & hr_capacity.task_ids)
    assert len(daily_rows) == 2
    assert {row.created_by for row in daily_rows} == {student_id, hr_id}
    await assert_settled_exactly_once(
        case, student_id, task_ids[0], cache_tokens=0, http_calls=len(calls),
    )
    await assert_settled_exactly_once(
        case, hr_id, hr_task, cache_tokens=17, http_calls=len(verification_calls),
    )


async def test_offline_fixture_contract_dual_pending_and_single_chain_booking(
    case, monkeypatch,  # noqa: F811
):
    """SQLite scope: fixture construction and one chain's booking contract only.

    SQLite cannot prove PostgreSQL row-lock concurrency (the race tests above
    skip without CAREERPROOF_TEST_DATABASE_URL); this contract keeps the
    preparation honest on any database.
    """
    task_ids, student_id = await prepare_two_matching_tasks(case, monkeypatch)
    assert len(task_ids) == 2 and task_ids[0] != task_ids[1]

    calls = []

    steps = []

    def handler(request):
        calls.append(request)
        steps.append(classify_request(request))
        return valid_response(request, inputs=123, outputs=45)

    provider = synthetic_provider(httpx.MockTransport(handler))
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr(settings, "semantic_retrieval_enabled", False)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)
    await asyncio.wait_for(
        analysis_service.execute_match_task(task_ids[0]), CHAIN_TIMEOUT_SECONDS
    )
    print("RACE-EVIDENCE offline-single-chain " + json.dumps(
        {"httpCalls": len(calls), "httpSteps": steps}
    ))
    assert calls, "the executed chain must reach the model at least once"

    async with case.factory() as session:
        executed = await session.get(AnalysisTask, task_ids[0])
        untouched = await session.get(AnalysisTask, task_ids[1])
        assert executed.status == TaskStatus.COMPLETED
        assert untouched.status == TaskStatus.PENDING and untouched.run_token is None
        attempts = list(await session.scalars(select(AiRequestAttempt).where(
            AiRequestAttempt.analysis_task_id.in_(task_ids),
        )))
        reservations = list(await session.scalars(select(AiBudgetReservation).where(
            AiBudgetReservation.created_by == student_id,
        )))
        assert {row.analysis_task_id for row in attempts} == {task_ids[0]}
        assert all(row.state == "booked" for row in attempts)
        assert {row.analysis_task_id for row in reservations} == {task_ids[0]}
    await assert_settled_exactly_once(
        case, student_id, task_ids[0], cache_tokens=0, http_calls=len(calls),
    )
