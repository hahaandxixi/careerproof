"""OPS-01B: four real child-process hard stops with database-only recovery.

Each parametrised window spawns a real child worker executing the production
verification entry, blocks it inside one committed durable phase, and kills that
exact process (never a coroutine cancellation). Recovery reads only database
facts: no HTTP, no business analysis, no revival of the old task.

On Windows the venv ``python.exe`` is a launcher that spawns the real interpreter,
so the worker process is identified by the pid the child itself reported and is
verified down to its parent pid and OS creation time before termination.
"""

import asyncio
import ctypes
import json
import os
import re
import signal
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.enums import TaskStatus
from app.models.identity import User
from app.models.recruitment import Application
from app.services import application_verification as verification
from app.services.ai_request_attempts import AttemptContext, AttemptService
from app.tests.test_application_verification import case  # noqa: F401
from app.tests.test_b08_usage_accounting import reap
from app.tests.test_real_matching import matching_db  # noqa: F401

WORKER = Path(__file__).with_name("ops_hard_stop_worker.py")
PHASES = [
    "send_intent_committed",
    "response_observed",
    "receipt_committed",
    "ledger_committed",
]
HTTP_AT_HANG = {
    "send_intent_committed": 0,
    "response_observed": 1,
    "receipt_committed": 1,
    "ledger_committed": 1,
}
MARKER_TIMEOUT_SECONDS = 60.0
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0


def redact(text_value: str) -> str:
    return re.sub(r"postgresql\+asyncpg://[^\s\"']+", "postgresql+asyncpg://<redacted>",
                  text_value or "")


class WorkerProcess:
    """The exact process that executed the verification entry, open for inspection."""

    def __init__(self, pid: int):
        self.pid = pid
        self._kernel32 = None
        self._handle = None
        if sys.platform == "win32":
            self._kernel32 = ctypes.windll.kernel32
            self._kernel32.OpenProcess.restype = wintypes.HANDLE
            self._kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                                   wintypes.DWORD]
            self._handle = self._kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE | SYNCHRONIZE,
                False, pid,
            )
            if not self._handle:
                raise OSError(f"cannot open worker process {pid}")

    def _creation_filetime(self):
        creation, exit_time = wintypes.FILETIME(), wintypes.FILETIME()
        kernel_time, user_time = wintypes.FILETIME(), wintypes.FILETIME()
        self._kernel32.GetProcessTimes.restype = wintypes.BOOL
        self._kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        if not self._kernel32.GetProcessTimes(self._handle, ctypes.byref(creation),
                                              ctypes.byref(exit_time),
                                              ctypes.byref(kernel_time),
                                              ctypes.byref(user_time)):
            raise OSError("GetProcessTimes failed")
        return creation

    @property
    def creation_seconds(self) -> float:
        """Actual OS-level creation time; proves the pid is the child we spawned."""
        if sys.platform == "win32":
            stamp = ((self._creation_filetime().dwHighDateTime << 32)
                     | self._creation_filetime().dwLowDateTime)
            return stamp / 10_000_000 - 11_644_473_600
        fields = Path(f"/proc/{self.pid}/stat").read_text().rsplit(") ", 1)[1].split()
        with open("/proc/stat", encoding="ascii") as proc_stat:
            boot = next(int(line.split()[1]) for line in proc_stat
                        if line.startswith("btime"))
        return boot + int(fields[19]) / os.sysconf("SC_CLK_TCK")

    @property
    def parent_pid(self) -> int:
        if sys.platform == "win32":
            class PROCESS_BASIC_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("ExitStatus", ctypes.c_long),
                    ("PebBaseAddress", ctypes.c_void_p),
                    ("AffinityMask", ctypes.c_size_t),
                    ("BasePriority", ctypes.c_long),
                    ("UniqueProcessId", ctypes.c_void_p),
                    ("InheritedFromUniqueProcessId", ctypes.c_void_p),
                ]

            ntdll = ctypes.windll.ntdll
            ntdll.NtQueryInformationProcess.restype = ctypes.c_long
            ntdll.NtQueryInformationProcess.argtypes = [
                wintypes.HANDLE, ctypes.c_uint, ctypes.c_void_p, wintypes.ULONG,
                ctypes.POINTER(wintypes.ULONG),
            ]
            info = PROCESS_BASIC_INFORMATION()
            returned = wintypes.ULONG()
            status = ntdll.NtQueryInformationProcess(
                self._handle, 0, ctypes.byref(info), ctypes.sizeof(info),
                ctypes.byref(returned),
            )
            assert status == 0, "NtQueryInformationProcess failed"
            return info.InheritedFromUniqueProcessId
        stat = Path(f"/proc/{self.pid}/stat").read_text().rsplit(") ", 1)[1].split()
        return int(stat[1])

    def terminate_and_wait(self, timeout_seconds: float) -> int:
        """Real hard stop on this process; returns its actual exit code."""
        if sys.platform != "win32":
            os.kill(self.pid, signal.SIGKILL)
            _, status = os.waitpid(self.pid, 0)
            assert os.WIFSIGNALED(status)
            return 1
        self._kernel32.TerminateProcess.restype = wintypes.BOOL
        self._kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self._kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        self._kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                                      ctypes.POINTER(wintypes.DWORD)]
        assert self._kernel32.TerminateProcess(self._handle, 1)
        assert self._kernel32.WaitForSingleObject(
            self._handle, int(timeout_seconds * 1000)) == WAIT_OBJECT_0
        exit_code = wintypes.DWORD()
        assert self._kernel32.GetExitCodeProcess(self._handle, ctypes.byref(exit_code))
        return exit_code.value

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


async def wait_for_child_state(state_file: Path, wanted: str, child, log_file: Path):
    deadline = asyncio.get_running_loop().time() + MARKER_TIMEOUT_SECONDS
    while True:
        if state_file.exists():
            state = json.loads(state_file.read_text(encoding="utf-8"))
            if state.get("event") == wanted:
                return state
            if state.get("event") == "child_error":
                pytest.fail(f"hard-stop child failed: {redact(state.get('traceback', ''))}")
            if state.get("event") == "child_returned":
                pytest.fail(f"hard-stop child finished without blocking in {wanted}")
        if child.poll() is not None:
            pytest.fail(
                f"hard-stop child exited early with {child.returncode}: "
                f"{redact(log_file.read_text(encoding='utf-8', errors='replace'))}"
            )
        assert asyncio.get_running_loop().time() < deadline, f"child never reached {wanted}"
        await asyncio.sleep(0.05)


def http_count(counter_file: Path) -> int:
    return int(counter_file.read_text(encoding="utf-8")) if counter_file.exists() else 0


async def wait_for_locks_released(factory, user_id, task_id, attempt_id):
    """The killed child's row locks must be gone before any recovery runs."""
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        try:
            async with factory() as session:
                await session.scalar(select(User.id).where(
                    User.id == user_id).with_for_update(nowait=True, key_share=True))
                await session.scalar(select(AnalysisTask.id).where(
                    AnalysisTask.id == task_id).with_for_update(nowait=True, key_share=True))
                await session.scalar(select(AiRequestAttempt.id).where(
                    AiRequestAttempt.id == attempt_id).with_for_update(
                        nowait=True, key_share=True))
                await session.rollback()
            return
        except OperationalError:
            assert asyncio.get_running_loop().time() < deadline, (
                "child PostgreSQL row locks were never released"
            )
            await asyncio.sleep(0.1)


@pytest.mark.parametrize("phase", PHASES)
async def test_real_child_hard_stop_then_database_only_recovery(
    phase, case, tmp_path  # noqa: F811
):
    database_url = os.environ.get("CAREERPROOF_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip(
            "A real child-process hard stop needs an explicitly configured isolated "
            "PostgreSQL schema; SQLite cannot prove row-lock release across processes"
        )
    async with case.factory() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema)

    task_id = UUID((await case.start())["taskId"])
    async with case.factory() as session:
        for table in ("users", "analysis_tasks", "ai_request_attempts", "ai_usage_logs"):
            assert await session.scalar(text(
                "SELECT n.nspname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.oid=to_regclass(:table)"
            ), {"table": table}) == schema
        application = await session.get(Application, UUID(case.application_id))
        snapshot_digest = verification._digest(application.report_snapshot)

    nonce = uuid4().hex
    counter_file = tmp_path / f"http-count-{phase}.txt"
    state_file = tmp_path / f"child-state-{phase}.json"
    log_file = tmp_path / f"child-log-{phase}.txt"
    config_file = tmp_path / f"child-config-{phase}.json"
    config_file.write_text(json.dumps({
        "database_url": database_url,
        "schema": schema,
        "task_id": str(task_id),
        "phase": phase,
        "nonce": nonce,
        "counter_file": str(counter_file),
        "state_file": str(state_file),
    }), encoding="utf-8")
    spawn_time = time.time()
    with log_file.open("wb") as log_handle:
        child = subprocess.Popen(
            [sys.executable, "-u", str(WORKER), str(config_file)],
            cwd=str(WORKER.parents[2]), stdout=log_handle, stderr=subprocess.STDOUT,
        )
    try:
        state = await wait_for_child_state(state_file, "hanging", child, log_file)

        # Identity checks before the hard stop: the reported pid must be the live
        # worker we spawned (child of the interpreter process on Windows), with the
        # right nonce, phase, task, schema, creation time and physical HTTP count.
        worker = WorkerProcess(state["pid"])
        try:
            assert child.poll() is None
            assert worker.parent_pid == child.pid
            assert state["phase"] == phase and state["nonce"] == nonce
            assert state["task_id"] == str(task_id) and state["schema"] == schema
            creation = worker.creation_seconds
            assert spawn_time - 2 <= creation <= time.time()
            assert http_count(counter_file) == HTTP_AT_HANG[phase]
            assert http_count(counter_file) == state["http_count"]

            async with case.factory() as session:
                task = await session.get(AnalysisTask, task_id)
                assert task.status == TaskStatus.RUNNING and task.run_token is not None
                claim_token = task.run_token
                owner_id = task.created_by
                attempt = await session.scalar(select(AiRequestAttempt).where(
                    AiRequestAttempt.analysis_task_id == task_id))
                assert attempt is not None and str(attempt.id) == state["attempt_id"]
                ledger_at_hang = list(await session.scalars(select(AiUsageLog).where(
                    AiUsageLog.analysis_task_id == task_id)))
            if phase in ("send_intent_committed", "response_observed"):
                assert attempt.state == "in_flight" and attempt.response_digest is None
                assert attempt.usage_input_tokens is None and ledger_at_hang == []
            elif phase == "receipt_committed":
                assert attempt.state == "received_unbooked" and ledger_at_hang == []
            else:
                assert attempt.state == "booked"
            if phase in ("receipt_committed", "ledger_committed"):
                assert (attempt.usage_input_tokens, attempt.usage_output_tokens,
                        attempt.usage_cache_hit_tokens) == (123, 45, 17)
            if phase == "ledger_committed":
                assert [(row.input_tokens, row.output_tokens, row.cache_hit_tokens)
                        for row in ledger_at_hang] == [(123, 45, 17)]
            pre_kill = {
                "attempt_state": attempt.state,
                "ledger": [(row.input_tokens, row.output_tokens, row.cache_hit_tokens)
                           for row in ledger_at_hang],
            }

            # The hard stop itself: terminate exactly this worker process.
            exit_code = worker.terminate_and_wait(15)
            assert exit_code != 0, "a killed worker must report a real nonzero exit"
            child.wait(timeout=15)
        finally:
            worker.close()
        await wait_for_locks_released(case.factory, owner_id, task_id, attempt.id)
        assert http_count(counter_file) == HTTP_AT_HANG[phase]

        async with case.factory() as session:
            task = await session.get(AnalysisTask, task_id)
            assert task.status == TaskStatus.RUNNING and task.run_token == claim_token
            row = await session.get(AiRequestAttempt, attempt.id)
            ledger_after_kill = list(await session.scalars(select(AiUsageLog).where(
                AiUsageLog.analysis_task_id == task_id)))
            assert row.state == pre_kill["attempt_state"]
            assert [(item.input_tokens, item.output_tokens, item.cache_hit_tokens)
                    for item in ledger_after_kill] == pre_kill["ledger"]

        # Deterministically do what recover_interrupted_tasks does to an abandoned
        # lease, then reconcile twice with the original run_token/owner/provider/model.
        await reap(case.factory, str(task_id))
        context = AttemptContext(task_id, owner_id, claim_token, row.step,
                                 row.provider, row.model)
        service = AttemptService(case.factory, context)
        written_first = await service.reconcile()
        assert http_count(counter_file) == HTTP_AT_HANG[phase]
        written_second = await service.reconcile()
        assert http_count(counter_file) == HTTP_AT_HANG[phase]

        async with case.factory() as session:
            task = await session.get(AnalysisTask, task_id)
            assert task.status == TaskStatus.FAILED and task.run_token is None
            saved = task.input_snapshot
            assert saved.get("analysis") is None and saved.get("aiStatus") != "validated"
            row = await session.get(AiRequestAttempt, attempt.id)
            ledger = list(await session.scalars(select(AiUsageLog).where(
                AiUsageLog.analysis_task_id == task_id)))
            tasks = list(await session.scalars(select(AnalysisTask).where(
                AnalysisTask.task_type == "application_verification")))
            application = await session.get(Application, UUID(case.application_id))
        assert len(tasks) == 1, "recovery must never revive or recreate the old task"
        assert verification._digest(application.report_snapshot) == snapshot_digest

        summary = await service.summary()
        if phase in ("send_intent_committed", "response_observed"):
            assert (written_first, written_second) == (0, 0)
            assert row.state == "usage_unknown"
            assert row.reason == "worker_ended_without_receipt"
            assert row.usage_input_tokens is None and ledger == []
            assert summary["usageKnown"] is False
            assert summary["trustedReceiptCount"] == 0
            assert summary["unknownAttemptCount"] == 1 and summary["intentCount"] == 1
        elif phase == "receipt_committed":
            assert (written_first, written_second) == (1, 0)
            assert row.state == "booked"
            assert [(item.input_tokens, item.output_tokens, item.cache_hit_tokens)
                    for item in ledger] == [(123, 45, 17)]
            assert all(item.run_token == claim_token and item.request_seq == 1
                       and item.attempt_id == attempt.id for item in ledger)
            assert summary["usageKnown"] and summary["usageBooked"]
            assert (summary["inputTokens"], summary["outputTokens"],
                    summary["cacheHitTokens"]) == (123, 45, 17)
        else:
            assert (written_first, written_second) == (0, 0)
            assert row.state == "booked" and len(ledger) == 1
            assert summary["usageKnown"] and summary["usageBooked"]
            assert summary["trustedReceiptCount"] == 1
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=15)
