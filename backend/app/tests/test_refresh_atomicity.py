"""Real independent transactions: one successor, rollback, unrelated sessions intact."""

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import Base
from app.core.exceptions import AppError
from app.models.enums import UserRole
from app.models.identity import RefreshToken, StudentProfile, User
from app.repositories.users import UserRepository
from app.services.auth import AuthService
from app.tests.test_ai_request_attempt_migration import attempt_pg as attempt_pg
from app.tests.test_auth import auth_db as auth_db


async def exercise(factory, monkeypatch):
    async with factory() as session:
        user = User(email="rotation-proof@example.com", password_hash="synthetic-no-login",
                    display_name="synthetic", role=UserRole.STUDENT)
        session.add(user)
        await session.flush()
        original = await AuthService(session)._issue_tokens(user)
        other_device = await AuthService(session)._issue_tokens(user)
        await session.commit()
    # Force the old SELECT-then-UPDATE implementation to expose its race.
    # An atomic UPDATE does not use this read hook, and needs no artificial yield.
    read = UserRepository.get_active_refresh_token
    ready = asyncio.Event()
    arrived = 0

    async def both_read(self, digest):
        nonlocal arrived
        row = await read(self, digest)
        if row:
            arrived += 1
            if arrived == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), 10)
        return row

    async def rotate():
        async with factory() as session:
            return await AuthService(session).refresh(original.refresh_token)

    with monkeypatch.context() as patch:
        patch.setattr(UserRepository, "get_active_refresh_token", both_read)
        results = await asyncio.gather(rotate(), rotate(), return_exceptions=True)
    winners = [r for r in results if not isinstance(r, BaseException)]
    losers = [r for r in results if isinstance(r, BaseException)]
    assert len(winners) == len(losers) == 1
    assert isinstance(losers[0], AppError) and losers[0].status_code == 401
    assert losers[0].code == 4015  # Rejected, but possibly a normal in-flight race.
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RefreshToken).where(
            RefreshToken.revoked_at.is_(None))) == 2
        # Neither a race loser nor replay may revoke an unrelated device.
        await AuthService(session).refresh(other_device.refresh_token)
        await AuthService(session).refresh(winners[0].refresh_token)


async def test_sqlite_refresh_one_successor_and_other_device_survives(auth_db, monkeypatch):  # noqa: F811
    _app, factory = auth_db
    await exercise(factory, monkeypatch)


async def test_pg_refresh_one_successor_and_other_device_survives(attempt_pg, monkeypatch):  # noqa: F811
    engine, _schema = attempt_pg
    async with engine.begin() as c:
        await c.run_sync(lambda conn: Base.metadata.create_all(
            conn, tables=[User.__table__, StudentProfile.__table__, RefreshToken.__table__]))
    await exercise(async_sessionmaker(engine, expire_on_commit=False), monkeypatch)


async def test_failed_issue_rolls_back_consumption(auth_db, monkeypatch):  # noqa: F811
    _app, factory = auth_db
    async with factory() as session:
        user = User(email="rollback-proof@example.com", password_hash="synthetic-no-login",
                    display_name="synthetic", role=UserRole.STUDENT)
        session.add(user)
        await session.flush()
        initial = await AuthService(session)._issue_tokens(user)
        await session.commit()

    async def fail(*_args):
        raise RuntimeError("synthetic issue failure")

    with monkeypatch.context() as patch:
        patch.setattr(AuthService, "_issue_tokens", fail)
        async with factory() as session:
            with pytest.raises(RuntimeError, match="synthetic issue"):
                await AuthService(session).refresh(initial.refresh_token)
    async with factory() as session:
        assert (await AuthService(session).refresh(initial.refresh_token)).user.id == user.id
