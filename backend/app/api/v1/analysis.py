from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import async_session_factory, get_session
from app.models.enums import TaskStatus
from app.models.identity import User
from app.repositories.analysis import AnalysisRepository
from app.schemas.analysis import (
    AnalysisTaskView,
    EvidenceReviewUpdate,
    MatchCreate,
    MatchItemView,
    MatchReportSummary,
    MatchReportView,
    TaskAccepted,
)
from app.schemas.common import ApiResponse, success
from app.services.analysis import AnalysisService, execute_match_task, format_sse_event
from app.services.portfolio import retry_material_task
from app.services.task_runner import FastAPIBackgroundTaskRunner

router = APIRouter()


@router.post("/matches", response_model=ApiResponse[TaskAccepted], status_code=202)
async def create_match(
    payload: MatchCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TaskAccepted]:
    accepted = await AnalysisService(session).create_match_task(payload, current_user)
    FastAPIBackgroundTaskRunner().submit(
        background_tasks,
        execute_match_task,
        accepted.task_id,
    )
    return success(accepted, message="accepted")


@router.post(
    "/analysis-tasks/{task_id}/retry", response_model=ApiResponse[TaskAccepted], status_code=202
)
async def retry_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TaskAccepted]:
    task = await AnalysisService(session).get_task(task_id, current_user)
    if task.task_type == "job_match":
        accepted = await AnalysisService(session).retry_match(task_id, current_user)
        callback, args = execute_match_task, (task_id,)
    else:
        accepted, callback, args = await retry_material_task(session, task_id, current_user)
    FastAPIBackgroundTaskRunner().submit(background_tasks, callback, *args)
    return success(accepted, message="accepted")


@router.get("/match-reports", response_model=ApiResponse[list[MatchReportSummary]])
async def list_match_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100, alias="pageSize"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[MatchReportSummary]]:
    return success(await AnalysisService(session).list_reports(current_user, page, page_size))


@router.get("/analysis-tasks/{task_id}", response_model=ApiResponse[AnalysisTaskView])
async def get_analysis_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AnalysisTaskView]:
    return success(await AnalysisService(session).get_task(task_id, current_user))


@router.get("/analysis-tasks/{task_id}/events", response_class=StreamingResponse)
async def task_events(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    await AnalysisService(session).get_task(task_id, current_user)

    async def stream():
        last_state: tuple[str, int, str | None] | None = None
        while True:
            async with async_session_factory() as polling_session:
                task = await AnalysisRepository(polling_session).get_task(task_id)
                if not task:
                    yield format_sse_event("task.failed", {"message": "任务不存在"})
                    return
                state = (task.status.value, task.progress, task.current_step)
                if state != last_state:
                    event = (
                        "task.completed"
                        if task.status == TaskStatus.COMPLETED
                        else "task.failed"
                        if task.status == TaskStatus.FAILED
                        else "task.progress"
                    )
                    yield format_sse_event(
                        event,
                        {
                            "taskId": str(task.id),
                            "status": task.status.value,
                            "progress": task.progress,
                            "currentStep": task.current_step,
                            "errorMessage": task.error_message,
                        },
                    )
                    last_state = state
                if task.status in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                }:
                    return
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/match-reports/{report_id}", response_model=ApiResponse[MatchReportView])
async def get_match_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MatchReportView]:
    return success(await AnalysisService(session).get_report(report_id, current_user))


@router.patch(
    "/match-reports/{report_id}/items/{requirement_id}/review",
    response_model=ApiResponse[MatchItemView],
)
async def review_match_evidence(
    report_id: UUID,
    requirement_id: UUID,
    payload: EvidenceReviewUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MatchItemView]:
    item = await AnalysisService(session).review_evidence(
        report_id, requirement_id, payload, current_user
    )
    return success(item, message="reviewed")
