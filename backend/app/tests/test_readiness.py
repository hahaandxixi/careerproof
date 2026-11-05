import asyncio
from time import monotonic
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import health


@pytest.mark.asyncio
async def test_readiness_distinguishes_live_db_dispatcher_failure_and_staleness(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(health, "async_session_factory", async_sessionmaker(engine))
    application = FastAPI()
    application.include_router(health.router)
    application.state.recovery_task = SimpleNamespace(done=lambda: False)
    application.state.recovery_ok = True
    application.state.recovery_last_success = monotonic()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as c:
            assert (await c.get("/ready")).status_code == 200
            application.state.recovery_last_success -= 100
            stale = await c.get("/ready")
            assert stale.status_code == 503
            assert stale.json()["data"] == {
                "status": "not_ready",
                "database": True,
                "dispatcher": False,
            }
            application.state.recovery_last_success = monotonic()
            application.state.recovery_task = SimpleNamespace(done=lambda: True)
            assert (await c.get("/ready")).status_code == 503
            assert (await c.get("/health")).status_code == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["error", "timeout"])
async def test_dependency_failure_is_bounded_and_does_not_echo_secrets(monkeypatch, mode):
    class Session:
        async def __aenter__(self):
            if mode == "timeout":
                await asyncio.sleep(30)
            raise RuntimeError("SYNTHETIC_DATABASE_PASSWORD")

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(health, "async_session_factory", Session)
    application = FastAPI()
    application.include_router(health.router)
    started = monotonic()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        response = await c.get("/ready")
    assert monotonic() - started < 5
    assert response.status_code == 503
    assert response.json()["data"]["database"] is False
    assert "SYNTHETIC_DATABASE_PASSWORD" not in response.text


@pytest.mark.asyncio
async def test_recovery_health_records_success_failure_and_safe_error_class(monkeypatch, caplog):
    from app import main

    calls = []

    async def recovered(_factory):
        calls.append("recovered")

    async def dispatched(_factory):
        calls.append("dispatched")

    monkeypatch.setattr(main, "recover_interrupted_tasks", recovered)
    monkeypatch.setattr(main, "dispatch_pending_tasks", dispatched)
    application = FastAPI()
    await main._record_recovery(application)
    assert application.state.recovery_ok is True
    stamp = application.state.recovery_last_success
    assert calls == ["recovered", "dispatched"]

    async def failed(_factory):
        raise RuntimeError("SYNTHETIC_RECOVERY_SECRET")

    monkeypatch.setattr(main, "recover_interrupted_tasks", failed)
    await main._record_recovery(application)
    assert application.state.recovery_ok is False
    assert application.state.recovery_last_success == stamp
    assert calls == ["recovered", "dispatched"]
    assert "RuntimeError" in caplog.text
    assert "SYNTHETIC_RECOVERY_SECRET" not in caplog.text


@pytest.mark.asyncio
async def test_recovery_round_timeout_rolls_back_before_retry(monkeypatch, tmp_path):
    from app import main

    database = (tmp_path / "recovery-timeout.sqlite").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE recovery_probe (value INTEGER NOT NULL)"))
        await connection.execute(text("INSERT INTO recovery_probe VALUES (0)"))
    monkeypatch.setattr(main, "async_session_factory", factory)
    monkeypatch.setattr(main, "_RECOVERY_TIMEOUT_SECONDS", 0.1)
    entered = asyncio.Event()
    blocked = asyncio.Event()
    dispatches = []

    async def blocked_recovery(session_factory):
        async with session_factory() as session:
            await session.execute(text("UPDATE recovery_probe SET value = 1"))
            entered.set()
            await blocked.wait()
            await session.commit()

    async def dispatched(_factory):
        dispatches.append(True)

    monkeypatch.setattr(main, "recover_interrupted_tasks", blocked_recovery)
    monkeypatch.setattr(main, "dispatch_pending_tasks", dispatched)
    application = FastAPI()
    application.state.recovery_last_success = None
    try:
        async with asyncio.timeout(3):
            await main._record_recovery(application)
        assert entered.is_set()
        assert application.state.recovery_ok is False
        assert application.state.recovery_last_success is None
        assert dispatches == []
        async with factory() as session:
            assert await session.scalar(text("SELECT value FROM recovery_probe")) == 0

        async def recovered(session_factory):
            async with session_factory() as session:
                await session.execute(text("UPDATE recovery_probe SET value = 2"))
                await session.commit()

        monkeypatch.setattr(main, "recover_interrupted_tasks", recovered)
        await main._record_recovery(application)
        assert application.state.recovery_ok is True
        assert application.state.recovery_last_success is not None
        assert dispatches == [True]
        async with factory() as session:
            assert await session.scalar(text("SELECT value FROM recovery_probe")) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_lifespan_is_live_while_recovery_times_out_then_becomes_ready(monkeypatch):
    from app import main

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(health, "async_session_factory", async_sessionmaker(engine))
    monkeypatch.setattr(main, "_RECOVERY_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(main, "settings", SimpleNamespace(task_dispatch_interval_seconds=0.01))
    entered = asyncio.Event()
    blocked = asyncio.Event()
    recovered = asyncio.Event()
    rounds = []
    stopped = []

    async def recovering(_factory):
        rounds.append(True)
        if len(rounds) == 1:
            entered.set()
            await blocked.wait()

    async def dispatched(_factory):
        recovered.set()

    async def stop_dispatched():
        stopped.append(True)

    monkeypatch.setattr(main, "recover_interrupted_tasks", recovering)
    monkeypatch.setattr(main, "dispatch_pending_tasks", dispatched)
    monkeypatch.setattr(main, "stop_dispatched_tasks", stop_dispatched)
    application = FastAPI()
    application.include_router(health.router)
    try:
        async with asyncio.timeout(3), main.lifespan(application):
            await entered.wait()
            async with AsyncClient(
                transport=ASGITransport(app=application), base_url="http://test"
            ) as client:
                assert (await client.get("/health")).status_code == 200
                pending = await client.get("/ready")
                assert pending.status_code == 503
                assert pending.json()["data"]["dispatcher"] is False
                await recovered.wait()
                assert len(rounds) >= 2
                assert (await client.get("/ready")).status_code == 200
        assert application.state.recovery_task.done()
        assert application.state.recovery_ok is False
        assert stopped == [True]
    finally:
        await engine.dispose()
