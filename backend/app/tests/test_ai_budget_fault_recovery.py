"""Budget transaction commit-fault recovery at the real SQLAlchemy boundary.

Reuses the real DeepSeekProvider wire path over httpx.MockTransport and the
isolated ``budget_data`` fixture (temp SQLite, or a disposable cp_test_*
PostgreSQL schema when CAREERPROOF_TEST_DATABASE_URL is set; public schema is
never targeted). No real model, no network, no production rows.

Injection semantics, stated per task card: ``CommitFaultFactory`` interrupts
the Nth real ``session.commit()`` call. ``mode="before"`` rolls the open
transaction back BEFORE any COMMIT statement runs, so the outcome is
definitely "not committed" — this is NOT a claim about dropped-connection
ambiguity. ``mode="after"`` lets the real COMMIT apply durably and only then
raises, modeling the "commit actually applied" branch of an ambiguous outcome
(a connection dropped after the server applied COMMIT). The "before" mode
checks a definitely rolled-back outcome; neither mode injects a real driver
disconnect or proves how an unknown network outcome is reported.

prepare_for_send, mark_intent, receive and book_one each commit exactly one
transaction per physical attempt, so a commit ordinal identifies the boundary:

1. prepare_for_send — attempt row + budget hold commit atomically together;
2. mark_intent      — in_flight intent commit;
3. receive          — trusted receipt + budget settlement commit;
4. book_one         — exactly-once ledger booking commit.
"""

import json
from datetime import date

import pytest
from sqlalchemy import select

from app.agents.provider import ProviderReceiptPersistenceError
from app.models.ai_budget import AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog
from app.services.ai_budget import BudgetPolicy, SharedBudgetService
from app.services.ai_request_attempts import DurableRequestObserver
from app.tests.test_ai_budget_attempt_integration import (
    request_for,
    response,
    service_for,
)
from app.tests.test_ai_shared_budget_service import NOW
from app.tests.test_ai_shared_budget_service import budget_data as budget_data
from app.tests.test_b08_usage_accounting import reap
from app.tests.test_durable_matching import durable_db as durable_db
from app.tests.test_durable_matching import synthetic_provider

DAY = date(2026, 10, 7)


class CommitFault(RuntimeError):
    """Raised by the injection at the real SQLAlchemy session.commit() boundary."""


class _FaultingSession:
    """Delegates everything to the wrapped AsyncSession except commit()."""

    def __init__(self, session, controller):
        self._proxied = session
        self._controller = controller

    def __getattr__(self, name):
        return getattr(self._proxied, name)

    async def __aenter__(self):
        await self._proxied.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return await self._proxied.__aexit__(exc_type, exc, tb)

    async def commit(self):
        if not self._controller.next_commit_fails():
            return await self._proxied.commit()
        if self._controller.mode == "before":
            # Definitely not committed: the transaction is discarded before
            # any COMMIT statement is sent to the server.
            await self._proxied.rollback()
            self._controller.raised += 1
            raise CommitFault("injected before COMMIT: transaction rolled back")
        # Ambiguous branch where COMMIT actually applied: the database keeps
        # the transaction, then the caller is told the commit failed.
        await self._proxied.commit()
        self._controller.raised += 1
        raise CommitFault("injected after COMMIT applied: outcome ambiguous to caller")


class CommitFaultFactory:
    """Sessionmaker wrapper interrupting one chosen session.commit() ordinal."""

    def __init__(self, factory, *, fail_on_commit, mode):
        if mode not in ("before", "after"):
            raise ValueError("mode must be 'before' or 'after'")
        self._factory = factory
        self.fail_on_commit = fail_on_commit
        self.mode = mode
        self.commits = 0
        self.raised = 0

    def next_commit_fails(self):
        self.commits += 1
        return self.commits == self.fail_on_commit

    def __call__(self):
        return _FaultingSession(self._factory(), self)


async def persisted_rows(factory, task):
    async with factory() as session:
        attempts = list(
            await session.scalars(
                select(AiRequestAttempt).where(AiRequestAttempt.analysis_task_id == task)
            )
        )
        holds = list(
            await session.scalars(
                select(AiBudgetReservation).where(
                    AiBudgetReservation.analysis_task_id == task
                )
            )
        )
        ledger = list(
            await session.scalars(
                select(AiUsageLog).where(AiUsageLog.analysis_task_id == task)
            )
        )
        return attempts, holds, ledger


async def capacity_on(factory, budget, owner, day=DAY):
    async with factory() as session:
        return await budget.capacity(session, owner, day=day)


async def wire(data, *, fail_on_commit, mode):
    factory, _runtime, owner, task, _other = data
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return response(request)

    provider = synthetic_provider(handler)
    faults = CommitFaultFactory(factory, fail_on_commit=fail_on_commit, mode=mode)
    budget = SharedBudgetService(clock=lambda: NOW, policy=BudgetPolicy(1, 10000, 300, 10000, 300))
    service = await service_for(faults, owner, task, provider, budget)
    provider.durable_observer = DurableRequestObserver(service)
    return factory, budget, faults, owner, task, provider, service, calls


@pytest.mark.parametrize("mode", ["before", "after"])
async def test_prepare_commit_fault_sends_no_http_and_keeps_rows_atomic(
    budget_data, mode  # noqa: F811 - imported fixture
):
    """Boundary 1: prepare's commit (#1) fails — no HTTP, attempt+hold stay atomic."""
    factory, budget, faults, owner, task, provider, _service, calls = await wire(
        budget_data, fail_on_commit=1, mode=mode
    )
    # before_send runs outside the provider retry catch: its failure propagates
    # immediately and no POST is ever issued.
    with pytest.raises(CommitFault):
        await provider._completion(request_for(provider))
    assert calls == []
    assert faults.raised == 1
    attempts, holds, _ledger = await persisted_rows(factory, task)
    usage = await capacity_on(factory, budget, owner)
    if mode == "before":
        # The transaction was discarded before COMMIT: neither the attempt row
        # nor its budget reservation exists, and no capacity is held.
        assert attempts == [] and holds == []
        assert (usage.inputs, usage.outputs, len(usage.task_ids)) == (0, 0, 0)
    else:
        # Ambiguous branch where the prepare COMMIT applied: the caller saw a
        # failure, but the not_sent attempt and its held reservation are in the
        # database — capacity conservatively stays held, never treated as free.
        assert len(attempts) == len(holds) == 1
        attempt, hold = attempts[0], holds[0]
        assert attempt.state == "not_sent" and attempt.send_intent_at is None
        assert attempt.ended_at is None
        assert hold.state == "held" and hold.settled_at is None
        assert hold.output_bound == attempt.max_output_tokens == 300
        assert (usage.known_inputs, usage.known_outputs) == (0, 0)
        assert (usage.held_inputs, usage.held_outputs, usage.unknown_count) == (
            attempt.estimated_input_tokens,
            300,
            1,
        )
        recovery = await service_for(factory, owner, task, provider, budget)
        await reap(factory, str(task))
        assert await recovery.reconcile() == 0
        assert await recovery.reconcile() == 0
        recovered, released, ledger = await persisted_rows(factory, task)
        assert recovered[0].state == "not_sent" and recovered[0].ended_at is not None
        assert released[0].state == "released" and ledger == []
        capacity = await capacity_on(factory, budget, owner)
        assert (capacity.inputs, capacity.outputs, len(capacity.task_ids)) == (0, 0, 0)
        assert calls == []


@pytest.mark.parametrize("mode", ["before", "after"])
async def test_intent_commit_fault_never_sends_and_recovers_from_durable_facts(
    budget_data, mode  # noqa: F811 - imported fixture
):
    factory, budget, faults, owner, task, provider, _service, calls = await wire(
        budget_data, fail_on_commit=2, mode=mode
    )
    with pytest.raises(CommitFault):
        await provider._completion(request_for(provider))
    assert faults.raised == 1 and calls == []
    recovery = await service_for(factory, owner, task, provider, budget)
    await reap(factory, str(task))
    assert await recovery.reconcile() == 0
    assert await recovery.reconcile() == 0
    attempts, holds, ledger = await persisted_rows(factory, task)
    assert len(attempts) == len(holds) == 1 and ledger == []
    attempt, hold = attempts[0], holds[0]
    assert attempt.usage_input_tokens is None and hold.actual_input_tokens is None
    assert attempt.ended_at is not None
    capacity = await capacity_on(factory, budget, owner)
    if mode == "before":
        assert attempt.state == "not_sent" and attempt.send_intent_at is None
        assert hold.state == "released"
        assert (capacity.inputs, capacity.outputs, len(capacity.task_ids)) == (0, 0, 0)
    else:
        # Recovery cannot use this test's private HTTP counter as a receipt.
        # Persisted intent means a send was possible, so the upper bound stays.
        assert attempt.state == "usage_unknown" and attempt.send_intent_at is not None
        assert hold.state == "held"
        assert (capacity.known_inputs, capacity.known_outputs) == (0, 0)
        assert (capacity.held_inputs, capacity.held_outputs, capacity.unknown_count) == (
            attempt.estimated_input_tokens, 300, 1,
        )
    assert calls == []


@pytest.mark.parametrize("mode", ["before", "after"])
async def test_receipt_commit_fault_never_fabricates_trusted_cost(
    budget_data, mode  # noqa: F811 - imported fixture
):
    """Boundary 2: receive's commit (#3) fails — no fabricated trusted cost."""
    factory, budget, faults, owner, task, provider, _service, calls = await wire(
        budget_data, fail_on_commit=3, mode=mode
    )
    # The receipt persistence failure is not a provider send failure: it must
    # surface as ProviderReceiptPersistenceError without another POST.
    with pytest.raises(ProviderReceiptPersistenceError) as excinfo:
        await provider._completion(request_for(provider))
    assert isinstance(excinfo.value.__cause__, CommitFault)
    assert faults.raised == 1
    assert len(calls) == 1
    attempts, holds, ledger = await persisted_rows(factory, task)
    assert len(attempts) == len(holds) == 1
    attempt, hold = attempts[0], holds[0]
    usage = await capacity_on(factory, budget, owner)
    if mode == "before":
        # The receipt transaction was discarded before COMMIT: the physical
        # response did not become a trusted cost, and the committed intent and
        # hold stay conservative for recovery.
        assert attempt.state == "in_flight" and attempt.ended_at is None
        assert attempt.usage_raw == {} and attempt.response_digest is None
        assert attempt.usage_input_tokens is None and attempt.usage_output_tokens is None
        assert hold.state == "held" and hold.settled_at is None
        assert hold.actual_input_tokens is None and hold.actual_output_tokens is None
        assert ledger == []
        assert (usage.known_inputs, usage.known_outputs) == (0, 0)
        assert (usage.held_inputs, usage.held_outputs, usage.unknown_count) == (
            attempt.estimated_input_tokens,
            300,
            1,
        )
        # Conservative recovery: the still-in-flight attempt closes as
        # usage_unknown; its held capacity is neither released nor settled.
        await provider.durable_observer.on_failure(attempt.id, "provider_network")
        closed, closed_holds, _closed_ledger = await persisted_rows(factory, task)
        assert closed[0].state == "usage_unknown" and closed[0].ended_at is not None
        assert closed[0].reason == "provider_network"
        assert closed[0].usage_input_tokens is None and closed[0].usage_raw == {}
        assert closed_holds[0].state == "held"
        after = await capacity_on(factory, budget, owner)
        assert (after.known_inputs, after.known_outputs) == (0, 0)
        assert (after.held_inputs, after.held_outputs, after.unknown_count) == (
            attempt.estimated_input_tokens,
            300,
            1,
        )
    else:
        # Ambiguous branch where the receipt COMMIT applied: the trusted
        # receipt is durable with its settled actuals. The late failure the
        # caller saw must neither erase the receipt nor double the cost, and a
        # late failure callback must not relabel it as unknown.
        assert attempt.state == "received_unbooked" and attempt.receipt_at is not None
        assert (attempt.usage_input_tokens, attempt.usage_output_tokens) == (12, 7)
        assert attempt.response_digest is not None
        assert hold.state == "settled" and hold.settled_at is not None
        assert (hold.actual_input_tokens, hold.actual_output_tokens) == (12, 7)
        assert ledger == []
        assert (usage.known_inputs, usage.known_outputs) == (12, 7)
        assert (usage.held_inputs, usage.held_outputs, usage.unknown_count) == (0, 0, 0)
        await provider.durable_observer.on_failure(attempt.id, "provider_network")
        kept, _kept_holds, _kept_ledger = await persisted_rows(factory, task)
        assert kept[0].state == "received_unbooked"
        assert (kept[0].usage_input_tokens, kept[0].usage_output_tokens) == (12, 7)
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["before", "after"])
async def test_book_commit_fault_recovers_exactly_once_without_http(
    budget_data, mode  # noqa: F811 - imported fixture
):
    """Boundary 3: book_one's commit (#4) fails — exactly-once ledger recovery."""
    factory, budget, faults, owner, task, provider, service, calls = await wire(
        budget_data, fail_on_commit=4, mode=mode
    )
    await provider._completion(request_for(provider))
    assert len(calls) == 1
    attempts, _holds, _ledger = await persisted_rows(factory, task)
    assert len(attempts) == 1 and attempts[0].state == "received_unbooked"
    attempt_id = attempts[0].id
    # The trusted receipt and its settled budget actuals were already durable
    # in the receipt transaction; the booking failure happens after them.
    with pytest.raises(CommitFault):
        await service.book_one(attempt_id)
    assert faults.raised == 1
    assert len(calls) == 1
    if mode == "before":
        faulted, faulted_holds, faulted_ledger = await persisted_rows(factory, task)
        assert faulted[0].state == "received_unbooked" and faulted[0].booked_at is None
        assert faulted_ledger == []
        usage = await capacity_on(factory, budget, owner)
        assert (usage.inputs, usage.outputs) == (12, 7)
        assert (usage.known_inputs, usage.known_outputs) == (12, 7)
        assert faulted_holds[0].state == "settled"
        assert (faulted_holds[0].actual_input_tokens, faulted_holds[0].actual_output_tokens) == (
            12,
            7,
        )
    else:
        faulted, faulted_holds, faulted_ledger = await persisted_rows(factory, task)
        # The booking COMMIT applied before the caller learned of the failure:
        # the ledger row and booked state already exist.
        assert faulted[0].state == "booked" and faulted[0].booked_at is not None
        assert len(faulted_ledger) == 1
        assert faulted_holds[0].state == "settled"
    # Recovery: an independent reconciliation finishes the booking without any
    # new provider HTTP, writes the ledger exactly once, and keeps the budget
    # actuals from the durable receipt.
    recovery = await service_for(factory, owner, task, provider, budget)
    assert await recovery.reconcile() == (1 if mode == "before" else 0)
    assert await recovery.reconcile() == 0
    assert len(calls) == 1
    attempts, holds, ledger = await persisted_rows(factory, task)
    assert len(ledger) == 1
    row = ledger[0]
    assert (row.input_tokens, row.output_tokens) == (12, 7)
    assert row.attempt_id == attempt_id and row.request_seq == 1
    assert attempts[0].state == "booked" and attempts[0].booked_at is not None
    assert holds[0].state == "settled"
    assert (holds[0].actual_input_tokens, holds[0].actual_output_tokens) == (12, 7)
    usage = await capacity_on(factory, budget, owner)
    assert (usage.inputs, usage.outputs) == (12, 7)
    assert (usage.known_inputs, usage.known_outputs) == (12, 7)
    assert (usage.held_inputs, usage.held_outputs, usage.unknown_count) == (0, 0, 0)
