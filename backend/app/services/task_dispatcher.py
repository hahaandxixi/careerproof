"""Resume database-backed pending jobs after request or process interruption."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus
from app.models.portfolio import ProjectVersion, ResumeVersion
from app.services.analysis import execute_match_task
from app.services.portfolio import execute_project_scan_task, execute_resume_parse_task
from app.services.task_runner import run_bounded

logger = logging.getLogger(__name__)
_active: dict[UUID, asyncio.Task[None]] = {}


async def _pending_jobs(
    session_factory,
) -> list[tuple[UUID, Callable[..., Awaitable[None]], tuple[Any, ...]]]:
    jobs: list[tuple[UUID, Callable[..., Awaitable[None]], tuple[Any, ...]]] = []
    async with session_factory() as session:
        tasks = list(
            await session.scalars(
                select(AnalysisTask)
                .where(AnalysisTask.status == TaskStatus.PENDING)
                .order_by(AnalysisTask.created_at, AnalysisTask.id)
                .limit(settings.task_concurrency * 4)
            )
        )
        for task in tasks:
            if task.task_type == "job_match":
                jobs.append((task.id, execute_match_task, (task.id,)))
            elif task.task_type == "resume_parse":
                version_id = await session.scalar(
                    select(ResumeVersion.id).where(ResumeVersion.analysis_task_id == task.id)
                )
                if version_id:
                    jobs.append((task.id, execute_resume_parse_task, (task.id, version_id)))
            elif task.task_type == "project_scan":
                version_id = await session.scalar(
                    select(ProjectVersion.id).where(ProjectVersion.analysis_task_id == task.id)
                )
                if version_id:
                    jobs.append((task.id, execute_project_scan_task, (task.id, version_id)))
    return jobs


def _forget(task_id: UUID, execution: asyncio.Task[None]) -> None:
    if _active.get(task_id) is execution:
        _active.pop(task_id, None)
    if not execution.cancelled() and (error := execution.exception()):
        logger.error("Dispatched task %s escaped its worker: %s", task_id, error)


async def dispatch_pending_tasks(session_factory) -> int:
    scheduled = 0
    for task_id, callback, args in await _pending_jobs(session_factory):
        if task_id in _active:
            continue
        execution = asyncio.create_task(
            run_bounded(callback, *args), name=f"careerproof-task-{task_id}"
        )
        _active[task_id] = execution
        execution.add_done_callback(lambda done, key=task_id: _forget(key, done))
        scheduled += 1
    return scheduled


async def stop_dispatched_tasks() -> None:
    tasks = list(_active.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _active.clear()


async def wait_for_dispatched_tasks() -> None:
    """Testing hook: wait until the current dispatcher batch settles."""
    while tasks := list(_active.values()):
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks)
