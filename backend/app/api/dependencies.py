from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.models.identity import User
from app.repositories.users import UserRepository

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials if credentials else request.cookies.get("careerproof_access")
    if not token:
        raise AppError("请先登录", code=4015, status_code=401)
    payload = decode_token(token, "access")
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AppError("登录凭证内容无效", code=4016, status_code=401) from exc
    user = await UserRepository(session).get(user_id)
    if not user or not user.is_active:
        raise AppError("账号不存在或已停用", code=4017, status_code=401)
    return user
