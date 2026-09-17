from __future__ import annotations

import asyncio
import os
import pickle
import subprocess
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol
from weakref import WeakKeyDictionary

from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.exceptions import AppError

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
    # Uvicorn --reload uses Windows' SelectorEventLoop, which cannot create
    # asyncio subprocesses. Popen + a bounded background thread works on both
    # event-loop policies; the parser itself still runs in a separate process.
    process = subprocess.Popen(
        [sys.executable, "-m", "app.services.isolated_worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    communication = asyncio.create_task(
        asyncio.to_thread(
            process.communicate,
            payload,
            timeout=timeout_seconds or settings.task_timeout_seconds,
        )
    )
    try:
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
        if process.poll() is None:
            process.kill()
        await asyncio.to_thread(process.wait)
        with suppress(subprocess.TimeoutExpired):
            await communication


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
