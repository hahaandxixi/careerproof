"""Real synthetic upload setup for the PG hard-stop matching entry."""

from uuid import UUID

from sqlalchemy import select

from app.models.ai_budget import AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.models.recruitment import Application
from app.services.application_verification import _digest
from app.tests.test_application_verification import case as case
from app.tests.test_attempt_hard_stop import prepare_chain_task
from app.tests.test_real_matching import matching_db as matching_db


async def test_matching_setup_uploads_then_queues_same_owner_without_changing_application(
    case, monkeypatch,  # noqa: F811
):
    async with case.factory() as session:
        application = await session.get(Application, UUID(case.application_id))
        before = _digest(application.report_snapshot)
        original_report = await session.get(MatchReport, case.report_id)
        owner = (await session.get(AnalysisTask, original_report.analysis_task_id)).created_by
    task_id = await prepare_chain_task(case, "matching", monkeypatch)
    async with case.factory() as session:
        task = await session.get(AnalysisTask, task_id)
        assert task.status == TaskStatus.PENDING
        assert task.created_by == owner and task.task_type == "job_match"
        assert await session.scalar(select(MatchReport.id).where(
            MatchReport.analysis_task_id == task_id,
        )) is None
        assert await session.scalar(select(AiRequestAttempt.id).where(
            AiRequestAttempt.analysis_task_id == task_id,
        )) is None
        assert await session.scalar(select(AiBudgetReservation.id).where(
            AiBudgetReservation.analysis_task_id == task_id,
        )) is None
        application = await session.get(Application, UUID(case.application_id))
        assert _digest(application.report_snapshot) == before
    assert len(case.submitted) == 1
    assert case.submitted[0][1][0] == task_id
