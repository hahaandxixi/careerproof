from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.identity import User
from app.schemas.common import ApiResponse, success
from app.schemas.enterprises import EnterpriseCreate, EnterpriseView
from app.services.enterprises import EnterpriseService

router = APIRouter()


@router.get("/me", response_model=ApiResponse[list[EnterpriseView]])
async def my_enterprises(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[EnterpriseView]]:
    return success(await EnterpriseService(session).mine(current_user))


@router.post("", response_model=ApiResponse[EnterpriseView], status_code=201)
async def create_enterprise(
    request: EnterpriseCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[EnterpriseView]:
    return success(
        await EnterpriseService(session).create(request, current_user), message="created"
    )
