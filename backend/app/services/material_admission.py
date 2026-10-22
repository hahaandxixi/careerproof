"""Transactional per-owner upload admission, including outstanding extraction space."""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus
from app.models.identity import User
from app.models.portfolio import Project, ProjectFile, ProjectVersion, Resume, ResumeVersion


async def lock_material_owner(session: AsyncSession, user_id: UUID) -> None:
    # The same row serializes different projects, resumes and retries on PostgreSQL.
    # Take this lock before project/task locks; hold through admission and commit.
    # NO KEY UPDATE still excludes another admission, but permits audit FK KEY
    # SHARE while archive_material owns the project row; FOR UPDATE deadlocks.
    await session.execute(
        select(User.id).where(User.id == user_id).with_for_update(key_share=True)
    )


async def admit_material(
    session: AsyncSession, user_id: UUID, student_id: UUID, *, size: int, project: bool
) -> None:
    active = (TaskStatus.PENDING, TaskStatus.RUNNING)
    pending = await session.scalar(
        select(func.count())
        .select_from(AnalysisTask)
        .where(
            AnalysisTask.created_by == user_id,
            AnalysisTask.task_type.in_(("resume_parse", "project_scan")),
            AnalysisTask.status.in_(active),
        )
    )
    if pending >= settings.material_pending_task_limit:
        raise AppError(
            "待处理材料已达上限，请等待完成或处理失败任务后重试", code=4291, status_code=429
        )
    originals = (
        select(func.coalesce(func.sum(ResumeVersion.size_bytes), 0))
        .join(Resume)
        .where(Resume.student_id == student_id)
        .scalar_subquery()
    )
    archives = select(
        func.coalesce(
            func.sum(func.coalesce(ProjectVersion.size_bytes, settings.max_archive_bytes)), 0
        )
    )
    archives = archives.join(Project).where(Project.student_id == student_id).scalar_subquery()
    extracted = (
        select(func.coalesce(func.sum(ProjectFile.size_bytes), 0))
        .join(ProjectVersion)
        .join(Project)
        .where(Project.student_id == student_id)
        .scalar_subquery()
    )
    reserved = (
        select(func.count())
        .select_from(ProjectVersion)
        .join(Project)
        .join(AnalysisTask, ProjectVersion.analysis_task_id == AnalysisTask.id)
        .where(Project.student_id == student_id, AnalysisTask.status.in_(active))
        .scalar_subquery()
    )
    # One statement snapshot: a finishing parser must not disappear between the
    # extraction sum and reservation count, temporarily undercounting its bytes.
    total = await session.scalar(
        select(
            originals
            + archives
            + extracted
            + size
            + (reserved + int(project)) * settings.max_extracted_bytes
        )
    )
    if total > settings.material_storage_limit_bytes:
        raise AppError(
            "材料容量及解析预留空间已达上限，请联系管理员核对容量", code=4131, status_code=413
        )


@asynccontextmanager
async def persisted_upload(session, storage, key: str, content: bytes, session_factory):
    """A failed transaction must not leave its newly owned original file behind."""
    try:
        storage.save(key, content)
        yield
    except BaseException:
        await session.rollback()
        # COMMIT may have succeeded before a connection error reached the caller.
        async with session_factory() as check:
            resume = await check.scalar(
                select(ResumeVersion.id).where(ResumeVersion.storage_key == key).limit(1)
            )
            project = await check.scalar(
                select(ProjectVersion.id).where(ProjectVersion.archive_storage_key == key).limit(1)
            )
        if resume is None and project is None:
            storage.resolve(key).unlink(missing_ok=True)
        raise
