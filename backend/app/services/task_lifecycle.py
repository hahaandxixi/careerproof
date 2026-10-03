"""Database compare-and-set leases shared by material and matching tasks."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus
from app.models.identity import User
from app.models.portfolio import ProjectVersion, ResumeVersion

logger = logging.getLogger(__name__)


async def claim_task(session: AsyncSession, task_id: UUID, *, step: str) -> UUID | None:
    token = uuid4()
    now = datetime.now(UTC)
    result = await session.execute(
        update(AnalysisTask)
        .where(AnalysisTask.id == task_id, AnalysisTask.status == TaskStatus.PENDING)
        .values(
            status=TaskStatus.RUNNING,
            run_token=token,
            attempt=AnalysisTask.attempt + 1,
            started_at=now,
            heartbeat_at=now,
            completed_at=None,
            error_message=None,
            progress=10,
            current_step=step,
        )
    )
    await session.commit()
    return token if result.rowcount == 1 else None


async def finish_task(
    session: AsyncSession,
    task_id: UUID,
    token: UUID,
    *,
    status: TaskStatus = TaskStatus.COMPLETED,
    step: str,
    error_message: str | None = None,
) -> bool:
    """Does not commit: save business results in the same transaction on True."""
    if status not in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        raise ValueError("finish_task requires a terminal status")
    result = await session.execute(
        update(AnalysisTask)
        .where(
            AnalysisTask.id == task_id,
            AnalysisTask.status == TaskStatus.RUNNING,
            AnalysisTask.run_token == token,
        )
        .values(
            status=status,
            progress=100 if status == TaskStatus.COMPLETED else 0,
            current_step=step,
            error_message=error_message,
            completed_at=datetime.now(UTC),
            run_token=None,
        )
    )
    return result.rowcount == 1


async def update_task_progress(
    session: AsyncSession,
    task_id: UUID,
    token: UUID,
    *,
    progress: int,
    step: str,
) -> bool:
    if not 10 <= progress < 100:
        raise ValueError("running task progress must be between 10 and 99")
    result = await session.execute(
        update(AnalysisTask)
        .where(
            AnalysisTask.id == task_id,
            AnalysisTask.status == TaskStatus.RUNNING,
            AnalysisTask.run_token == token,
        )
        .values(progress=progress, current_step=step, heartbeat_at=datetime.now(UTC))
    )
    await session.commit()
    return result.rowcount == 1


async def heartbeat_task(task_id: UUID, token: UUID, session_factory) -> None:
    consecutive_failures = 0
    while True:
        await asyncio.sleep(min(10, settings.task_lease_seconds / 3))
        try:
            async with session_factory() as session:
                result = await session.execute(
                    update(AnalysisTask)
                    .where(
                        AnalysisTask.id == task_id,
                        AnalysisTask.status == TaskStatus.RUNNING,
                        AnalysisTask.run_token == token,
                    )
                    .values(heartbeat_at=datetime.now(UTC))
                )
                await session.commit()
                if result.rowcount != 1:
                    return
            consecutive_failures = 0
        except (SQLAlchemyError, OSError, TimeoutError):
            consecutive_failures += 1
            if consecutive_failures == 1 or consecutive_failures % 12 == 0:
                logger.warning(
                    "Task heartbeat failed for %s (%s consecutive attempts); retrying",
                    task_id,
                    consecutive_failures,
                    exc_info=True,
                )


async def reset_failed_task(
    session: AsyncSession, task_id: UUID, current_user: User
) -> AnalysisTask:
    """Owner-only compare-and-set retry. Caller validates inputs before committing."""
    task = await session.get(AnalysisTask, task_id)
    if not task or task.created_by != current_user.id:
        raise AppError("分析任务不存在或无权访问", code=4041, status_code=404)
    result = await session.execute(
        update(AnalysisTask)
        .where(
            AnalysisTask.id == task_id,
            AnalysisTask.created_by == current_user.id,
            AnalysisTask.status == TaskStatus.FAILED,
        )
        .values(
            status=TaskStatus.PENDING,
            run_token=None,
            heartbeat_at=datetime.now(UTC),
            started_at=None,
            completed_at=None,
            error_message=None,
            progress=0,
            current_step="等待重试",
        )
    )
    if result.rowcount != 1:
        raise AppError(
            "只有失败的任务可以重试，任务可能已被其他请求重新提交", code=4094, status_code=409
        )
    await session.refresh(task)
    return task


async def recover_interrupted_tasks(session_factory) -> int:
    """Recover expired leases only; another live worker's tasks remain untouched."""
    now = datetime.now(UTC)
    running_cutoff = now - timedelta(seconds=settings.task_lease_seconds)
    pending_cutoff = now - timedelta(seconds=settings.task_pending_timeout_seconds)
    async with session_factory() as session:
        result = await session.execute(
            update(AnalysisTask)
            .where(
                or_(
                    and_(
                        AnalysisTask.status == TaskStatus.RUNNING,
                        or_(
                            AnalysisTask.heartbeat_at < running_cutoff,
                            and_(
                                AnalysisTask.heartbeat_at.is_(None),
                                AnalysisTask.updated_at < running_cutoff,
                            ),
                        ),
                    ),
                    and_(
                        AnalysisTask.status == TaskStatus.PENDING,
                        or_(
                            AnalysisTask.heartbeat_at < pending_cutoff,
                            and_(
                                AnalysisTask.heartbeat_at.is_(None),
                                AnalysisTask.updated_at < pending_cutoff,
                            ),
                        ),
                    ),
                )
            )
            .values(
                status=TaskStatus.FAILED,
                run_token=None,
                completed_at=now,
                current_step="任务中断",
                error_message="任务执行已中断或等待超时，请重试；已上传文件仍然保留",
            )
            .returning(AnalysisTask.id)
        )
        ids = list(result.scalars())
        if ids:
            await session.execute(
                update(ResumeVersion)
                .where(ResumeVersion.analysis_task_id.in_(ids))
                .values(parse_status="failed")
            )
            await session.execute(
                update(ProjectVersion)
                .where(ProjectVersion.analysis_task_id.in_(ids))
                .values(analysis_status="failed")
            )
        await session.commit()
        return len(ids)
