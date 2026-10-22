from __future__ import annotations

import asyncio
import os
import pickle
import subprocess
import sys
import tempfile
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4
from weakref import WeakKeyDictionary

from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.worker_identity import (
    WindowsWorkerHandle,
    publish_identity,
    read_identity_record,
)

_limits: WeakKeyDictionary = WeakKeyDictionary()


async def run_bounded(function: Callable[..., Awaitable[None]], *args: Any) -> None:
    loop = asyncio.get_running_loop()
    limit = _limits.setdefault(loop, asyncio.Semaphore(settings.task_concurrency))
    async with limit:
        await function(*args)


async def run_isolated(
    function: Callable[..., Any],
    *args: Any,
    timeout_seconds: float | None = None,
    **kwargs: Any,
) -> Any:
    """Run trusted parsing code in a killable process; never execute uploaded code.

    Only top-level Python callables are supported. The pickle IPC is private and
    contains server-generated arguments, not a client-supplied pickle payload.
    """
    payload = pickle.dumps((function, args, kwargs))
    identity_directory = tempfile.TemporaryDirectory(prefix="careerproof-parser-") if (
        os.name == "nt"
    ) else None
    identity_path = Path(identity_directory.name) / "worker.json" if identity_directory else None
    nonce = uuid4().hex
    command = [sys.executable, "-m", "app.services.isolated_worker"]
    if identity_path:
        command.extend(["--identity", str(identity_path), nonce])
    # Uvicorn --reload uses Windows' SelectorEventLoop, which cannot create
    # asyncio subprocesses. Popen + a bounded background thread works on both
    # event-loop policies; the parser itself still runs in a separate process.
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except BaseException:
        if identity_directory:
            identity_directory.cleanup()
        raise
    communication = asyncio.create_task(
        asyncio.to_thread(
            process.communicate,
            payload,
            timeout=timeout_seconds or settings.task_timeout_seconds,
        )
    )
    worker = None
    identity_task = None

    async def retain_worker():
        deadline = asyncio.get_running_loop().time() + min(
            10, timeout_seconds or settings.task_timeout_seconds
        )
        while asyncio.get_running_loop().time() < deadline:
            identity = read_identity_record(identity_path)
            if identity is not None:
                return WindowsWorkerHandle(identity, nonce), identity
            if communication.done():
                communication.result()
                raise AppError("文件处理进程启动失败，请稍后重试", code=4025)
            await asyncio.sleep(0.01)
        raise subprocess.TimeoutExpired(command, timeout_seconds or settings.task_timeout_seconds)

    try:
        if identity_path:
            identity_task = asyncio.create_task(retain_worker())
            worker, identity = await asyncio.shield(identity_task)
            # No await between retaining the exact process and publishing admission.
            publish_identity(identity_path.with_suffix(".ack"), identity)
        stdout, _ = await asyncio.shield(communication)
        if process.returncode != 0:
            raise AppError("文件处理进程异常退出，请稍后重试", code=4025)
        result = pickle.loads(stdout)
        if not result["ok"]:
            raise AppError(result["message"], code=result["code"])
        return result["value"]
    except subprocess.TimeoutExpired as exc:
        raise AppError("处理超时，已终止解析进程；请精简文件后重试", code=4026) from exc
    finally:
        original_error = sys.exception()

        async def shutdown():
            nonlocal worker
            try:
                if process.poll() is None:
                    process.kill()
                await asyncio.to_thread(process.wait)
                if identity_task is not None and worker is None:
                    # An unacknowledged child cannot run the parser. Retain its
                    # handle if publication won the startup cancellation race.
                    try:
                        worker, _ = await asyncio.wait_for(asyncio.shield(identity_task), 1)
                    except (Exception, asyncio.CancelledError):
                        if not identity_task.done():
                            identity_task.cancel()
                if worker is not None:
                    await asyncio.to_thread(worker.terminate_and_wait)
                with suppress(subprocess.TimeoutExpired):
                    await communication
            finally:
                if worker is not None:
                    worker.close()
                if identity_directory:
                    identity_directory.cleanup()

        # Cancellation of this caller must never cancel teardown after an admitted
        # parser exists. Repeated cancel() calls are postponed until all joins and
        # handle/control-file cleanup finish, retaining the first cancellation.
        teardown = asyncio.create_task(shutdown())
        later_cancellation = None
        while not teardown.done():
            try:
                await asyncio.shield(teardown)
            except asyncio.CancelledError as cancellation:
                if later_cancellation is None:
                    later_cancellation = cancellation
        teardown.result()
        if later_cancellation is not None and not isinstance(
            original_error, asyncio.CancelledError
        ):
            raise later_cancellation


class TaskRunner(Protocol):
    def submit(
        self,
        background_tasks: BackgroundTasks,
        function: Callable[..., Awaitable[None]],
        *args: Any,
    ) -> None: ...


class FastAPIBackgroundTaskRunner:
    def submit(
        self,
        background_tasks: BackgroundTasks,
        function: Callable[..., Awaitable[None]],
        *args: Any,
    ) -> None:
        background_tasks.add_task(run_bounded, function, *args)
