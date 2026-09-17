from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.identity import User
from app.schemas.auth import UserView
from app.schemas.common import ApiResponse, success

router = APIRouter()


@router.get("/me", response_model=ApiResponse[UserView])
async def me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserView]:
    return success(UserView.model_validate(current_user))
