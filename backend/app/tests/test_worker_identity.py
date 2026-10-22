"""Private worker protocol regression; trusted synthetic callables only."""

import asyncio
import json
import os
import pickle
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import task_runner, worker_identity
from app.services.worker_identity import WindowsWorkerHandle, publish_identity


async def test_normal_worker_finishes_and_removes_private_identity_directory(monkeypatch):
    paths = []
    original = task_runner.tempfile.TemporaryDirectory

    def capture_directory(*args, **kwargs):
        directory = original(*args, **kwargs)
        paths.append(Path(directory.name))
        return directory

    monkeypatch.setattr(task_runner.tempfile, "TemporaryDirectory", capture_directory)
    assert await task_runner.run_isolated(str, 17, timeout_seconds=5) == "17"
    assert all(not path.exists() for path in paths)


async def test_posix_branch_keeps_original_private_pickle_command(monkeypatch):
    # Run the non-Windows branch even when this regression is executed on Windows;
    # this checks branch behavior, not an assertion that the OS itself is Linux.
    monkeypatch.setattr(task_runner, "os", SimpleNamespace(name="posix"))
    calls = []
    original = task_runner.subprocess.Popen

    def capture(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(task_runner.subprocess, "Popen", capture)
    assert await task_runner.run_isolated(str, 23, timeout_seconds=5) == "23"
    assert calls == [[sys.executable, "-m", "app.services.isolated_worker"]]


@pytest.mark.parametrize("identity", [
    {"pid": 1, "creationTicks": 1, "nonce": "wrong"},
    {"pid": True, "creationTicks": 1, "nonce": "expected"},
    {"pid": 1, "creationTicks": 0, "nonce": "expected"},
])
def test_invalid_identity_is_rejected_before_opening_any_process(identity):
    with pytest.raises(ValueError, match="private worker identity"):
        WindowsWorkerHandle(identity, "expected")


def test_reused_pid_creation_time_is_rejected_and_handle_closed(monkeypatch):
    closed = []
    fake = SimpleNamespace(OpenProcess=lambda *args: 7, CloseHandle=closed.append)
    monkeypatch.setattr(worker_identity, "_kernel", lambda: fake)
    monkeypatch.setattr(worker_identity, "_creation_ticks", lambda *args: 123)
    with pytest.raises(ValueError, match="identity changed"):
        WindowsWorkerHandle({"pid": 1, "creationTicks": 124, "nonce": "expected"}, "expected")
    assert closed == [7]


def test_stale_acknowledgment_cannot_admit_worker(tmp_path, monkeypatch):
    fake = SimpleNamespace(GetCurrentProcess=lambda: 7)
    monkeypatch.setattr(worker_identity, "_kernel", lambda: fake)
    monkeypatch.setattr(worker_identity, "_creation_ticks", lambda *args: 123)
    destination = tmp_path / "worker.json"
    destination.with_suffix(".ack").write_text(
        json.dumps({"pid": os.getpid(), "creationTicks": 123, "nonce": "stale"})
    )
    with pytest.raises(RuntimeError, match="acknowledgment does not match"):
        worker_identity.await_parent_admission(destination, "current")


def test_failed_identity_publication_cannot_execute_even_trusted_callable(tmp_path):
    marker = tmp_path / "must-not-run"
    # Parent creates a private directory in normal operation. Missing publication
    # directory is an explicit failure and must precede pickle deserialization.
    result = subprocess.run(
        [sys.executable, "-m", "app.services.isolated_worker", "--identity",
         str(tmp_path / "absent" / "worker.json"), "synthetic-nonce"],
        input=pickle.dumps((Path.touch, (marker,), {})),
        capture_output=True, timeout=5,
    )
    assert result.returncode != 0
    assert not marker.exists()


def test_private_identity_publication_is_atomic_and_leaves_no_temporary_file(tmp_path):
    destination = tmp_path / "worker.json"
    publish_identity(destination, {"pid": os.getpid(), "nonce": "synthetic"})
    assert destination.exists()
    assert not destination.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("transient_read", [None, PermissionError, FileNotFoundError])
async def test_second_cancellation_waits_for_complete_teardown_and_preserves_first(
    monkeypatch, transient_read,
):
    """Deterministic control-flow test; native-process proof is a separate probe."""
    events = []
    launcher_wait_started = asyncio.Event()
    launcher_release = asyncio.Event()
    communication_release = asyncio.Event()
    identity_reads = []

    class MemoryPath:
        def __init__(self, *args):
            pass

        def __truediv__(self, value):
            return self

        def exists(self):
            return True

        def read_text(self, **kwargs):
            identity_reads.append(True)
            if transient_read is not None and len(identity_reads) <= 2:
                raise transient_read("synthetic private identity transient read")
            return '{"nonce":"expected"}'

        def with_suffix(self, value):
            return self

        def __str__(self):
            return "memory-only"

    class Process:
        returncode = None

        def poll(self):
            return self.returncode

        def kill(self):
            events.append("launcher_killed")
            self.returncode = 1

        def communicate(self, *args, **kwargs):
            raise AssertionError("No actual I/O in memory control-flow test")

        def wait(self):
            raise AssertionError("No actual I/O in memory control-flow test")

    process = Process()

    class Worker:
        def __init__(self, *args):
            events.append("worker_retained")

        def terminate_and_wait(self):
            events.append("actual_worker_joined")
            communication_release.set()

        def close(self):
            events.append("handle_closed")

    async def fake_thread(function, *args, **kwargs):
        if function == process.communicate:
            await communication_release.wait()
            return b"", None
        if function == process.wait:
            events.append("launcher_wait_started")
            launcher_wait_started.set()
            await launcher_release.wait()
            return 1
        return function(*args, **kwargs)

    asynchronous = SimpleNamespace(**{
        name: getattr(asyncio, name) for name in (
            "get_running_loop", "create_task", "shield", "wait_for", "sleep", "CancelledError"
        )
    }, to_thread=fake_thread)
    monkeypatch.setattr(task_runner, "asyncio", asynchronous)
    monkeypatch.setattr(task_runner, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(task_runner, "Path", MemoryPath)
    monkeypatch.setattr(task_runner, "uuid4", lambda: SimpleNamespace(hex="expected"))
    monkeypatch.setattr(task_runner, "tempfile", SimpleNamespace(
        TemporaryDirectory=lambda **kwargs: SimpleNamespace(
            name="memory-only", cleanup=lambda: events.append("identity_removed")
        )
    ))
    monkeypatch.setattr(task_runner, "subprocess", SimpleNamespace(
        Popen=lambda *args, **kwargs: process,
        PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL,
        CREATE_NO_WINDOW=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        TimeoutExpired=subprocess.TimeoutExpired,
    ))
    monkeypatch.setattr(task_runner, "WindowsWorkerHandle", Worker)
    monkeypatch.setattr(task_runner, "publish_identity", lambda *args: events.append("admitted"))
    task = asyncio.create_task(task_runner.run_isolated(str, 1, timeout_seconds=5))
    try:
        async with asyncio.timeout(1):
            while "admitted" not in events:
                await asyncio.sleep(0)
        task.cancel("first cancellation")
        await asyncio.wait_for(launcher_wait_started.wait(), 1)
        task.cancel("second cancellation")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done(), "second cancellation interrupted teardown"
        assert "actual_worker_joined" not in events
        launcher_release.set()
        with pytest.raises(asyncio.CancelledError, match="first cancellation"):
            await task
        assert events[-3:] == ["actual_worker_joined", "handle_closed", "identity_removed"]
        assert len(identity_reads) == (1 if transient_read is None else 3)
    finally:
        launcher_release.set()
        communication_release.set()
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.parametrize("read_error", [PermissionError, FileNotFoundError])
def test_transient_acknowledgment_read_retries_within_existing_deadline(
    tmp_path, monkeypatch, read_error,
):
    fake = SimpleNamespace(GetCurrentProcess=lambda: 7)
    monkeypatch.setattr(worker_identity, "_kernel", lambda: fake)
    monkeypatch.setattr(worker_identity, "_creation_ticks", lambda *args: 123)
    destination = tmp_path / "worker.json"
    acknowledgment = destination.with_suffix(".ack")
    acknowledgment.write_text(json.dumps({
        "pid": os.getpid(), "creationTicks": 123, "nonce": "current"
    }))
    original_read = Path.read_text
    reads = []
    clock = [0.0]

    def read(path, **kwargs):
        if path == acknowledgment:
            reads.append(True)
            if len(reads) <= 2:
                raise read_error("synthetic transient private ack read")
        return original_read(path, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(worker_identity, "time", SimpleNamespace(
        monotonic=lambda: clock[0], sleep=lambda delay: clock.__setitem__(0, clock[0] + delay)
    ))
    worker_identity.await_parent_admission(destination, "current")
    assert len(reads) == 3
    assert clock[0] == 0.02


@pytest.mark.parametrize("read_error", [PermissionError, FileNotFoundError])
def test_permanent_acknowledgment_read_cannot_extend_deadline(
    tmp_path, monkeypatch, read_error,
):
    fake = SimpleNamespace(GetCurrentProcess=lambda: 7)
    monkeypatch.setattr(worker_identity, "_kernel", lambda: fake)
    monkeypatch.setattr(worker_identity, "_creation_ticks", lambda *args: 123)
    destination = tmp_path / "worker.json"
    acknowledgment = destination.with_suffix(".ack")
    acknowledgment.write_text("{}")
    original_read = Path.read_text
    clock = [0.0]

    def read(path, **kwargs):
        if path == acknowledgment:
            raise read_error("synthetic permanent private ack read")
        return original_read(path, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(worker_identity, "time", SimpleNamespace(
        monotonic=lambda: clock[0], sleep=lambda delay: clock.__setitem__(0, clock[0] + delay)
    ))
    with pytest.raises(TimeoutError, match="parent admission timed out"):
        worker_identity.await_parent_admission(destination, "current")
    assert 10 <= clock[0] <= 10.02


def test_corrupt_acknowledgment_is_not_retried_as_transient(tmp_path, monkeypatch):
    fake = SimpleNamespace(GetCurrentProcess=lambda: 7)
    monkeypatch.setattr(worker_identity, "_kernel", lambda: fake)
    monkeypatch.setattr(worker_identity, "_creation_ticks", lambda *args: 123)
    destination = tmp_path / "worker.json"
    destination.with_suffix(".ack").write_text("corrupt-json")
    with pytest.raises(json.JSONDecodeError):
        worker_identity.await_parent_admission(destination, "current")
