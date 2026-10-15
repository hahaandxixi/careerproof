import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import install_exception_handlers
from app.core.request_context import RequestIdMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.services.task_dispatcher import dispatch_pending_tasks, stop_dispatched_tasks
from app.services.task_lifecycle import recover_interrupted_tasks


async def _recover_once() -> None:
    try:
        await recover_interrupted_tasks(async_session_factory)
        await dispatch_pending_tasks(async_session_factory)
    except Exception:
        logging.getLogger(__name__).warning("Task recovery unavailable; dispatcher will retry")


async def _recovery_loop() -> None:
    while True:
        await asyncio.sleep(settings.task_dispatch_interval_seconds)
        await _recover_once()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _recover_once()
    recovery = asyncio.create_task(_recovery_loop())
    try:
        yield
    finally:
        recovery.cancel()
        with suppress(asyncio.CancelledError):
            await recovery
        await stop_dispatched_tasks()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None if settings.app_env == "production" else "/redoc",
        openapi_url=None if settings.app_env == "production" else "/openapi.json",
        lifespan=lifespan,
    )
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(SecurityHeadersMiddleware)
    install_exception_handlers(application)
    application.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
