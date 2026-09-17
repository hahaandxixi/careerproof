from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.schemas.auth import AuthData, LoginRequest, RefreshData, RegisterRequest, UserView
from app.schemas.common import ApiResponse, success
from app.services.auth import (
    AuthService,
    IssuedTokens,
    access_cookie_max_age,
    refresh_cookie_max_age,
)

router = APIRouter()


def _set_auth_cookies(response: Response, tokens: IssuedTokens) -> None:
    common = {
        "httponly": True,
        "secure": settings.app_env == "production",
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        "careerproof_access",
        tokens.access_token,
        max_age=access_cookie_max_age(),
        **common,
    )
    response.set_cookie(
        "careerproof_refresh",
        tokens.refresh_token,
        max_age=refresh_cookie_max_age(),
        **common,
    )


def _auth_data(tokens: IssuedTokens) -> AuthData:
    return AuthData(
        user=UserView.model_validate(tokens.user),
        access_token_expires_in=access_cookie_max_age(),
    )


@router.post("/register", response_model=ApiResponse[AuthData], status_code=201)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AuthData]:
    tokens = await AuthService(session).register(payload)
    _set_auth_cookies(response, tokens)
    return success(_auth_data(tokens), message="registered")


@router.post("/login", response_model=ApiResponse[AuthData])
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AuthData]:
    tokens = await AuthService(session).login(payload)
    _set_auth_cookies(response, tokens)
    return success(_auth_data(tokens), message="authenticated")


@router.post("/refresh", response_model=ApiResponse[RefreshData])
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[RefreshData]:
    refresh_token = request.cookies.get("careerproof_refresh")
    if not refresh_token:
        raise AppError("缺少刷新凭证", code=4018, status_code=401)
    tokens = await AuthService(session).refresh(refresh_token)
    _set_auth_cookies(response, tokens)
    return success(RefreshData(access_token_expires_in=access_cookie_max_age()))


@router.post("/logout", response_model=ApiResponse[dict])
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    await AuthService(session).revoke(request.cookies.get("careerproof_refresh"))
    response.delete_cookie("careerproof_access", path="/")
    response.delete_cookie("careerproof_refresh", path="/")
    return success({}, message="logged out")
