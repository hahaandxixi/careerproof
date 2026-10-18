"""Independent PG sessions exercise upload replay and version allocation.

Only an explicit integration URL is accepted; matching_db owns a random schema.
These service-level cases do not run parsers or contact a model.
"""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.enums import UserRole
from app.models.identity import StudentProfile, User
from app.models.portfolio import Project, ProjectVersion
from app.repositories.portfolio import PortfolioRepository
from app.services.portfolio import PortfolioService

pytest_plugins = ["app.tests.test_real_matching"]
pytestmark = pytest.mark.skipif(
    not os.environ.get("CAREERPROOF_TEST_DATABASE_URL", "").startswith("postgresql+asyncpg://"),
    reason="requires an explicit isolated PostgreSQL integration database",
)


@pytest.mark.parametrize("mode", ["same-key", "conflicting-content", "different-keys"])
async def test_concurrent_project_uploads_serialize(matching_db, monkeypatch, mode):
    _app, factory = matching_db
    async with factory() as session:
        user = User(email=f"upload-{uuid4().hex}@example.test", password_hash="synthetic",
                    display_name="Synthetic", role=UserRole.STUDENT, is_active=True)
        session.add(user)
        await session.flush()
        student = StudentProfile(user_id=user.id, school="Synthetic", major="Software")
        session.add(student)
        await session.flush()
        project = Project(student_id=student.id, name="Concurrent synthetic upload")
        session.add(project)
        await session.commit()
        user_id, project_id = user.id, project.id

    # Both independent transactions reach the locking query before either proceeds.
    original = PortfolioRepository.owned_project
    ready = asyncio.Event()
    arrivals = 0

    async def synchronized(self, *args, **kwargs):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 10)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(PortfolioRepository, "owned_project", synchronized)
    key = uuid4()

    async def upload(index):
        async with factory() as session:
            current_user = await session.get(User, user_id)
            return await PortfolioService(session).create_project_version(
                project_id=project_id, filename="synthetic.txt",
                content=(b"different" if mode == "conflicting-content" and index else b"original"),
                current_user=current_user,
                request_id=(uuid4() if mode == "different-keys" else key),
            )

    results = await asyncio.wait_for(
        asyncio.gather(upload(0), upload(1), return_exceptions=True), 20,
    )
    failures = [result for result in results if isinstance(result, BaseException)]
    successes = [result for result in results if not isinstance(result, BaseException)]
    if mode == "conflicting-content":
        assert len(successes) == len(failures) == 1, results
        assert isinstance(failures[0], AppError), results
        assert failures[0].code == 4092
    else:
        assert not failures, results
        assert len(successes) == 2
        if mode == "same-key":
            assert successes[0][0].version_id == successes[1][0].version_id
            assert successes[0][0].task_id == successes[1][0].task_id
            assert sorted(result[1] for result in successes) == [False, True]
        else:
            assert successes[0][0].version_id != successes[1][0].version_id
            assert all(result[1] for result in successes)
    async with factory() as session:
        versions = list(await session.scalars(select(ProjectVersion).where(
            ProjectVersion.project_id == project_id).order_by(ProjectVersion.version_number)))
        assert [row.version_number for row in versions] == (
            [1, 2] if mode == "different-keys" else [1])
        assert await session.scalar(select(func.count()).select_from(ProjectVersion).where(
            ProjectVersion.project_id == project_id)) == len(versions)
