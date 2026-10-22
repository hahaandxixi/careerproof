"""Private Windows parser identity handshake; no uploaded content is executed."""

from __future__ import annotations

import ctypes
import json
import os
import time
from ctypes import wintypes
from pathlib import Path


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
        ctypes.POINTER(wintypes.FILETIME)
    ] * 4
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel


def _creation_ticks(kernel, handle) -> int:
    created, exited, spent, user = (wintypes.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(
        handle, ctypes.byref(created), ctypes.byref(exited),
        ctypes.byref(spent), ctypes.byref(user),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


class WindowsWorkerHandle:
    """A retained kernel process object, protected against numeric PID reuse."""

    def __init__(self, identity: dict, nonce: str):
        pid, created = identity.get("pid"), identity.get("creationTicks")
        if (
            identity.get("nonce") != nonce
            or type(pid) is not int or pid <= 0
            or type(created) is not int or created <= 0
        ):
            raise ValueError("Invalid private worker identity")
        self.kernel = _kernel()
        self.handle = self.kernel.OpenProcess(0x1000 | 0x100000 | 0x1, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if _creation_ticks(self.kernel, self.handle) != created:
                raise ValueError("Worker identity changed before admission")
        except BaseException:
            self.close()
            raise

    def terminate_and_wait(self) -> None:
        if self.kernel.WaitForSingleObject(self.handle, 0) != 0:
            # A venv launcher may already be terminating its child through a job.
            # TerminateProcess can then return false; the retained handle still
            # must become signaled before its material directory is safe to touch.
            self.kernel.TerminateProcess(self.handle, 1)
            if self.kernel.WaitForSingleObject(self.handle, 5000) != 0:
                raise TimeoutError("Parser worker exit could not be confirmed")

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def publish_identity(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle)
    temporary.replace(path)


def read_identity_record(path: Path) -> dict | None:
    """A transient local read denial is not admission; callers keep their deadline."""
    try:
        text = path.read_text(encoding="utf-8")
    except (PermissionError, FileNotFoundError):
        return None
    record = json.loads(text)
    if not isinstance(record, dict):
        raise ValueError("Private worker identity record must be an object")
    return record


def await_parent_admission(path: Path, nonce: str) -> None:
    """Publish before unpickling; parse only after the parent retained our handle."""
    kernel = _kernel()
    identity = {
        "pid": os.getpid(),
        "creationTicks": _creation_ticks(kernel, kernel.GetCurrentProcess()),
        "nonce": nonce,
    }
    publish_identity(path, identity)
    acknowledgment = path.with_suffix(".ack")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not path.parent.is_dir():
            raise RuntimeError("Parser parent abandoned startup")
        acknowledgment_record = read_identity_record(acknowledgment)
        if acknowledgment_record is not None:
            if acknowledgment_record != identity:
                raise RuntimeError("Parser parent acknowledgment does not match")
            return
        time.sleep(0.01)
    raise TimeoutError("Parser parent admission timed out")
