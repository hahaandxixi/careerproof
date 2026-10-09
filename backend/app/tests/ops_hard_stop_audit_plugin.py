"""Read-only evidence recorder around the unchanged real hard-stop assertions."""

import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.ai_budget import AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask, MatchReport
from app.models.recruitment import Application
from app.services.ai_request_attempts import AttemptService
from app.services.application_verification import _digest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.module.__name__.split(".")[-1] != "test_attempt_hard_stop":
        yield
        return
    destination = Path(os.environ["OPS_HARD_STOP_AUDIT_DIR"]).resolve()
    allowed = Path(__file__).resolve().parents[3] / "docs" / "evidence"
    if not destination.is_relative_to(allowed):
        raise AssertionError("Hard-stop audit must be inside this repository's evidence directory")
    destination.mkdir(parents=True, exist_ok=True)
    phase = item.callspec.params["phase"]
    chain = item.callspec.params["chain"]
    proof = {"phase": phase, "chain": chain, "recovery": []}
    target = destination / f"{chain}-{phase}.json"
    if target.exists():
        raise AssertionError("Preserve previous hard-stop evidence; choose a fresh audit directory")
    case = item.funcargs["case"]
    temporary = item.funcargs["tmp_path"]
    worker_class = item.module.WorkerProcess
    original_terminate = worker_class.terminate_and_wait
    original_reconcile = AttemptService.reconcile

    def save():
        target.write_text(json.dumps(proof, indent=2, default=str), encoding="utf-8")

    def terminate(worker, timeout):
        marker = json.loads((temporary / f"child-state-{phase}.json").read_text(encoding="utf-8"))
        proof["killIdentity"] = {
            "pid": worker.pid, "parentPid": worker.parent_pid,
            "creationSeconds": worker.creation_seconds, "marker": marker,
        }
        save()
        code = original_terminate(worker, timeout)
        proof["killExitCode"] = code
        save()
        return code

    async def facts(service):
        async with case.factory() as session:
            task = await session.get(AnalysisTask, service.context.task_id)
            attempts = list(await session.scalars(select(AiRequestAttempt).where(
                AiRequestAttempt.analysis_task_id == task.id,
                AiRequestAttempt.run_token == service.context.run_token,
            )))
            ledger = list(await session.scalars(select(AiUsageLog).where(
                AiUsageLog.analysis_task_id == task.id,
            )))
            reservations = list(await session.scalars(select(AiBudgetReservation).where(
                AiBudgetReservation.analysis_task_id == task.id,
            )))
            application = await session.get(Application, UUID(case.application_id))
            snapshot_digest = _digest(application.report_snapshot)
            business_report = await session.scalar(select(MatchReport.id).where(
                MatchReport.analysis_task_id == task.id,
            ))
        counter = temporary / f"http-count-{phase}.txt"
        return {
            "httpCount": int(counter.read_text()) if counter.exists() else 0,
            "taskStatus": task.status.value, "taskRunToken": task.run_token,
            "businessAnalysisPresent": bool((task.input_snapshot or {}).get("analysis")),
            "businessReportPresent": business_report is not None,
            "applicationSnapshotDigest": snapshot_digest,
            "reservations": [{
                "attemptId": row.attempt_id, "state": row.state,
                "day": row.reservation_day, "inputBound": row.input_bound,
                "outputBound": row.output_bound, "actualInput": row.actual_input_tokens,
                "actualOutput": row.actual_output_tokens,
            } for row in reservations],
            "attempts": [{
                "id": row.id, "state": row.state, "reason": row.reason,
                "input": row.usage_input_tokens, "output": row.usage_output_tokens,
                "cache": row.usage_cache_hit_tokens, "runToken": row.run_token,
            } for row in attempts],
            "ledger": [{
                "id": row.id, "attemptId": row.attempt_id, "runToken": row.run_token,
                "sequence": row.request_seq, "input": row.input_tokens,
                "output": row.output_tokens, "cache": row.cache_hit_tokens,
            } for row in ledger],
        }

    async def reconcile(service):
        before = await facts(service)
        written = await original_reconcile(service)
        after = await facts(service)
        proof["recovery"].append({
            "before": before, "written": written, "after": after,
            "summary": await service.summary(),
        })
        save()
        return written

    worker_class.terminate_and_wait = terminate
    AttemptService.reconcile = reconcile
    try:
        outcome = yield
        proof["assertionsPassed"] = outcome.excinfo is None
        save()
    finally:
        worker_class.terminate_and_wait = original_terminate
        AttemptService.reconcile = original_reconcile
