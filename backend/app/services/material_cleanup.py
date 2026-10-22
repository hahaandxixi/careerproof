"""Delete only unreferenced extraction attempts after their worker has exited."""

import ctypes
import json
import os
import shutil
import time
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus
from app.models.portfolio import ProjectFile, ProjectVersion


def worker_running(pid: int) -> bool:
    if pid <= 0:
        return True
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            # Access denied is not evidence that a process has stopped.
            return kernel.GetLastError() != 87
        try:
            code = ctypes.c_ulong()
            return (
                not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
                or code.value == 259
            )
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def attempt_paths(storage, version_id: UUID, token: UUID) -> tuple[Path, Path]:
    raw = storage.base_dir / "projects" / "extracted" / str(version_id) / str(token)
    for part in (raw, *raw.parents):
        if part == storage.base_dir:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError("Linked extraction attempt is not safe to remove")
    directory = storage.resolve(f"projects/extracted/{version_id}/{token}")
    marker = directory.parent / f".{token}.worker.json"
    return directory, marker


async def cleanup_attempt(
    session,
    storage,
    version_id: UUID,
    token: UUID,
    *,
    worker_exited: bool = False,
    local_attempt: bool = False,
    apply: bool = True,
) -> str:
    try:
        directory, marker = attempt_paths(storage, version_id, token)
    except ValueError:
        return "linked-path"
    # The parser may have exited while its parent is still committing/indexing.
    # Lock the durable task first, then re-read references after that commit.
    task = await session.scalar(
        select(AnalysisTask)
        .join(ProjectVersion, ProjectVersion.analysis_task_id == AnalysisTask.id)
        .where(ProjectVersion.id == version_id)
        .with_for_update(of=AnalysisTask)
    )
    if (
        not worker_exited
        and not local_attempt
        and task
        and task.status == TaskStatus.RUNNING
        and task.run_token == token
    ):
        return "task-running"
    prefix = f"projects/extracted/{version_id}/{token}/"
    referenced = await session.scalar(
        select(ProjectFile.id)
        .where(ProjectFile.storage_key.startswith(prefix, autoescape=True))
        .limit(1)
    )
    if referenced:
        return "referenced"
    if not directory.exists() and not marker.exists():
        return "absent"
    if directory.is_symlink() or directory.is_junction():
        return "linked-path"
    if not worker_exited:
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
            if metadata["versionId"] != str(version_id) or metadata["runToken"] != str(token):
                return "unknown-worker"
            if worker_running(int(metadata["pid"])):
                return "worker-running"
        except (OSError, ValueError, KeyError, TypeError):
            return "unknown-worker"
    if not apply:
        return "eligible"
    # resolve() above confines the exact UUID path to storage. Never remove its parent.
    if directory.exists():
        shutil.rmtree(directory)
    marker.unlink(missing_ok=True)
    return "removed"


async def recover_extractions(
    session, storage, *, apply: bool = False, min_age_seconds: float = 3600
) -> list[dict]:
    """Dry-run by default. Old runs without a verifiable worker marker are retained."""
    base = storage.resolve("projects/extracted")
    results = []
    if not base.exists():
        return results
    for version_dir in base.iterdir():
        if version_dir.is_symlink() or version_dir.is_junction():
            continue
        try:
            version_id = UUID(version_dir.name)
        except ValueError:
            continue
        if not version_dir.is_dir():
            continue
        tokens = set()
        for entry in version_dir.iterdir():
            name = entry.name
            if name.startswith(".") and name.endswith(".worker.json"):
                name = name[1 : -len(".worker.json")]
            try:
                tokens.add(UUID(name))
            except ValueError:
                continue
        for token in tokens:
            try:
                directory, marker = attempt_paths(storage, version_id, token)
            except ValueError:
                results.append(
                    {"versionId": str(version_id), "runToken": str(token), "outcome": "linked-path"}
                )
                continue
            paths = [path for path in (directory, marker) if path.exists()]
            if (
                not paths
                or time.time() - max(path.stat().st_mtime for path in paths) < min_age_seconds
            ):
                continue
            outcome = await cleanup_attempt(session, storage, version_id, token, apply=apply)
            results.append(
                {"versionId": str(version_id), "runToken": str(token), "outcome": outcome}
            )
    return results
