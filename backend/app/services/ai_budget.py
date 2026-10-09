"""Database-backed daily capacity; provider receipts remain independent facts.

Call these methods inside the attempt's short transaction, after business
authorization and before its attempt lock. No method performs HTTP or commits.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.agents.attempt_receipts import parse_usage_receipt
from app.core.config import settings
from app.models.ai_budget import (
    AiBudgetAdjustment,
    AiBudgetCutover,
    AiBudgetReservation,
    AiDailyBudget,
)
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.enums import TaskStatus, UserRole
from app.models.identity import User

SHANGHAI = timezone(timedelta(hours=8))
GATE_ID = "shared_daily_v1"


class BudgetAdmissionError(RuntimeError):
    """A failed admission may not cause a physical HTTP retry."""


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    daily_reports: int
    daily_input: int
    daily_output: int
    report_input: int
    report_output: int

    @classmethod
    def current(cls):
        return cls(
            settings.ai_daily_report_limit,
            settings.ai_daily_input_token_limit,
            settings.ai_daily_output_token_limit,
            settings.ai_per_report_input_token_limit,
            settings.ai_per_report_output_token_limit,
        )


@dataclass(frozen=True, slots=True)
class Capacity:
    inputs: int
    outputs: int
    task_ids: frozenset[UUID]


def reservation_cost(row):
    if row.state == "released":
        return 0, 0
    if row.state == "settled":
        values = row.actual_input_tokens, row.actual_output_tokens
    elif row.state == "adjusted":
        values = row.adjusted_input_tokens, row.adjusted_output_tokens
    elif row.state == "held":
        values = row.input_bound, row.output_bound
    else:
        raise BudgetAdmissionError("invalid_persisted_reservation_state")
    if any(type(v) is not int or v < 0 for v in values):
        raise BudgetAdmissionError("invalid_persisted_capacity")
    return values


def approve_output(policy, daily, report, task_id, inputs, requested):
    if type(inputs) is not int or inputs < 0 or type(requested) is not int or requested < 1:
        raise BudgetAdmissionError("invalid_request_bounds")
    if task_id not in daily.task_ids and len(daily.task_ids) >= policy.daily_reports:
        raise BudgetAdmissionError("daily_report_limit")
    if daily.inputs + inputs > policy.daily_input:
        raise BudgetAdmissionError("daily_input_token_limit")
    if report.inputs + inputs > policy.report_input:
        raise BudgetAdmissionError("report_input_token_limit")
    grant = min(
        requested, policy.daily_output - daily.outputs, policy.report_output - report.outputs
    )
    if grant < 1:
        raise BudgetAdmissionError("output_token_limit")
    return grant


class SharedBudgetService:
    def __init__(self, *, clock=None, policy=None):
        self.clock = clock or (lambda: datetime.now(UTC))
        self.policy = policy or BudgetPolicy.current()

    def now(self):
        value = self.clock()
        if value.tzinfo is None:
            raise BudgetAdmissionError("server_clock_requires_timezone")
        return value.astimezone(UTC)

    def today(self):
        return self.now().astimezone(SHANGHAI).date()

    async def _administrator(self, session, actor_id):
        actor = await session.scalar(
            select(User)
            .where(
                User.id == actor_id,
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if actor is None:
            raise BudgetAdmissionError("active_administrator_required")

    async def activate(self, session, *, actor_id, reason):
        """Audit/drain/backfill before activation; never infer unknown legacy fees.

        Old external runs without physical provenance keep the gate closed.
        Caller must commit this transaction or roll back on any exception.
        """
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise BudgetAdmissionError("activation_audit_reason_required")
        await self._administrator(session, actor_id)
        insertion = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
        now = self.now()
        await session.execute(
            insertion(AiBudgetCutover)
            .values(
                id=GATE_ID,
                enabled=False,
                reason="",
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        gate = await session.scalar(
            select(AiBudgetCutover)
            .where(
                AiBudgetCutover.id == GATE_ID,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if gate.enabled:
            # Activation evidence cannot be overwritten by another caller.
            await self.assert_gate(session)
            return gate.inventory_digest
        tasks = list(await session.scalars(select(AnalysisTask)))
        modern_ids = set(await session.scalars(select(AiRequestAttempt.analysis_task_id)))
        for task in tasks:
            snapshot = task.input_snapshot or {}
            if snapshot.get("externalAiConsent") is not True:
                continue
            if task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
                raise BudgetAdmissionError("external_claims_must_drain_before_cutover")
            if task.id not in modern_ids or snapshot.get("usageAccountingMode") != "attempt_v1":
                # COMPLETED/FAILED and even a partial old aggregate ledger do
                # not prove the physical request inventory is complete.
                raise BudgetAdmissionError("legacy_external_run_requires_audit_gate_remains_closed")
        await self.backfill_pre_budget_attempts(session)
        attempts = list(
            await session.scalars(select(AiRequestAttempt).order_by(AiRequestAttempt.id))
        )
        reservations = list(await session.scalars(select(AiBudgetReservation)))
        holds = {row.attempt_id: row for row in reservations}
        inventory = []
        for attempt in attempts:
            hold = holds.get(attempt.id)
            if (
                hold is None
                or hold.created_by != attempt.created_by
                or hold.analysis_task_id != attempt.analysis_task_id
                or hold.run_token != attempt.run_token
            ):
                raise BudgetAdmissionError("cutover_inventory_identity_incomplete")
            if (
                hold.input_bound != attempt.estimated_input_tokens
                or hold.output_bound != attempt.max_output_tokens
            ):
                raise BudgetAdmissionError("cutover_capacity_bounds_conflict")
            if attempt.state != "not_sent" and (
                attempt.send_intent_at is None
                or attempt.sending_day is None
                or hold.reservation_day != attempt.sending_day
            ):
                raise BudgetAdmissionError("cutover_original_sending_day_missing")
            if attempt.state in {"received_unbooked", "booked"}:
                parsed = parse_usage_receipt({"usage": attempt.usage_raw})
                if (
                    not parsed.trusted
                    or hold.state != "settled"
                    or (
                        attempt.usage_input_tokens,
                        attempt.usage_output_tokens,
                        attempt.usage_cache_hit_tokens,
                    )
                    != (parsed.input_tokens, parsed.output_tokens, parsed.cache_hit_tokens)
                    or (hold.actual_input_tokens, hold.actual_output_tokens)
                    != (parsed.input_tokens, parsed.output_tokens)
                ):
                    raise BudgetAdmissionError("cutover_receipt_capacity_conflict")
            elif attempt.state in {"in_flight", "usage_unknown"}:
                if hold.state not in {"held", "adjusted"}:
                    raise BudgetAdmissionError("cutover_unknown_capacity_lost")
            elif attempt.state == "not_sent":
                if attempt.send_intent_at is not None or hold.state not in {"held", "released"}:
                    raise BudgetAdmissionError("cutover_unsent_capacity_invalid")
                if hold.state == "released" and attempt.ended_at is None:
                    raise BudgetAdmissionError("cutover_unsent_release_unproven")
            inventory.append(
                {
                    "id": str(attempt.id),
                    "owner": str(attempt.created_by),
                    "task": str(attempt.analysis_task_id),
                    "run": str(attempt.run_token),
                    "state": attempt.state,
                    "day": str(hold.reservation_day),
                    "source": hold.source,
                    "capacity": reservation_cost(hold),
                    "receiptDigest": attempt.response_digest,
                }
            )
        # Legacy ledgers remain immutable; including their identity in the audit
        # avoids treating a new empty budget table as an empty spending history.
        legacy = list(
            await session.execute(
                select(
                    AiUsageLog.id,
                    AiUsageLog.analysis_task_id,
                    AiUsageLog.created_at,
                    AiUsageLog.input_tokens,
                    AiUsageLog.output_tokens,
                )
                .where(AiUsageLog.attempt_id.is_(None))
                .order_by(AiUsageLog.id)
            )
        )
        payload = {"attempts": inventory, "legacy": [tuple(row) for row in legacy]}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        gate.enabled, gate.inventory_digest = True, digest
        gate.activated_by, gate.activated_at, gate.reason = actor_id, now, reason.strip()
        await session.flush()
        return digest

    async def adjust_unknown(
        self, session, *, actor_id, attempt_id, operation_id, reason, input_tokens, output_tokens
    ):
        """Append-only administrative capacity decision, never a usage receipt."""
        if (
            not isinstance(operation_id, str)
            or not operation_id.strip()
            or len(operation_id) > 100
            or not isinstance(reason, str)
            or not reason.strip()
            or len(reason) > 1000
            or any(type(v) is not int or v < 0 for v in (input_tokens, output_tokens))
        ):
            raise BudgetAdmissionError("invalid_capacity_adjustment")
        await self._administrator(session, actor_id)
        attempt, hold = await self.lock_attempt(session, attempt_id)
        existing = await session.scalar(
            select(AiBudgetAdjustment).where(
                AiBudgetAdjustment.operation_id == operation_id,
            )
        )
        if existing:
            if (
                existing.reservation_id != hold.id
                or existing.actor_id != actor_id
                or existing.reason != reason.strip()
                or (existing.after_input_tokens, existing.after_output_tokens)
                != (input_tokens, output_tokens)
            ):
                raise BudgetAdmissionError("adjustment_operation_conflict")
            return existing.id
        if attempt.state != "usage_unknown" or hold.state not in {"held", "adjusted"}:
            raise BudgetAdmissionError("only_unknown_capacity_may_be_adjusted")
        before_input, before_output = reservation_cost(hold)
        audit = AiBudgetAdjustment(
            operation_id=operation_id,
            reservation_id=hold.id,
            created_by=attempt.created_by,
            actor_id=actor_id,
            reason=reason.strip(),
            before_input_tokens=before_input,
            before_output_tokens=before_output,
            after_input_tokens=input_tokens,
            after_output_tokens=output_tokens,
        )
        session.add(audit)
        hold.state = "adjusted"
        hold.adjusted_input_tokens, hold.adjusted_output_tokens = input_tokens, output_tokens
        await session.flush()
        return audit.id

    async def assert_gate(self, session, *, exclude_attempt=None):
        gate = await session.scalar(
            select(AiBudgetCutover)
            .where(
                AiBudgetCutover.id == GATE_ID,
            )
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if not gate or not gate.enabled:
            raise BudgetAdmissionError("budget_cutover_not_enabled")
        if (
            not gate.activated_at
            or not gate.activated_by
            or not gate.reason.strip()
            or len(gate.inventory_digest or "") != 64
        ):
            raise BudgetAdmissionError("budget_cutover_evidence_missing")
        query = (
            select(AiRequestAttempt.id)
            .outerjoin(
                AiBudgetReservation,
                AiBudgetReservation.attempt_id == AiRequestAttempt.id,
            )
            .where(AiBudgetReservation.id.is_(None))
        )
        if exclude_attempt is not None:
            query = query.where(AiRequestAttempt.id != exclude_attempt)
        if await session.scalar(query.limit(1)):
            raise BudgetAdmissionError("pre_budget_attempt_inventory_incomplete")
        return gate

    async def lock_days(self, session, owner_id, days):
        """Insert-if-absent and lock days in ascending order, never after attempt."""
        insertion = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
        for day in sorted(set(days)):
            if type(day) is not date:
                raise BudgetAdmissionError("invalid_capacity_day")
            now = self.now()
            await session.execute(
                insertion(AiDailyBudget)
                .values(
                    id=uuid4(),
                    created_by=owner_id,
                    budget_day=day,
                    policy_version=1,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=["created_by", "budget_day"])
            )
            locked = await session.scalar(
                select(AiDailyBudget)
                .where(
                    AiDailyBudget.created_by == owner_id,
                    AiDailyBudget.budget_day == day,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not locked:
                raise BudgetAdmissionError("capacity_lock_missing")
        transaction = session.sync_session.get_transaction()
        routing = session.info.get("ai_budget_locked_days")
        if not routing or routing["transaction"] is not transaction:
            routing = {"transaction": transaction, "owners": {}}
            session.info["ai_budget_locked_days"] = routing
        routing["owners"].setdefault(owner_id, set()).update(days)

    async def capacity(self, session, owner_id, *, day=None, task_id=None, exclude=None):
        if (day is None) == (task_id is None):
            raise ValueError("Choose daily or whole-task capacity")
        query = select(AiBudgetReservation).where(AiBudgetReservation.created_by == owner_id)
        if day is not None:
            query = query.where(AiBudgetReservation.reservation_day == day)
        else:
            query = query.where(AiBudgetReservation.analysis_task_id == task_id)
        if exclude is not None:
            query = query.where(AiBudgetReservation.attempt_id != exclude)
        rows = list(await session.scalars(query))
        inputs = outputs = 0
        tasks = set()
        for row in rows:
            cost_in, cost_out = reservation_cost(row)
            inputs += cost_in
            outputs += cost_out
            if row.state != "released":
                tasks.add(row.analysis_task_id)
        legacy = (
            select(AiUsageLog)
            .join(
                AnalysisTask,
                AnalysisTask.id == AiUsageLog.analysis_task_id,
            )
            .where(AnalysisTask.created_by == owner_id, AiUsageLog.attempt_id.is_(None))
        )
        if day is not None:
            start = datetime.combine(day, time.min, SHANGHAI).astimezone(UTC)
            legacy = legacy.where(
                AiUsageLog.created_at >= start, AiUsageLog.created_at < start + timedelta(days=1)
            )
        else:
            legacy = legacy.where(AiUsageLog.analysis_task_id == task_id)
        for row in await session.scalars(legacy):
            if any(type(v) is not int or v < 0 for v in (row.input_tokens, row.output_tokens)):
                raise BudgetAdmissionError("legacy_usage_requires_audit")
            inputs += row.input_tokens
            outputs += row.output_tokens
            tasks.add(row.analysis_task_id)
        return Capacity(inputs, outputs, frozenset(tasks))

    async def reserve(self, session, attempt):
        """Create one hold atomically with the attempt; return the exact wire grant."""
        await self.assert_gate(session, exclude_attempt=attempt.id)
        day = self.today()
        await self.lock_days(session, attempt.created_by, [day])
        daily = await self.capacity(session, attempt.created_by, day=day)
        report = await self.capacity(session, attempt.created_by, task_id=attempt.analysis_task_id)
        grant = approve_output(
            self.policy,
            daily,
            report,
            attempt.analysis_task_id,
            attempt.estimated_input_tokens,
            attempt.max_output_tokens,
        )
        attempt.max_output_tokens = grant
        row = AiBudgetReservation(
            attempt_id=attempt.id,
            analysis_task_id=attempt.analysis_task_id,
            created_by=attempt.created_by,
            run_token=attempt.run_token,
            reservation_day=day,
            input_bound=attempt.estimated_input_tokens,
            output_bound=grant,
            state="held",
            source="admission",
        )
        session.add(row)
        await session.flush()
        return grant

    async def lock_attempt(self, session, attempt_id, *, include_today=False):
        """Reread unlocked routing after day locks; never write under a stale day."""
        route = (
            await session.execute(
                select(
                    AiBudgetReservation.created_by,
                    AiBudgetReservation.reservation_day,
                ).where(AiBudgetReservation.attempt_id == attempt_id)
            )
        ).one_or_none()
        if route is None:
            raise BudgetAdmissionError("attempt_reservation_missing")
        owner, day = route
        days = [day, self.today()] if include_today else [day]
        await self.lock_days(session, owner, days)
        attempt = await session.scalar(
            select(AiRequestAttempt)
            .where(
                AiRequestAttempt.id == attempt_id,
            )
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        reservation = await session.scalar(
            select(AiBudgetReservation)
            .where(
                AiBudgetReservation.attempt_id == attempt_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not attempt
            or not reservation
            or reservation.reservation_day != day
            or reservation.created_by != owner
            or attempt.created_by != owner
            or reservation.analysis_task_id != attempt.analysis_task_id
            or reservation.run_token != attempt.run_token
        ):
            raise BudgetAdmissionError("reservation_routing_changed_or_invalid")
        return attempt, reservation

    async def transfer_before_intent(self, session, attempt, reservation):
        day = self.today()
        routing = session.info.get("ai_budget_locked_days", {})
        if routing.get(
            "transaction"
        ) is not session.sync_session.get_transaction() or day not in routing.get("owners", {}).get(
            attempt.created_by, set()
        ):
            raise BudgetAdmissionError("server_day_changed_after_capacity_lock")
        if attempt.state != "not_sent" or attempt.ended_at or reservation.state != "held":
            raise BudgetAdmissionError("reservation_no_longer_sendable")
        if reservation.reservation_day == day:
            return
        # Caller acquired both date locks through lock_attempt(include_today=True).
        daily = await self.capacity(session, attempt.created_by, day=day, exclude=attempt.id)
        report = await self.capacity(
            session, attempt.created_by, task_id=attempt.analysis_task_id, exclude=attempt.id
        )
        grant = approve_output(
            self.policy,
            daily,
            report,
            attempt.analysis_task_id,
            reservation.input_bound,
            reservation.output_bound,
        )
        if grant < reservation.output_bound:
            raise BudgetAdmissionError("new_day_cannot_honor_original_grant")
        reservation.reservation_day = day

    def settle(self, attempt, reservation, *, inputs, outputs):
        if (
            attempt.sending_day is None
            or attempt.sending_day != reservation.reservation_day
            or any(type(v) is not int or v < 0 for v in (inputs, outputs))
        ):
            raise BudgetAdmissionError("invalid_receipt_capacity_identity")
        if reservation.state == "settled":
            if (reservation.actual_input_tokens, reservation.actual_output_tokens) != (
                inputs,
                outputs,
            ):
                raise BudgetAdmissionError("conflicting_capacity_receipt")
            return
        if reservation.state not in {"held", "adjusted"}:
            raise BudgetAdmissionError("receipt_for_released_reservation")
        reservation.state = "settled"
        reservation.actual_input_tokens, reservation.actual_output_tokens = inputs, outputs
        reservation.adjusted_input_tokens = reservation.adjusted_output_tokens = None
        reservation.settled_at = self.now()

    def release_not_sent(self, attempt, reservation):
        if attempt.state != "not_sent" or attempt.send_intent_at is not None:
            raise BudgetAdmissionError("cannot_release_sent_or_unknown_capacity")
        if reservation.state == "held":
            reservation.state, reservation.released_at = "released", self.now()
        elif reservation.state != "released":
            raise BudgetAdmissionError("cannot_release_receipt_or_adjusted_capacity")

    async def backfill_pre_budget_attempts(self, session):
        """Strict receipt-preserving inventory; caller keeps the activation gate closed.

        This does not infer missing legacy HTTP or authorize activation. Every
        failure aborts the caller's transaction, rather than skipping bad rows.
        """
        pending = list(
            await session.scalars(
                select(AiRequestAttempt)
                .outerjoin(
                    AiBudgetReservation,
                    AiBudgetReservation.attempt_id == AiRequestAttempt.id,
                )
                .where(AiBudgetReservation.id.is_(None))
                .order_by(
                    AiRequestAttempt.created_by,
                    AiRequestAttempt.physical_sequence,
                )
            )
        )
        routes = []
        for row in pending:
            if row.state == "not_sent":
                if row.send_intent_at is not None or row.sending_day is not None:
                    raise BudgetAdmissionError("pre_budget_unsent_identity_invalid")
                created = row.created_at
                # SQLite stores ORM UTC DateTime without its timezone marker.
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                day = created.astimezone(SHANGHAI).date()
            else:
                if row.send_intent_at is None or row.sending_day is None:
                    raise BudgetAdmissionError("pre_budget_send_day_missing")
                intent = row.send_intent_at
                if intent.tzinfo is None:
                    intent = intent.replace(tzinfo=UTC)
                day = row.sending_day
                if intent.astimezone(SHANGHAI).date() != day:
                    raise BudgetAdmissionError("pre_budget_send_day_conflict")
            task_owner = await session.scalar(
                select(AnalysisTask.created_by).where(
                    AnalysisTask.id == row.analysis_task_id,
                )
            )
            if task_owner != row.created_by:
                raise BudgetAdmissionError("pre_budget_owner_conflict")
            routes.append((row.created_by, day, row.id))
        # Lock every routing day before any attempt; stable owner/date order.
        for owner in sorted({owner for owner, _day, _id in routes}, key=str):
            await self.lock_days(session, owner, [day for who, day, _id in routes if who == owner])
        count = 0
        for owner, day, attempt_id in routes:
            row = await session.scalar(
                select(AiRequestAttempt)
                .where(
                    AiRequestAttempt.id == attempt_id,
                )
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
            if row.created_by != owner or (row.state != "not_sent" and row.sending_day != day):
                raise BudgetAdmissionError("pre_budget_routing_changed")
            existing = await session.scalar(
                select(AiBudgetReservation.id).where(
                    AiBudgetReservation.attempt_id == attempt_id,
                )
            )
            if existing:
                continue
            item = AiBudgetReservation(
                attempt_id=row.id,
                created_by=owner,
                analysis_task_id=row.analysis_task_id,
                run_token=row.run_token,
                reservation_day=day,
                input_bound=row.estimated_input_tokens,
                output_bound=row.max_output_tokens,
                state="held",
                source="pre_budget_attempt",
            )
            if row.state in {"received_unbooked", "booked"}:
                receipt = parse_usage_receipt({"usage": row.usage_raw})
                if not receipt.trusted or (
                    row.usage_input_tokens,
                    row.usage_output_tokens,
                    row.usage_cache_hit_tokens,
                ) != (receipt.input_tokens, receipt.output_tokens, receipt.cache_hit_tokens):
                    raise BudgetAdmissionError("pre_budget_receipt_invalid")
                self.settle(row, item, inputs=receipt.input_tokens, outputs=receipt.output_tokens)
            elif row.state == "not_sent" and row.ended_at is not None:
                self.release_not_sent(row, item)
            elif row.state not in {"not_sent", "in_flight", "usage_unknown"}:
                raise BudgetAdmissionError("pre_budget_state_invalid")
            session.add(item)
            await session.flush()
            count += 1
        return count
