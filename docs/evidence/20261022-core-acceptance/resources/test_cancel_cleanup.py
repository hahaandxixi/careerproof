"""Offline evidence probe; intentionally outside regular app/tests collection.

The real task, upload HTTP route, SQLite fixture, subprocess runner and cleanup
execute unchanged. Only the trusted processor is replaced with a child callable
which writes a partial attempt then blocks, making cancellation deterministic.
"""

import asyncio
import ctypes
import hashlib
import json
import os
import time
from ctypes import wintypes
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.analysis import AnalysisTask
from app.models.portfolio import ProjectFile, ProjectVersion
from app.services import portfolio as portfolio_service
from app.services import task_runner
from app.tests.test_portfolio_api import app_database as app_database
from app.tests.test_portfolio_api import project_zip
from app.tests.test_portfolio_api import student as student
from app.tools.storage import LocalStorage


ROOT = Path(__file__).resolve().parents[4]
ACCEPTED_BACKEND = ROOT / "backend/.tmp/core-acceptance-20261022/source/backend"


class NativeWorkerHandle:
    """Retain the exact child process object even after its launcher exits."""

    def __init__(self, pid):
        assert os.name == "nt", "this probe checks the Windows venv launcher case"
        self.pid = pid
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
            ctypes.POINTER(wintypes.FILETIME)
        ] * 4
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.OpenProcess(0x1000 | 0x100000 | 0x1, False, pid)
        assert self.handle, f"cannot retain the owned parser process: {ctypes.get_last_error()}"
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        assert self.kernel.GetProcessTimes(
            self.handle, ctypes.byref(created), ctypes.byref(exited),
            ctypes.byref(kernel), ctypes.byref(user),
        )
        self.creation_ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime

    def exit_code(self):
        if self.kernel.WaitForSingleObject(self.handle, 0) == 0x102:
            return None
        code = wintypes.DWORD()
        assert self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code))
        return code.value

    def close(self):
        # Failure cleanup addresses this held process object, never a reused PID.
        if self.kernel.WaitForSingleObject(self.handle, 1000) != 0:
            terminated = self.kernel.TerminateProcess(self.handle, 1)
            assert terminated or self.exit_code() is not None
            assert self.kernel.WaitForSingleObject(self.handle, 5000) == 0
        self.kernel.CloseHandle(self.handle)


def blocking_project_processor(source, destination, storage_base, *args, run_context=None):
    """Executed in app.services.isolated_worker, not a fake process or coroutine."""
    assert Path(source).is_file()
    assert Path(destination).is_relative_to(Path(storage_base))
    destination.mkdir(parents=True)
    marker = destination.parent / f".{destination.name}.worker.json"
    marker.write_text(json.dumps({**run_context, "pid": os.getpid()}), encoding="utf-8")
    (destination / "partial.txt").write_text("synthetic partial extraction", encoding="utf-8")
    while True:
        time.sleep(30)


async def wait_until(predicate, timeout=20):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_mode", ["cancel", "timeout"])
async def test_cancel_joins_real_worker_before_removing_only_its_attempt(
    student, app_database, monkeypatch, stop_mode,
):
    assert Path(portfolio_service.__file__).resolve().is_relative_to(ACCEPTED_BACKEND)
    assert settings.ai_external_enabled is False and settings.ai_provider == "mock"
    submitted = []

    def queue_only(self, background_tasks, function, *args):
        submitted.append((function, args))

    monkeypatch.setattr(task_runner.FastAPIBackgroundTaskRunner, "submit", queue_only)
    project = (await student.post("/api/v1/projects", json={"name": "cancel-cleanup-probe"}))
    assert project.status_code == 201, project.text
    project_id = project.json()["data"]["id"]

    async def upload(filename):
        response = await student.post(
            f"/api/v1/projects/{project_id}/versions",
            data={"requestId": str(uuid4())},
            files={"file": (filename, project_zip(), "application/zip")},
        )
        assert response.status_code == 202, response.text
        return response.json()["data"]

    # A real successful material has persisted ProjectFile references; it is not
    # just a similarly named directory pretending to be an accepted version.
    successful = await upload("successful.zip")
    await portfolio_service.execute_project_scan_task(
        UUID(successful["taskId"]), UUID(successful["versionId"])
    )
    async with portfolio_service.async_session_factory() as session:
        version = await session.get(ProjectVersion, UUID(successful["versionId"]))
        assert version.analysis_status == "completed"
        files = list(await session.scalars(select(ProjectFile).where(
            ProjectFile.project_version_id == version.id
        )))
        assert files
        successful_keys = [entry.storage_key for entry in files]
    storage = LocalStorage(settings.storage_base_dir)
    successful_bytes = {
        key: storage.resolve(key).read_bytes() for key in successful_keys
    }

    target = await upload("cancelled.zip")
    version_id = UUID(target["versionId"])
    task_id = UUID(target["taskId"])
    async with portfolio_service.async_session_factory() as session:
        target_version = await session.get(ProjectVersion, version_id)
        raw_key = target_version.archive_storage_key
    raw_bytes = storage.resolve(raw_key).read_bytes()
    target_parent = storage.resolve(f"projects/extracted/{version_id}")
    captured = []
    real_popen = task_runner.subprocess.Popen

    def capture_popen(*args, **kwargs):
        assert args[0][1:3] == ["-m", "app.services.isolated_worker"]
        process = real_popen(*args, **kwargs)
        captured.append(process)
        return process

    cleanup_events = []
    worker_handle = None
    original_cleanup = portfolio_service.cleanup_attempt

    async def audited_cleanup(session, current_storage, current_version_id, token, **kwargs):
        if current_version_id == version_id:
            assert len(captured) == 1
            child = captured[0]
            assert child.poll() is not None, "cleanup raced a still-running parser"
            assert worker_handle is not None, "actual child identity must be observed first"
            real_exit_code = worker_handle.exit_code()
            attempt = current_storage.resolve(f"projects/extracted/{version_id}/{token}")
            cleanup_events.append({
                "launcherPid": child.pid, "launcherReturnCodeBeforeCleanup": child.returncode,
                "workerPid": worker_handle.pid,
                "workerCreationTicks": worker_handle.creation_ticks,
                "actualWorkerExitCodeBeforeCleanup": real_exit_code,
                "attemptExistedBeforeCleanup": attempt.exists(),
            })
            Path(__file__).with_name("cancellation-observation.json").write_text(
                json.dumps(cleanup_events[-1], indent=2) + "\n", encoding="utf-8"
            )
            assert real_exit_code is not None, "cleanup raced the actual worker behind venv launcher"
            assert attempt.exists(), "worker must have written partial output before cancellation"
        result = await original_cleanup(
            session, current_storage, current_version_id, token, **kwargs
        )
        if current_version_id == version_id:
            cleanup_events[-1]["result"] = result
            cleanup_events[-1]["attemptExistsAfterCleanup"] = attempt.exists()
        return result

    monkeypatch.setattr(task_runner.subprocess, "Popen", capture_popen)
    monkeypatch.setattr(portfolio_service, "cleanup_attempt", audited_cleanup)
    monkeypatch.setattr(portfolio_service, "process_project", blocking_project_processor)
    if stop_mode == "timeout":
        monkeypatch.setattr(settings, "task_timeout_seconds", 3)
    execution = asyncio.create_task(portfolio_service.execute_project_scan_task(task_id, version_id))
    try:
        await wait_until(lambda: target_parent.exists() and any(target_parent.glob("*/partial.txt")))
        assert len(captured) == 1 and captured[0].poll() is None
        partial = next(target_parent.glob("*/partial.txt"))
        worker_metadata = json.loads(
            (target_parent / f".{partial.parent.name}.worker.json").read_text(encoding="utf-8")
        )
        assert worker_metadata["versionId"] == str(version_id)
        assert worker_metadata["runToken"] == partial.parent.name
        worker_handle = NativeWorkerHandle(worker_metadata["pid"])
        assert worker_handle.exit_code() is None
        if stop_mode == "cancel":
            execution.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(execution, timeout=15)
        else:
            await asyncio.wait_for(execution, timeout=15)
            async with portfolio_service.async_session_factory() as session:
                timed_out = await session.get(AnalysisTask, task_id)
                assert timed_out.status.value == "failed"
                assert "超时" in timed_out.error_message
        assert captured[0].poll() is not None
        assert cleanup_events and cleanup_events[0]["result"] == "removed"
        assert cleanup_events[0]["attemptExistsAfterCleanup"] is False
        assert not partial.parent.exists()
        assert not list(target_parent.glob(".*.worker.json"))
        assert storage.resolve(raw_key).read_bytes() == raw_bytes
        assert all(storage.resolve(k).read_bytes() == v for k, v in successful_bytes.items())
        async with portfolio_service.async_session_factory() as session:
            retained = list(await session.scalars(select(ProjectFile).where(
                ProjectFile.project_version_id == UUID(successful["versionId"])
            )))
            assert {entry.storage_key for entry in retained} == set(successful_keys)
        evidence = {
            "acceptedBackend": str(ACCEPTED_BACKEND),
            "portfolioSourceSha256": hashlib.sha256(
                Path(portfolio_service.__file__).read_bytes()
            ).hexdigest(),
            "actualWorkerHandleFromOwnedMarker": True,
            "stopMode": stop_mode,
            "cancellationPropagated": stop_mode == "cancel",
            "timeoutPersistedAsFailedTask": stop_mode == "timeout",
            "cleanupEvents": cleanup_events,
            "rawArchivePreserved": True,
            "successfulReferencedFilesPreserved": len(successful_keys),
            "externalModelRequests": 0,
            "database": "fixture-owned temporary SQLite",
        }
        filename = "cancellation-result.json" if stop_mode == "cancel" else "timeout-result.json"
        Path(__file__).with_name(filename).write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(evidence, ensure_ascii=False))
    finally:
        if not execution.done():
            execution.cancel()
            try:
                await asyncio.wait_for(execution, timeout=15)
            except asyncio.CancelledError:
                pass
        for process in captured:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        if worker_handle is not None:
            worker_handle.close()
