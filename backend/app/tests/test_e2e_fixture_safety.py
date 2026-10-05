"""Isolation and idempotency regressions for the E2E fixture seeder (evals/seed_e2e.py).

Everything runs on temporary SQLite through the in-process ASGI app; the guard and
manifest tests are pure or file-based with a fake process probe. No business database
row is ever read, no network is used and the conftest autouse fixture keeps
AI_EXTERNAL_ENABLED=false / AI_PROVIDER=mock.
"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.main import create_app
from app.models.identity import User
from app.models.notification import Notification
from app.models.recruitment import Application, ApplicationEvent
from evals.seed_e2e import (
    DEFAULT_STATE_DIR,
    IsolationError,
    _windows_process_started_at,
    assert_run_database,
    expected_database_name,
    guard_base_url,
    guard_database_url,
    guard_run_id,
    load_startup_manifest,
    normalized_snapshot_hash,
    seed_fixture,
    verify_startup_manifest,
)

RUN_ID = "e2e-card01"
SLOTS = ("A", "B", "A2")


@pytest.fixture
async def e2e_app(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'e2e.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection, _record):
        connection.create_function(
            "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
        )
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[t for t in Base.metadata.sorted_tables if t.name != "knowledge_chunks"],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = session_override
    try:
        yield app, factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def run_seed(app, factory, tmp_path, run_id=RUN_ID, verify_only=False):
    transport = ASGITransport(app=app)

    def client_factory() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://127.0.0.1/api/v1")

    return await seed_fixture(
        client_factory,
        factory,
        run_id=run_id,
        state_path=Path(tmp_path) / "state" / f"{run_id}.json",
        storage_dir=Path(tmp_path) / "storage",
        verify_only=verify_only,
    )


async def load_state(tmp_path, run_id=RUN_ID):
    return json.loads((Path(tmp_path) / "state" / f"{run_id}.json").read_text(encoding="utf-8"))


async def fixture_counts(factory):
    async with factory() as session:
        return {
            "users": await session.scalar(select(func.count()).select_from(User)),
            "applications": await session.scalar(select(func.count()).select_from(Application)),
            "events": await session.scalar(select(func.count()).select_from(ApplicationEvent)),
            "notifications": await session.scalar(select(func.count()).select_from(Notification)),
        }


async def withdraw_as(app, state, student_key, slot):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1/api/v1"
    ) as client:
        response = await client.post(
            "/auth/login",
            json={
                "email": state["accounts"][student_key]["email"],
                "password": state["accounts"][student_key]["password"],
            },
        )
        assert response.status_code == 200, response.text
        return await client.post(f"/applications/{state['applications'][slot]['id']}/withdraw")


def test_database_url_guard_rejects_business_remote_and_foreign_targets():
    for bad in (
        "postgresql+asyncpg://careerproof:careerproof@127.0.0.1:5432/careerproof",
        "postgresql+asyncpg://u:p@127.0.0.1:5432/cp_test_abc123",
        "postgresql+asyncpg://u:p@db.internal.example.com:5432/cp_e2e_r1",
        "postgresql+asyncpg://u:p@10.0.0.8:5432/cp_e2e_r1",
        "sqlite+aiosqlite:///tmp/cp_e2e_r1.db",
        # Query/fragment could override connection parameters; never accepted.
        "postgresql+asyncpg://u:p@127.0.0.1:5432/cp_e2e_r1?sslmode=require",
        "postgresql+asyncpg://u:p@127.0.0.1:5432/cp_e2e_r1#fragment",
    ):
        with pytest.raises(IsolationError):
            guard_database_url(bad)
    with pytest.raises(IsolationError) as exc_info:
        guard_database_url("postgresql+asyncpg://u:sekret@10.0.0.8:5432/cp_e2e_r1")
    # The refusal must never leak the connection string credentials.
    assert "sekret" not in str(exc_info.value)
    assert guard_database_url("postgresql+asyncpg://u:p@127.0.0.1:5432/cp_e2e_r1") == "cp_e2e_r1"
    assert guard_database_url("postgresql+asyncpg://u:p@localhost:5432/cp_e2e_r1") == "cp_e2e_r1"
    assert guard_database_url("postgresql+asyncpg://u:p@[::1]:5432/cp_e2e_r1") == "cp_e2e_r1"


def test_seeding_requires_the_exact_run_database_name():
    assert expected_database_name("e2e-card01") == "cp_e2e_e2e-card01"
    with pytest.raises(IsolationError):
        assert_run_database("cp_e2e_other-run", "e2e-card01")
    assert assert_run_database("cp_e2e_e2e-card01", "e2e-card01") == "cp_e2e_e2e-card01"


def test_base_url_guard_rejects_business_ports_and_malformed_targets():
    for bad in (
        "http://127.0.0.1:8000/api/v1",  # the business backend port
        "http://127.0.0.1:3000/api/v1",
        "http://10.0.0.5:8001/api/v1",
        "http://localhost.evil.com:8001/api/v1",
        "https://127.0.0.1:8001/api/v1",
        "http://u:p@127.0.0.1:8001/api/v1",  # userinfo
        "http://127.0.0.1:8001/api/v1?debug=1",
        "http://127.0.0.1:8001/api/v1#frag",
        "http://127.0.0.1:8001/",  # wrong path
        "http://127.0.0.1:8001/api/v2",
        "http://[fe80::1]:8001/api/v1",  # IPv6 but not loopback
    ):
        with pytest.raises(IsolationError):
            guard_base_url(bad)
    assert guard_base_url("http://127.0.0.1:8001/api/v1/") == "http://127.0.0.1:8001/api/v1"
    assert guard_base_url("http://localhost:8001/api/v1") == "http://localhost:8001/api/v1"
    # The rebuilt URL must keep IPv6 brackets instead of producing http://::1:8001.
    assert guard_base_url("http://[::1]:8001/api/v1") == "http://[::1]:8001/api/v1"


def test_run_id_guard():
    for bad in ("UPPER", "e2e_card01", "", "a" * 33, "../escape"):
        with pytest.raises(IsolationError):
            guard_run_id(bad)
    assert guard_run_id("e2e-card01") == "e2e-card01"


def _manifest(tmp_path, **overrides):
    manifest = {
        "runId": RUN_ID,
        "createdAt": datetime.now(UTC).isoformat(),
        "backendPort": 8001,
        "frontendPort": 3001,
        "databaseName": "cp_e2e_e2e-card01",
        "storageDir": str(Path(tmp_path) / "storage"),
        "distDir": ".next-e2e",
        "aiExternalEnabled": "false",
        "aiProvider": "mock",
        "backend": {
            "id": 424242,
            "startedAt": datetime.now(UTC).isoformat(),
            "needle": "python.exe",
        },
        "processes": [],
    }
    manifest.update(overrides)
    return manifest


def test_startup_manifest_verification_binds_pid_database_storage_and_mock(tmp_path):
    def matching_probe(pid):
        return datetime.fromisoformat(_manifest(tmp_path)["backend"]["startedAt"])

    assert verify_startup_manifest(
        _manifest(tmp_path),
        run_id=RUN_ID,
        database_name="cp_e2e_e2e-card01",
        storage_dir=Path(tmp_path) / "storage",
        process_probe=matching_probe,
    )["id"] == 424242
    # A dead or reused PID refuses the seed.
    with pytest.raises(IsolationError):
        verify_startup_manifest(
            _manifest(tmp_path),
            run_id=RUN_ID,
            database_name="cp_e2e_e2e-card01",
            storage_dir=Path(tmp_path) / "storage",
            process_probe=lambda pid: None,
        )
    stale = _manifest(tmp_path)
    stale["backend"]["startedAt"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with pytest.raises(IsolationError):
        verify_startup_manifest(
            stale,
            run_id=RUN_ID,
            database_name="cp_e2e_e2e-card01",
            storage_dir=Path(tmp_path) / "storage",
            process_probe=matching_probe,
        )
    # Any manifest drift (run id, database, storage, AI mode, port) refuses.
    for key, value in (
        ("runId", "e2e-other02"),
        ("databaseName", "careerproof"),
        ("storageDir", str(Path(tmp_path) / "other-storage")),
        ("aiExternalEnabled", "true"),
        ("aiProvider", "deepseek"),
        ("backendPort", 8000),
    ):
        with pytest.raises(IsolationError):
            verify_startup_manifest(
                _manifest(tmp_path, **{key: value}),
                run_id=RUN_ID,
                database_name="cp_e2e_e2e-card01",
                storage_dir=Path(tmp_path) / "storage",
                process_probe=matching_probe,
            )


def test_missing_startup_manifest_refuses_before_any_connection(tmp_path):
    with pytest.raises(IsolationError):
        load_startup_manifest(Path(tmp_path) / "state" / "processes-e2e-card01.json")


def test_startup_manifest_accepts_powershell_utf8_bom_and_rejects_invalid_json(tmp_path):
    # Windows PowerShell 5 `Set-Content -Encoding utf8` writes a BOM; plain
    # utf-8 (PowerShell 7 / byte writer) must keep working too.
    raw = json.dumps(_manifest(tmp_path)).encode("utf-8")
    path = Path(tmp_path) / "processes-e2e-card01.json"
    path.write_bytes(b"\xef\xbb\xbf" + raw)
    assert load_startup_manifest(path)["backend"]["id"] == 424242
    path.write_bytes(raw)
    assert load_startup_manifest(path)["runId"] == RUN_ID
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(IsolationError):
        load_startup_manifest(path)
    path.write_bytes(b"\xef\xbb\xbf[1,2]")
    with pytest.raises(IsolationError):  # a JSON array is not a manifest
        load_startup_manifest(path)


def test_startup_manifest_parses_dotnet_roundtrip_timestamps(tmp_path):
    # Start-E2E.ps1 records StartTime.ToUniversalTime().ToString('o'): seven
    # fraction digits and a trailing Z. Verification must accept that form and
    # still refuse garbage.
    manifest = _manifest(tmp_path)
    manifest["backend"]["startedAt"] = "2026-10-04T12:00:00.1234567Z"
    probe_time = datetime(2026, 10, 4, 12, 0, 0, 123456, tzinfo=UTC)
    assert (
        verify_startup_manifest(
            manifest,
            run_id=RUN_ID,
            database_name="cp_e2e_e2e-card01",
            storage_dir=Path(tmp_path) / "storage",
            process_probe=lambda pid: probe_time,
        )["id"]
        == 424242
    )
    manifest["backend"]["startedAt"] = "not-a-timestamp"
    with pytest.raises(IsolationError):
        verify_startup_manifest(
            manifest,
            run_id=RUN_ID,
            database_name="cp_e2e_e2e-card01",
            storage_dir=Path(tmp_path) / "storage",
            process_probe=lambda pid: probe_time,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows-only ctypes process probe")
def test_windows_process_probe_reports_live_and_exited_pids():
    # Real ctypes evidence on 64-bit Windows: a live PID yields its UTC creation
    # time through the HANDLE-sized signatures...
    started = _windows_process_started_at(os.getpid())
    assert started is not None
    assert started.tzinfo is not None
    assert timedelta(0) <= datetime.now(UTC) - started < timedelta(hours=1)
    # ...and an exited-but-unreaped child (Popen keeps its handle, so the PID
    # stays reserved and OpenProcess succeeds) is detected through its exit
    # status instead of being mistaken for a live backend.
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    deadline = time.monotonic() + 10
    while child.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert child.returncode is not None
    assert _windows_process_started_at(child.pid) is None


async def test_cli_refusals_happen_before_any_http_or_database_call(tmp_path, monkeypatch):
    """Business API/database targets and a missing manifest refuse at the CLI
    level before an engine or HTTP client could exist (review 2026-10-05)."""
    import evals.seed_e2e as seed_module

    def forbidden(*args, **kwargs):
        raise AssertionError("a refusal must fire before any engine or client exists")

    monkeypatch.setattr(seed_module, "create_async_engine", forbidden)
    monkeypatch.setattr(seed_module.httpx, "AsyncClient", forbidden)
    monkeypatch.setenv(
        "E2E_DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:5432/cp_e2e_e2e-card01"
    )
    monkeypatch.setenv("E2E_STORAGE_DIR", str(tmp_path / "storage"))
    base = [
        "--run-id",
        RUN_ID,
        "--base-url",
        "http://127.0.0.1:8001/api/v1",
        "--manifest-dir",
        str(tmp_path),
    ]
    for extra in (
        ["--database-url", "postgresql+asyncpg://u:p@127.0.0.1:5432/careerproof"],
        ["--base-url", "http://127.0.0.1:8000/api/v1"],
        [],  # valid targets but no startup manifest under the temp manifest dir
    ):
        args = seed_module.build_parser().parse_args(base + extra)
        with pytest.raises(IsolationError):
            await seed_module._async_main(args)


async def test_seed_creates_two_students_three_frozen_deliveries_and_notifications(
    e2e_app, tmp_path
):
    app, factory = e2e_app
    result = await run_seed(app, factory, tmp_path)
    assert result["mode"] == "created"
    state = await load_state(tmp_path)
    assert set(state["accounts"]) == {"student", "studentA2", "enterprise"}
    counts = await fixture_counts(factory)
    # Three users, three deliveries, one submitted event each, two notices per event
    # (one for the delivering student, one for the enterprise manager).
    assert counts == {"users": 3, "applications": 3, "events": 3, "notifications": 6}
    # Citation fidelity: each frozen snapshot cites the real line in the stored file.
    for slot, student_key in (("A", "student"), ("B", "student"), ("A2", "studentA2")):
        material = state["materials"][student_key]
        stored = (Path(tmp_path) / "storage" / material["storageKey"]).read_bytes()
        lines = stored.decode("utf-8").splitlines()
        async with factory() as session:
            row = await session.get(Application, UUID(state["applications"][slot]["id"]))
            evidence = row.report_snapshot["items"][0]["evidenceList"][0]
            cited = lines[
                evidence["lineStart"] - 1 : evidence["lineEnd"]
            ]
            assert cited == [evidence["snippet"]]
            assert evidence["contentHash"] == material["contentHash"]
            assert normalized_snapshot_hash(row.report_snapshot) == state["applications"][slot][
                "snapshotSha256"
            ]
    async with factory() as session:
        rows = list(await session.scalars(select(Application).order_by(Application.created_at)))
        materials_by_slot = {
            slot: row.report_snapshot["materials"][0]["id"]
            for slot, row in zip(SLOTS, rows, strict=False)
        }
        # Same-item citation: reports A and B of one student share one resume version,
        # while student A2 owns a different version with a different content hash.
        assert materials_by_slot["A"] == materials_by_slot["B"]
        assert materials_by_slot["A2"] != materials_by_slot["A"]
        assert state["materials"]["student"]["resumeVersionId"] == materials_by_slot["A"]
        assert state["materials"]["studentA2"]["contentHash"] != state["materials"]["student"][
            "contentHash"
        ]
    # A same-run-id replay is read-only: nothing new, everything still frozen.
    before = await fixture_counts(factory)
    replay = await run_seed(app, factory, tmp_path)
    assert replay["mode"] == "verified"
    assert replay["withdrawnRestored"] is False
    assert await fixture_counts(factory) == before


async def test_rerun_after_withdraw_keeps_a2_and_b_without_restoring(e2e_app, tmp_path):
    app, factory = e2e_app
    await run_seed(app, factory, tmp_path)
    state = await load_state(tmp_path)
    assert (await withdraw_as(app, state, "student", "A")).status_code == 200
    after_withdraw = await fixture_counts(factory)
    replay = await run_seed(app, factory, tmp_path)
    assert replay["mode"] == "verified"
    assert replay["applications"]["A"]["status"] == "withdrawn"
    assert replay["applications"]["A"]["enterpriseBoardVisible"] is False
    # Withdrawing A leaves the same-job delivery A2 and the other job B readable.
    assert replay["applications"]["A2"]["status"] == "submitted"
    assert replay["applications"]["A2"]["enterpriseBoardVisible"] is True
    assert replay["applications"]["B"]["status"] == "submitted"
    assert replay["applications"]["B"]["enterpriseBoardVisible"] is True
    # The replay is read-only even around a withdrawn delivery.
    assert await fixture_counts(factory) == after_withdraw
    async with factory() as session:
        row = await session.get(Application, UUID(state["applications"]["A"]["id"]))
        assert row.status == "withdrawn"


async def test_verify_only_refuses_without_state_and_state_mismatch_refuses(e2e_app, tmp_path):
    app, factory = e2e_app
    with pytest.raises(IsolationError):
        await run_seed(app, factory, tmp_path, verify_only=True)
    await run_seed(app, factory, tmp_path)
    # A state file from another run id must not be adopted either.
    state_path = Path(tmp_path) / "state" / "e2e-other02.json"
    state_path.write_text(json.dumps(await load_state(tmp_path)), encoding="utf-8")
    transport = ASGITransport(app=app)

    def client_factory() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://127.0.0.1/api/v1")

    with pytest.raises(IsolationError):
        await seed_fixture(
            client_factory,
            factory,
            run_id="e2e-other02",
            state_path=state_path,
            storage_dir=Path(tmp_path) / "storage",
        )


async def test_deleted_state_file_blocks_account_adoption(e2e_app, tmp_path):
    app, factory = e2e_app
    await run_seed(app, factory, tmp_path)
    (Path(tmp_path) / "state" / f"{RUN_ID}.json").unlink()
    with pytest.raises(IsolationError):
        await run_seed(app, factory, tmp_path)
    counts = await fixture_counts(factory)
    assert counts["users"] == 3 and counts["applications"] == 3


async def test_credentials_never_reach_stdout_and_state_dir_stays_ignored(
    e2e_app, tmp_path, capsys
):
    app, factory = e2e_app
    await run_seed(app, factory, tmp_path)
    state = await load_state(tmp_path)
    captured = capsys.readouterr()
    for role in ("student", "studentA2", "enterprise"):
        password = state["accounts"][role]["password"]
        assert password not in captured.out
        assert password not in captured.err
    # The default state directory lives under the gitignored backend/.tmp tree.
    assert DEFAULT_STATE_DIR.name == "e2e"
    assert DEFAULT_STATE_DIR.parent.name == ".tmp"


def test_snapshot_hash_is_canonical_and_stable():
    snapshot = {"b": 1, "a": "中文"}
    assert normalized_snapshot_hash(snapshot) == normalized_snapshot_hash({"a": "中文", "b": 1})
    assert len(normalized_snapshot_hash(snapshot)) == 64


class _FakeAsyncpgConnection:
    """Offline stand-in for asyncpg.Connection: records calls, must be closed."""

    def __init__(self, *, exists=False, fail_execute=False):
        self._exists = exists
        self._fail_execute = fail_execute
        self.closed = False
        self.executed: list[str] = []

    async def fetchval(self, query, *args):
        assert "pg_database" in query
        return 1 if self._exists else None

    async def execute(self, query):
        self.executed.append(query)
        if self._fail_execute:
            raise RuntimeError("simulated CREATE DATABASE failure")

    async def close(self):
        assert not self.closed, "close() must not be awaited twice"
        self.closed = True


async def test_create_database_closes_on_every_branch_and_keeps_exceptions(monkeypatch):
    """Review round 3: asyncpg.Connection has close(), not aclose(); created,
    already-exists and execute-failure paths must all close the connection, and
    the execute failure must surface unchanged instead of being replaced."""
    import sys
    import types

    from evals.seed_e2e import create_database

    seen_dsns: list[str] = []

    def install(connection: _FakeAsyncpgConnection) -> None:
        async def fake_connect(dsn):
            seen_dsns.append(dsn)
            return connection

        monkeypatch.setitem(sys.modules, "asyncpg", types.SimpleNamespace(connect=fake_connect))

    url = "postgresql+asyncpg://u:sekret@127.0.0.1:5432/cp_e2e_e2e-card01"

    created = _FakeAsyncpgConnection()
    install(created)
    assert await create_database(url, RUN_ID) is True
    assert created.closed is True
    assert created.executed == ['CREATE DATABASE "cp_e2e_e2e-card01"']

    existing = _FakeAsyncpgConnection(exists=True)
    install(existing)
    assert await create_database(url, RUN_ID) is False
    assert existing.closed is True
    assert existing.executed == []

    failing = _FakeAsyncpgConnection(fail_execute=True)
    install(failing)
    with pytest.raises(RuntimeError, match="simulated CREATE DATABASE failure"):
        await create_database(url, RUN_ID)
    assert failing.closed is True

    # The maintenance connection targets the postgres database on loopback and
    # never the isolated run database; the run name only appears in CREATE.
    assert seen_dsns == [dsn for dsn in seen_dsns if dsn.startswith("postgresql://")]
    assert {dsn.rsplit("/", 1)[-1] for dsn in seen_dsns} == {"postgres"}
