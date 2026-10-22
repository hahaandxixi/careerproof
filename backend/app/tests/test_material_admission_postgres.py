"""Actual PostgreSQL owner-lock admission; no worker or business database.

The shared fixture creates/drops its own cp_test_* schema. Independent sessions
enter each race together; service methods perform the real lock/check/commit.
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask
from app.models.audit import AuditLog
from app.models.enums import TaskStatus, UserRole
from app.models.identity import StudentProfile, User
from app.models.portfolio import Project, ProjectFile, ProjectVersion, ResumeVersion
from app.services import portfolio as portfolio_service
from app.services.portfolio import PortfolioService, retry_material_task
from app.services.task_lifecycle import claim_task, finish_task
from app.tests import test_real_matching as shared_matching
from app.tools.storage import LocalStorage

matching_db = shared_matching.matching_db
pytestmark = pytest.mark.skipif(
    not os.environ.get("CAREERPROOF_TEST_DATABASE_URL", "").startswith("postgresql+asyncpg://"),
    reason="requires an explicit isolated PostgreSQL integration database",
)
CONTENT = b"synthetic material content".ljust(40, b".")


async def _owner(factory):
    async with factory() as session:
        user = User(
            email=f"material-quota-{uuid4().hex}@example.test",
            password_hash="synthetic",
            display_name="synthetic owner",
            role=UserRole.STUDENT,
        )
        session.add(user)
        await session.flush()
        student = StudentProfile(user_id=user.id)
        session.add(student)
        await session.flush()
        projects = [Project(student_id=student.id, name=f"project {i}") for i in range(2)]
        session.add_all(projects)
        await session.commit()
        return user.id, [project.id for project in projects]


async def _upload(factory, owner, project, *, barrier=None, request=None):
    async with factory() as session:
        user = await session.get(User, owner)
        if barrier is not None:
            await barrier.wait()
        service = PortfolioService(session)
        if project is None:
            accepted = await service.create_resume_upload(
                title="resume", filename="resume.txt", mime_type="text/plain",
                content=CONTENT, current_user=user,
            )
            return accepted
        accepted, created = await service.create_project_version(
            project_id=project, filename="source.txt", content=CONTENT,
            current_user=user, request_id=request or uuid4(),
        )
        return accepted, created


async def _counts(factory):
    async with factory() as session:
        return {
            "projects": await session.scalar(select(func.count()).select_from(ProjectVersion)),
            "resumes": await session.scalar(select(func.count()).select_from(ResumeVersion)),
            "tasks": await session.scalar(select(func.count()).select_from(AnalysisTask)),
            "active": await session.scalar(select(func.count()).select_from(AnalysisTask).where(
                AnalysisTask.status.in_((TaskStatus.PENDING, TaskStatus.RUNNING)),
            )),
        }


async def _terminal(factory, accepted, status):
    async with factory() as session:
        token = await claim_task(session, accepted.task_id, step="synthetic owned run")
        assert token is not None
        assert await finish_task(
            session, accepted.task_id, token, status=status, step="synthetic terminal",
        )
        version = await session.get(ProjectVersion, accepted.version_id)
        version.analysis_status = "failed" if status == TaskStatus.FAILED else "completed"
        await session.commit()


def _limits(monkeypatch, *, pending=10, storage=10000):
    monkeypatch.setattr(settings, "max_extracted_bytes", 100)
    monkeypatch.setattr(settings, "material_pending_task_limit", pending)
    monkeypatch.setattr(settings, "material_storage_limit_bytes", storage)


@pytest.mark.parametrize("constraint", ["pending", "storage"])
@pytest.mark.parametrize("mixed", [False, True], ids=["different-projects", "resume-and-project"])
async def test_owner_quota_serializes_different_upload_targets(
    matching_db, monkeypatch, constraint, mixed,
):
    _, factory = matching_db
    owner, projects = await _owner(factory)
    # Every individual upload fits. Both together exceed exactly one quota.
    _limits(
        monkeypatch,
        pending=1 if constraint == "pending" else 10,
        storage=(179 if mixed else 279) if constraint == "storage" else 10000,
    )
    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _upload(factory, owner, projects[0], barrier=barrier),
        _upload(factory, owner, None if mixed else projects[1], barrier=barrier),
        return_exceptions=True,
    )
    errors = [result for result in outcomes if isinstance(result, AppError)]
    winners = [result for result in outcomes if not isinstance(result, BaseException)]
    assert len(errors) == len(winners) == 1, outcomes
    assert errors[0].code == (4291 if constraint == "pending" else 4131)
    counts = await _counts(factory)
    assert counts["projects"] + counts["resumes"] == counts["tasks"] == counts["active"] == 1


async def test_same_request_replay_at_both_limits_adds_no_reservation(matching_db, monkeypatch):
    _, factory = matching_db
    owner, projects = await _owner(factory)
    _limits(monkeypatch, pending=1, storage=140)
    request = uuid4()
    first, created = await _upload(factory, owner, projects[0], request=request)
    assert created
    barrier = asyncio.Barrier(2)
    replayed = await asyncio.gather(*(
        _upload(factory, owner, projects[0], request=request, barrier=barrier)
        for _ in range(2)
    ))
    assert all(not created for _, created in replayed)
    assert all(item.version_id == first.version_id for item, _ in replayed)
    assert all(item.task_id == first.task_id for item, _ in replayed)
    assert await _counts(factory) == {"projects": 1, "resumes": 0, "tasks": 1, "active": 1}


async def test_retry_and_new_upload_compete_for_one_owner_slot(matching_db, monkeypatch):
    _, factory = matching_db
    owner, projects = await _owner(factory)
    _limits(monkeypatch, pending=1)
    first, _ = await _upload(factory, owner, projects[0])
    await _terminal(factory, first, TaskStatus.FAILED)
    barrier = asyncio.Barrier(2)

    async def retry():
        async with factory() as session:
            user = await session.get(User, owner)
            await barrier.wait()
            accepted, _, _ = await retry_material_task(session, first.task_id, user)
            return accepted

    outcomes = await asyncio.gather(
        retry(), _upload(factory, owner, projects[1], barrier=barrier),
        return_exceptions=True,
    )
    errors = [result for result in outcomes if isinstance(result, AppError)]
    winners = [result for result in outcomes if not isinstance(result, BaseException)]
    assert len(errors) == len(winners) == 1, outcomes
    assert errors[0].code == 4291
    counts = await _counts(factory)
    assert counts["active"] == 1
    assert counts["tasks"] == counts["projects"] in (1, 2)
    async with factory() as session:
        old = await session.get(ProjectVersion, first.version_id)
        assert old.size_bytes == len(CONTENT)
        storage = LocalStorage(settings.storage_base_dir)
        assert storage.resolve(old.archive_storage_key).read_bytes() == CONTENT


async def test_failure_releases_pending_and_extraction_but_keeps_original_bytes(
    matching_db, monkeypatch,
):
    _, factory = matching_db
    owner, projects = await _owner(factory)
    _limits(monkeypatch, storage=220)
    first, _ = await _upload(factory, owner, projects[0])
    with pytest.raises(AppError) as blocked:
        await _upload(factory, owner, projects[1])
    assert blocked.value.code == 4131
    await _terminal(factory, first, TaskStatus.FAILED)
    second, _ = await _upload(factory, owner, projects[1])
    # 80 original bytes + 100 outstanding extraction bytes fit. Retrying adds
    # another 100 reserved bytes, and must still be rejected (not undercounted).
    async with factory() as session:
        user = await session.get(User, owner)
        with pytest.raises(AppError) as retry_blocked:
            await retry_material_task(session, first.task_id, user)
        assert retry_blocked.value.code == 4131
    counts = await _counts(factory)
    assert counts == {"projects": 2, "resumes": 0, "tasks": 2, "active": 1}
    async with factory() as session:
        storage = LocalStorage(settings.storage_base_dir)
        for accepted in (first, second):
            version = await session.get(ProjectVersion, accepted.version_id)
            assert storage.resolve(version.archive_storage_key).read_bytes() == CONTENT
        assert (await session.get(AnalysisTask, first.task_id)).status == TaskStatus.FAILED


async def test_successful_extracted_bytes_remain_charged_and_files_preserved(
    matching_db, monkeypatch,
):
    _, factory = matching_db
    owner, projects = await _owner(factory)
    _limits(monkeypatch)
    first, _ = await _upload(factory, owner, projects[0])
    await _terminal(factory, first, TaskStatus.COMPLETED)
    storage = LocalStorage(settings.storage_base_dir)
    key = f"projects/extracted/{first.version_id}/{uuid4()}/main.py"
    storage.save(key, b"print()")
    async with factory() as session:
        session.add(ProjectFile(
            project_version_id=first.version_id, relative_path="main.py", content_hash="a" * 64,
            size_bytes=7, line_count=1, storage_key=key, analysis_status="completed",
        ))
        await session.commit()
    # 40 retained original + 7 extracted + a new (40 + 100) = 187.
    monkeypatch.setattr(settings, "material_storage_limit_bytes", 186)
    with pytest.raises(AppError) as blocked:
        await _upload(factory, owner, projects[1])
    assert blocked.value.code == 4131
    assert storage.resolve(key).read_bytes() == b"print()"
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProjectFile)) == 1
    assert await _counts(factory) == {"projects": 1, "resumes": 0, "tasks": 1, "active": 0}


async def test_archive_audit_and_upload_do_not_deadlock_on_owner_lock(matching_db, monkeypatch):
    """Archive holds project first, upload owner first; FK checks must coexist.

    The barriers observe the actual service locks. A full owner FOR UPDATE lock
    cycles with the audit insert's FK KEY SHARE; NO KEY UPDATE still serializes
    uploads while allowing that independent FK check to finish.
    """
    _, factory = matching_db
    owner, projects = await _owner(factory)
    _limits(monkeypatch)
    project_locked, owner_locked = asyncio.Event(), asyncio.Event()
    actual_owner_lock = portfolio_service.lock_material_owner

    async def observe_owner_lock(session, user_id):
        await actual_owner_lock(session, user_id)
        owner_locked.set()

    monkeypatch.setattr(portfolio_service, "lock_material_owner", observe_owner_lock)

    async def archive():
        async with factory() as session:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            user = await session.get(User, owner)
            actual_scalar = session.scalar

            async def pause_after_project_lock(*args, **kwargs):
                result = await actual_scalar(*args, **kwargs)
                if isinstance(result, Project):
                    project_locked.set()
                    await asyncio.wait_for(owner_locked.wait(), 5)
                return result

            monkeypatch.setattr(session, "scalar", pause_after_project_lock)
            return await PortfolioService(session).archive_material(
                "project", projects[0], True, user,
            )

    async def upload():
        await asyncio.wait_for(project_locked.wait(), 5)
        return await _upload(factory, owner, projects[0])

    outcomes = await asyncio.wait_for(
        asyncio.gather(archive(), upload(), return_exceptions=True), 15,
    )
    assert all(not isinstance(result, BaseException) for result in outcomes), outcomes
    async with factory() as session:
        assert (await session.get(Project, projects[0])).is_archived is True
        assert await session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "material.archive",
            AuditLog.resource_id == str(projects[0]),
        )) == 1
        assert await session.scalar(select(func.count()).select_from(ProjectVersion)) == 1
