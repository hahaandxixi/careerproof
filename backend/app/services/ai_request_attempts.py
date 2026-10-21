"""Durable physical requests; reconciliation never calls a provider or restores results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.agents.attempt_receipts import parse_usage_receipt
from app.models.ai_budget import AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.enums import TaskStatus
from app.models.identity import User

MODE = "attempt_v1"
SHANGHAI = timezone(timedelta(hours=8))


class AttemptAdmissionError(RuntimeError):
    """No HTTP may be sent when durable admission fails."""


class ReceiptConflictError(RuntimeError):
    """An existing physical identity cannot be relabelled or silently recharged."""


@dataclass(frozen=True, slots=True)
class AttemptContext:
    task_id: UUID
    created_by: UUID
    run_token: UUID
    step: str
    provider: str
    model: str


class AttemptService:
    def __init__(
        self, factory, context: AttemptContext, *, authorize=None, phase_hook=None, budget=None
    ):
        self.factory = factory
        self.context = context
        self.authorize = authorize
        self.phase_hook = phase_hook
        # None retains standalone/offline accounting. Workflow constructors must
        # explicitly supply SharedBudgetService to activate persistent admission.
        self.budget = budget

    async def _phase(self, name, attempt_id):
        if self.phase_hook:
            await self.phase_hook(name, attempt_id)

    async def _live_identity(self, session):
        ctx = self.context
        # NO KEY UPDATE excludes competing identity changes but permits FK
        # KEY SHARE checks from withdrawal notifications and ledger inserts.
        user = await session.scalar(
            select(User.id)
            .where(
                User.id == ctx.created_by,
                User.is_active.is_(True),
            )
            .with_for_update(key_share=True)
        )
        task = await session.scalar(
            select(AnalysisTask)
            .where(
                AnalysisTask.id == ctx.task_id,
            )
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if (
            not user
            or not task
            or task.created_by != ctx.created_by
            or task.status != TaskStatus.RUNNING
            or task.run_token != ctx.run_token
            or (task.input_snapshot or {}).get("externalAiConsent") is not True
        ):
            raise AttemptAdmissionError("claim_or_owner_not_authorized")
        return task

    def _check_identity(self, row):
        ctx = self.context
        if (
            not row
            or row.analysis_task_id != ctx.task_id
            or row.created_by != ctx.created_by
            or row.run_token != ctx.run_token
            or row.provider != ctx.provider
            or row.model != ctx.model
        ):
            raise ReceiptConflictError("attempt_identity_mismatch")

    async def _locked_attempt(self, session, attempt_id, *, include_today=False):
        if self.budget is not None:
            row, reservation = await self.budget.lock_attempt(
                session,
                attempt_id,
                include_today=include_today,
            )
            self._check_identity(row)
            session.info.setdefault("attempt_budget_reservations", {})[attempt_id] = reservation
            return row
        row = await session.scalar(
            select(AiRequestAttempt)
            .where(
                AiRequestAttempt.id == attempt_id,
            )
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        self._check_identity(row)
        return row

    async def prepare(self, *, estimated_input_tokens: int, max_output_tokens: int) -> UUID:
        attempt_id, _grant = await self.prepare_for_send(
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=max_output_tokens,
        )
        return attempt_id

    async def prepare_for_send(self, *, estimated_input_tokens: int, max_output_tokens: int):
        if any(
            type(value) is not int or value < 0
            for value in (estimated_input_tokens, max_output_tokens)
        ):
            raise AttemptAdmissionError("invalid_request_bounds")
        ctx = self.context
        async with self.factory() as session:
            task = await self._live_identity(session)
            legacy = await session.scalar(
                select(AiUsageLog.id)
                .where(
                    AiUsageLog.run_token == ctx.run_token,
                    AiUsageLog.attempt_id.is_(None),
                )
                .limit(1)
            )
            if legacy:
                raise AttemptAdmissionError("legacy_claim_cannot_switch_accounting")
            collision = await session.scalar(
                select(AiRequestAttempt.id)
                .where(
                    AiRequestAttempt.run_token == ctx.run_token,
                    or_(
                        AiRequestAttempt.analysis_task_id != ctx.task_id,
                        AiRequestAttempt.created_by != ctx.created_by,
                    ),
                )
                .limit(1)
            )
            if collision:
                raise AttemptAdmissionError("claim_identity_collision")
            mode = (task.input_snapshot or {}).get("usageAccountingMode")
            if mode not in (None, MODE):
                raise AttemptAdmissionError("incompatible_accounting_mode")
            task.input_snapshot = {**task.input_snapshot, "usageAccountingMode": MODE}
            sequence = (
                await session.scalar(
                    select(
                        func.max(
                            AiRequestAttempt.physical_sequence,
                        )
                    ).where(AiRequestAttempt.run_token == ctx.run_token)
                )
                or 0
            ) + 1
            row = AiRequestAttempt(
                analysis_task_id=ctx.task_id,
                created_by=ctx.created_by,
                run_token=ctx.run_token,
                step=ctx.step,
                physical_sequence=sequence,
                provider=ctx.provider,
                model=ctx.model,
                state="not_sent",
                estimated_input_tokens=estimated_input_tokens,
                max_output_tokens=max_output_tokens,
                usage_raw={},
            )
            session.add(row)
            await session.flush()
            attempt_id = row.id
            grant = (
                await self.budget.reserve(session, row)
                if self.budget is not None
                else max_output_tokens
            )
            await session.commit()
        await self._phase("prepared", attempt_id)
        return attempt_id, grant

    async def mark_intent(self, attempt_id):
        try:
            async with self.factory() as session:
                await self._live_identity(session)
                if self.authorize:
                    await self.authorize(session)
                if self.budget is not None:
                    await self.budget.assert_gate(session)
                row = await self._locked_attempt(session, attempt_id, include_today=True)
                if row.state != "not_sent" or row.ended_at is not None:
                    raise AttemptAdmissionError("attempt_no_longer_sendable")
                now = datetime.now(UTC)
                if self.budget is not None:
                    reservation = session.info["attempt_budget_reservations"][attempt_id]
                    await self.budget.transfer_before_intent(session, row, reservation)
                    now = self.budget.now()
                    if now.astimezone(SHANGHAI).date() != reservation.reservation_day:
                        raise AttemptAdmissionError("day_changed_before_intent_commit")
                row.state, row.send_intent_at = "in_flight", now
                row.sending_day = now.astimezone(SHANGHAI).date()
                await session.commit()
        except Exception:
            # A failed/ambiguous intent commit never permits HTTP. If the
            # server actually committed in_flight, do not erase that fact.
            await self.close_not_sent(attempt_id, "send_admission_failed")
            raise
        await self._phase("send_intent_committed", attempt_id)

    async def close_not_sent(self, attempt_id, reason):
        async with self.factory() as session:
            row = await self._locked_attempt(session, attempt_id)
            if row.state == "not_sent" and row.ended_at is None:
                if self.budget is not None:
                    self.budget.release_not_sent(
                        row,
                        session.info["attempt_budget_reservations"][attempt_id],
                    )
                row.ended_at, row.reason = datetime.now(UTC), reason
                await session.commit()

    async def receive(self, attempt_id, payload, latency_ms):
        receipt = parse_usage_receipt(payload)
        if type(latency_ms) is not int or latency_ms < 0:
            raise ReceiptConflictError("invalid_receipt_latency")
        await self._phase("response_observed", attempt_id)
        async with self.factory() as session:
            row = await self._locked_attempt(session, attempt_id)
            if row.state == "not_sent":
                raise ReceiptConflictError("receipt_before_send_intent")
            if row.response_digest:
                if row.response_digest != receipt.response_digest:
                    raise ReceiptConflictError("conflicting_physical_receipt")
                # A duplicate receipt must not change counters or timestamps.
                return row.state
            if row.state not in ("in_flight", "usage_unknown"):
                raise ReceiptConflictError("receipt_state_invalid")
            row.usage_raw = receipt.raw
            row.response_digest = receipt.response_digest
            row.latency_ms = latency_ms
            row.receipt_at = row.ended_at = datetime.now(UTC)
            row.reason = receipt.reason
            if receipt.trusted:
                if self.budget is not None:
                    self.budget.settle(
                        row,
                        session.info["attempt_budget_reservations"][attempt_id],
                        inputs=receipt.input_tokens,
                        outputs=receipt.output_tokens,
                    )
                row.state = "received_unbooked"
                row.usage_input_tokens = receipt.input_tokens
                row.usage_output_tokens = receipt.output_tokens
                row.usage_cache_hit_tokens = receipt.cache_hit_tokens
            else:
                row.state = "usage_unknown"
            state = row.state
            await session.commit()
        await self._phase("receipt_committed", attempt_id)
        return state

    async def mark_unknown(self, attempt_id, reason):
        allowed = {"provider_timeout", "provider_network", "provider_http_error", "cancelled"}
        reason = reason if reason in allowed else "provider_failure"
        async with self.factory() as session:
            row = await self._locked_attempt(session, attempt_id)
            if row.state == "in_flight":
                row.state, row.reason = "usage_unknown", reason
                row.ended_at = datetime.now(UTC)
                await session.commit()

    @staticmethod
    def _trusted_values(row):
        parsed = parse_usage_receipt({"usage": row.usage_raw})
        values = (row.usage_input_tokens, row.usage_output_tokens, row.usage_cache_hit_tokens)
        if not parsed.trusted or values != (
            parsed.input_tokens,
            parsed.output_tokens,
            parsed.cache_hit_tokens,
        ):
            raise ReceiptConflictError("persisted_receipt_not_trustworthy")
        return values

    async def book_one(self, attempt_id):
        ctx = self.context
        async with self.factory() as session:
            row = await self._locked_attempt(session, attempt_id)
            if row.state not in ("received_unbooked", "booked"):
                return 0
            inputs, outputs, cache = self._trusted_values(row)
            if self.budget is not None:
                self.budget.settle(
                    row,
                    session.info["attempt_budget_reservations"][attempt_id],
                    inputs=inputs,
                    outputs=outputs,
                )
            insertion = (
                pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
            )
            result = await session.execute(
                insertion(AiUsageLog)
                .values(
                    analysis_task_id=ctx.task_id,
                    attempt_id=row.id,
                    run_token=ctx.run_token,
                    request_seq=row.physical_sequence,
                    model=ctx.model,
                    input_tokens=inputs,
                    output_tokens=outputs,
                    cache_hit_tokens=cache,
                    latency_ms=row.latency_ms or 0,
                    unit_price_snapshot={
                        "provider": ctx.provider,
                        "priceVerified": False,
                        "accountingMode": MODE,
                    },
                )
                .on_conflict_do_nothing()
            )
            existing = list(
                await session.scalars(
                    select(AiUsageLog)
                    .where(
                        or_(
                            AiUsageLog.attempt_id == row.id,
                            (AiUsageLog.run_token == ctx.run_token)
                            & (AiUsageLog.request_seq == row.physical_sequence),
                        )
                    )
                    .with_for_update(key_share=True)
                )
            )
            if len(existing) != 1:
                raise ReceiptConflictError("ambiguous_ledger_identity")
            ledger = existing[0]
            if (
                ledger.attempt_id != row.id
                or ledger.analysis_task_id != ctx.task_id
                or ledger.run_token != ctx.run_token
                or ledger.request_seq != row.physical_sequence
                or ledger.model != ctx.model
                or (ledger.input_tokens, ledger.output_tokens, ledger.cache_hit_tokens)
                != (inputs, outputs, cache)
            ):
                raise ReceiptConflictError("conflicting_ledger_fact")
            if row.state != "booked":
                row.state, row.booked_at = "booked", datetime.now(UTC)
            written = result.rowcount or 0
            await session.commit()
        await self._phase("ledger_committed", attempt_id)
        return written

    async def reconcile(self):
        ctx = self.context
        async with self.factory() as session:
            ids = list(
                await session.scalars(
                    select(AiRequestAttempt.id)
                    .where(
                        AiRequestAttempt.analysis_task_id == ctx.task_id,
                        AiRequestAttempt.run_token == ctx.run_token,
                        AiRequestAttempt.state.in_(["received_unbooked", "booked"]),
                    )
                    .order_by(AiRequestAttempt.physical_sequence)
                )
            )
        written = sum([await self.book_one(attempt_id) for attempt_id in ids])
        async with self.factory() as session:
            task = await session.scalar(
                select(AnalysisTask)
                .where(
                    AnalysisTask.id == ctx.task_id,
                )
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
            if task and task.status == TaskStatus.RUNNING and task.run_token == ctx.run_token:
                return written
            pending = (
                select(AiRequestAttempt)
                .where(
                    AiRequestAttempt.analysis_task_id == ctx.task_id,
                    AiRequestAttempt.run_token == ctx.run_token,
                    AiRequestAttempt.state.in_(["not_sent", "in_flight"]),
                )
                .order_by(AiRequestAttempt.physical_sequence)
            )
            if self.budget is None:
                pending = pending.with_for_update(key_share=True)
            rows = list(await session.scalars(pending))
            if self.budget is not None and rows:
                days = list(await session.scalars(select(
                    AiBudgetReservation.reservation_day,
                ).where(AiBudgetReservation.attempt_id.in_([row.id for row in rows]))))
                # Acquire all recovery days in order before the first attempt;
                # physical sequence need not follow chronological days.
                await self.budget.lock_days(session, ctx.created_by, days)
            for row in rows:
                if self.budget is not None:
                    row = await self._locked_attempt(session, row.id)
                self._check_identity(row)
                if row.state == "not_sent" and row.ended_at is None:
                    if self.budget is not None:
                        self.budget.release_not_sent(
                            row,
                            session.info["attempt_budget_reservations"][row.id],
                        )
                    row.ended_at = datetime.now(UTC)
                    row.reason = "worker_ended_before_intent"
                elif row.state == "in_flight":
                    row.state, row.reason = "usage_unknown", "worker_ended_without_receipt"
                    row.ended_at = datetime.now(UTC)
            await session.commit()
        return written

    async def summary(self):
        ctx = self.context
        async with self.factory() as session:
            rows = list(
                await session.scalars(
                    select(AiRequestAttempt)
                    .where(
                        AiRequestAttempt.analysis_task_id == ctx.task_id,
                        AiRequestAttempt.run_token == ctx.run_token,
                    )
                    .order_by(AiRequestAttempt.physical_sequence)
                )
            )
        sent, known = [], []
        for row in rows:
            self._check_identity(row)
            if row.state == "not_sent":
                continue
            sent.append(row)
            if row.state in ("received_unbooked", "booked"):
                self._trusted_values(row)
                known.append(row)
        all_known = bool(sent) and len(known) == len(sent)
        return {
            "accountingMode": MODE,
            "attemptCount": len(rows),
            "intentCount": len(sent),
            "trustedReceiptCount": len(known),
            "unknownAttemptCount": len(sent) - len(known),
            "usageKnown": all_known,
            "usageBooked": all_known and all(row.state == "booked" for row in known),
            "inputTokens": sum(row.usage_input_tokens for row in known),
            "outputTokens": sum(row.usage_output_tokens for row in known),
            "cacheHitTokens": sum(row.usage_cache_hit_tokens for row in known),
            "latencyMs": sum(row.latency_ms or 0 for row in known),
        }


class DurableRequestObserver:
    def __init__(self, service: AttemptService):
        self.service = service

    async def before_send(self, request):
        maximum = request.get("max_tokens")
        if type(maximum) is not int or maximum < 1:
            raise AttemptAdmissionError("unbounded_output_request")
        from app.agents.input_budget import estimate_wire_input_bytes

        estimated = estimate_wire_input_bytes(request)
        if self.service.budget is None:
            attempt_id = await self.service.prepare(
                estimated_input_tokens=estimated,
                max_output_tokens=maximum,
            )
        else:
            attempt_id, grant = await self.service.prepare_for_send(
                estimated_input_tokens=estimated,
                max_output_tokens=maximum,
            )
            request["max_tokens"] = grant
        await self.service.mark_intent(attempt_id)
        return attempt_id

    async def after_response(self, attempt_id, payload, latency_ms):
        await self.service.receive(attempt_id, payload, latency_ms)

    async def on_failure(self, attempt_id, reason):
        await self.service.mark_unknown(attempt_id, reason)
