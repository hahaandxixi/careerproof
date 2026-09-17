from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import ApiResponse, HealthData, success

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthData])
async def health() -> ApiResponse[HealthData]:
    return success(HealthData(status="ok", service=settings.app_name, timestamp=datetime.now(UTC)))
