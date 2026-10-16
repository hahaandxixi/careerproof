"""Shared login limits: no identity exemption, no permanent account mutation."""

import asyncio
import os
import subprocess
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.tests.test_ai_request_attempt_migration import attempt_pg as attempt_pg
from app.tests.test_auth import PASSWORD
from app.tests.test_auth import auth_db as auth_db


async def test_http_repeated_login_is_temporarily_limited(auth_db):  # noqa: F811
    app, _ = auth_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        payload = {"email": "missing@example.com", "password": "incorrect-synthetic"}
        for _ in range(5):
            assert (await c.post("/api/v1/auth/login", json=payload)).status_code == 401
        denied = await c.post("/api/v1/auth/login", json=payload)
        assert denied.status_code == 429
        assert 1 <= int(denied.headers["Retry-After"]) <= 300
        assert denied.json()["code"] == 4293
        assert "set-cookie" not in denied.headers


async def test_success_clears_pair_but_not_source_and_does_not_disable_user(auth_db):  # noqa: F811
    from app.models.identity import User
    from app.models.login_limit import LoginLimit

    app, factory = auth_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        account = {"email": "demo-rate@example.com", "password": PASSWORD}
        assert (await c.post("/api/v1/auth/register", json={
            **account, "displayName": "Synthetic", "role": "student",
        })).status_code == 201
        for _ in range(4):
            assert (await c.post("/api/v1/auth/login", json={
                **account, "password": "incorrect-synthetic",
            })).status_code == 401
        assert (await c.post("/api/v1/auth/login", json=account)).status_code == 200
        async with factory() as session:
            assert (await session.scalar(select(User))).is_active
            rows = (await session.scalars(select(LoginLimit))).all()
            assert len(rows) == 1 and rows[0].scope == "source"
            assert rows[0].attempts == 5
        # Successful login restored the pair allowance, without an identity exemption.
        for _ in range(5):
            assert (await c.post("/api/v1/auth/login", json={
                **account, "password": "incorrect-synthetic",
            })).status_code == 401
        assert (await c.post("/api/v1/auth/login", json=account)).status_code == 429
        async with factory() as session:
            assert (await session.scalar(select(User))).is_active


async def test_forged_forwarded_headers_cannot_change_application_bucket(auth_db):  # noqa: F811
    app, _ = auth_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for index in range(6):
            response = await c.post("/api/v1/auth/login", json={
                "email": "forged@example.com", "password": "incorrect-synthetic",
            }, headers={"X-Forwarded-For": f"192.0.2.{index}", "X-Real-IP": f"198.51.100.{index}"})
            assert response.status_code == (401 if index < 5 else 429)


async def test_source_bucket_limits_rotating_emails_and_unknown_client(auth_db, monkeypatch):  # noqa: F811
    app, _ = auth_db
    monkeypatch.setattr(settings, "login_source_limit", 3)
    async with AsyncClient(transport=ASGITransport(app=app, client=None),
                           base_url="http://test") as c:
        for index in range(4):
            response = await c.post("/api/v1/auth/login", json={
                "email": f"missing{index}@example.com", "password": "incorrect-synthetic",
            })
            assert response.status_code == (401 if index < 3 else 429)


async def test_database_failure_does_not_bypass_admission_or_leak_sql(auth_db, monkeypatch):  # noqa: F811
    from sqlalchemy.exc import OperationalError

    from app.services.login_limit import LoginLimiter

    async def unavailable(*_args):
        raise OperationalError("sensitive SQL", {}, RuntimeError("private connection details"))

    monkeypatch.setattr(LoginLimiter, "admit", unavailable)
    app, _ = auth_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/api/v1/auth/login", json={
            "email": "missing@example.com", "password": "incorrect-synthetic",
        })
        assert response.status_code == 503 and response.json()["code"] == 5033
        assert "private" not in response.text and "SQL" not in response.text
        assert "set-cookie" not in response.headers


async def exercise_shared_limit(factory, monkeypatch):
    from app.core.exceptions import AppError
    from app.models.login_limit import LoginLimit
    from app.services.login_limit import LoginLimiter

    monkeypatch.setattr(settings, "login_pair_limit", 3)
    clock = [1_800_000_000]
    monkeypatch.setattr("app.services.login_limit.time.time", lambda: clock[0])

    async def admit():
        async with factory() as session:
            await LoginLimiter(session).admit("race@example.com", "192.0.2.1")

    results = await asyncio.gather(*(admit() for _ in range(8)), return_exceptions=True)
    assert sum(r is None for r in results) == 3
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(failures) == 5 and all(isinstance(r, AppError) for r in failures)
    assert all(r.status_code == 429 for r in failures)
    async with factory() as session:
        rows = (await session.scalars(select(LoginLimit))).all()
        assert sorted(row.attempts for row in rows) == [3, 8]
        assert all("race" not in row.key_hash and len(row.key_hash) == 64 for row in rows)
    # A different service/session still sees the same limit; it survives rollback/close.
    with pytest.raises(AppError):
        await admit()
    # Another source can authenticate the same account: no global account lock.
    async with factory() as session:
        await LoginLimiter(session).admit("RACE@example.com", "192.0.2.2")
    # Automatic expiry restores allowance; no sleep and no account writes.
    clock[0] += settings.login_pair_window_seconds
    renewed = await asyncio.gather(*(admit() for _ in range(8)), return_exceptions=True)
    assert sum(r is None for r in renewed) == 3
    assert all(r is None or isinstance(r, AppError) for r in renewed)


async def test_source_cap_is_atomic_and_does_not_reserve_extra_pairs(auth_db, monkeypatch):  # noqa: F811
    from app.core.exceptions import AppError
    from app.models.login_limit import LoginLimit
    from app.services.login_limit import LoginLimiter

    _, factory = auth_db
    monkeypatch.setattr(settings, "login_source_limit", 3)

    async def admit(index):
        async with factory() as session:
            await LoginLimiter(session).admit(f"rotating{index}@example.com", "192.0.2.5")

    results = await asyncio.gather(*(admit(i) for i in range(8)), return_exceptions=True)
    assert sum(r is None for r in results) == 3
    assert all(r is None or isinstance(r, AppError) for r in results)
    async with factory() as session:
        rows = (await session.scalars(select(LoginLimit))).all()
        assert len(rows) == 4
        assert sum(row.attempts for row in rows if row.scope == "source") == 3


async def test_sqlite_independent_sessions_share_limit_and_expiry(auth_db, monkeypatch):  # noqa: F811
    _, factory = auth_db
    await exercise_shared_limit(factory, monkeypatch)


async def test_pg_independent_sessions_share_limit_and_expiry(attempt_pg, monkeypatch):  # noqa: F811
    from app.models.login_limit import LoginLimit

    engine, _ = attempt_pg
    async with engine.begin() as c:
        await c.run_sync(LoginLimit.__table__.create)
    await exercise_shared_limit(async_sessionmaker(engine, expire_on_commit=False), monkeypatch)


async def test_pg_separate_processes_share_admission(attempt_pg):  # noqa: F811
    from app.models.login_limit import LoginLimit

    engine, schema = attempt_pg
    async with engine.begin() as c:
        await c.run_sync(LoginLimit.__table__.create)
    env = {**os.environ, "LOGIN_TEST_SCHEMA": schema, "LOGIN_PAIR_LIMIT": "3"}
    code = """
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.services.login_limit import LoginLimiter
from app.core.exceptions import AppError
async def main():
    schema = os.environ['LOGIN_TEST_SCHEMA']
    engine = create_async_engine(os.environ['CAREERPROOF_TEST_DATABASE_URL'],
        hide_parameters=True, connect_args={'server_settings': {'search_path': schema}})
    try:
        async with async_sessionmaker(engine)() as session:
            assert await session.scalar(text('SELECT current_schema()')) == schema
            await session.rollback()
            try:
                await LoginLimiter(session).admit('process@example.com', '192.0.2.19')
                print('allowed')
            except AppError as error:
                assert error.status_code == 429
                print('limited')
    finally:
        await engine.dispose()
asyncio.run(main())
"""
    children = []
    try:
        for _ in range(6):
            children.append(subprocess.Popen(
                [sys.executable, "-c", code], env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ))
        results = await asyncio.gather(*(
            asyncio.to_thread(child.communicate, timeout=30) for child in children
        ))
        assert all(child.returncode == 0 for child in children), results
        assert sorted(stdout.strip() for stdout, _ in results) == [
            b"allowed", b"allowed", b"allowed", b"limited", b"limited", b"limited",
        ]
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()


def test_client_identity_normalization_and_no_proxy_header_launchers():
    from pathlib import Path

    from app.services.login_limit import canonical_source

    assert canonical_source("::ffff:192.0.2.1") == canonical_source("192.0.2.1")
    assert canonical_source(None) == canonical_source("not-an-ip") == "unknown"
    assert canonical_source("2001:db8:1:2::123") == canonical_source("2001:db8:1:2::456")
    root = Path(__file__).resolve().parents[3]
    assert "--no-proxy-headers" in (root / "Start-Local.ps1").read_text(encoding="utf-8")
    assert "--no-proxy-headers" in (root / "scripts/Start-E2E.ps1").read_text(encoding="utf-8")
    assert '"--no-proxy-headers"' in (root / "backend/Dockerfile").read_text(encoding="utf-8")
