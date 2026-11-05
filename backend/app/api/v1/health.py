import asyncio
from datetime import UTC, datetime
from time import monotonic

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session_factory
from app.schemas.common import ApiResponse, HealthData, success

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthData])
async def health() -> ApiResponse[HealthData]:
    return success(HealthData(status="ok", service=settings.app_name, timestamp=datetime.now(UTC)))


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Liveness stays cheap; readiness requires a bounded DB probe and live dispatcher."""
    database = False
    try:
        async with asyncio.timeout(2):
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
                database = True
    except Exception:
        # Connection strings and driver errors must not become public response data.
        pass
    state = request.app.state
    recovery = getattr(state, "recovery_task", None)
    last_success = getattr(state, "recovery_last_success", None)
    dispatcher = bool(
        recovery is not None
        and not recovery.done()
        and getattr(state, "recovery_ok", False)
        and last_success is not None
        and monotonic() - last_success <= max(5, settings.task_dispatch_interval_seconds * 3)
    )
    available = database and dispatcher
    body = success(
        {
            "status": "ready" if available else "not_ready",
            "database": database,
            "dispatcher": dispatcher,
        }
    ).model_dump(mode="json", by_alias=True)
    if not available:
        body.update(code=5031, message="Service dependencies are not ready")
    return JSONResponse(body, status_code=200 if available else 503)
