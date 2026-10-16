from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    token_digest,
    verify_password,
)
from app.models.enums import UserRole
from app.models.identity import RefreshToken, StudentProfile, User
from app.models.login_limit import LoginLimit
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    user: User
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, request: RegisterRequest) -> IssuedTokens:
        if request.role is UserRole.ADMIN:
            raise AppError("不能通过公开接口注册管理员", code=4031, status_code=403)
        if await self.users.get_by_email(str(request.email)):
            raise AppError("邮箱已被注册", code=4090, status_code=409)
        user = User(
            email=str(request.email).lower(),
            password_hash=hash_password(request.password),
            display_name=request.display_name,
            role=request.role,
        )
        self.users.add(user)
        await self.session.flush()
        if user.role is UserRole.STUDENT:
            self.session.add(StudentProfile(user_id=user.id))
        tokens = await self._issue_tokens(user)
        await self.session.commit()
        return tokens

    async def login(self, request: LoginRequest, *,
                    admitted_pair_key: str | None = None) -> IssuedTokens:
        user = await self.users.get_by_email(str(request.email))
        if not user or not verify_password(request.password, user.password_hash):
            raise AppError("邮箱或密码错误", code=4012, status_code=401)
        if not user.is_active:
            raise AppError("账号已停用", code=4032, status_code=403)
        if admitted_pair_key is not None:
            await self.session.execute(delete(LoginLimit).where(
                LoginLimit.key_hash == admitted_pair_key, LoginLimit.scope == "pair",
            ))
        tokens = await self._issue_tokens(user)
        await self.session.commit()
        return tokens

    async def refresh(self, encoded_refresh_token: str) -> IssuedTokens:
        payload = decode_token(encoded_refresh_token, "refresh")
        digest = token_digest(payload["jti"])
        user_id = await self.users.consume_active_refresh_token(digest)
        if user_id is None:
            stored = await self.users.get_refresh_token(digest)
            if stored and stored.revoked_at:
                revoked_at = stored.revoked_at
                if revoked_at.tzinfo is None:
                    revoked_at = revoked_at.replace(tzinfo=UTC)
                if 0 <= (datetime.now(UTC) - revoked_at).total_seconds() <= 10:
                    # Still rejected: this does not reissue a consumed token.
                    # A delayed peer response may be updating the shared cookie.
                    raise AppError(
                        "会话可能正在其他窗口刷新，请稍后重试", code=4015, status_code=401
                    )
            raise AppError("刷新凭证已失效", code=4013, status_code=401)
        user = await self.users.get(user_id)
        if not user or not user.is_active:
            raise AppError("账号不存在或已停用", code=4014, status_code=401)
        tokens = await self._issue_tokens(user)
        await self.session.commit()
        return tokens

    async def revoke(self, encoded_refresh_token: str | None) -> None:
        if not encoded_refresh_token:
            return
        try:
            payload = decode_token(encoded_refresh_token, "refresh")
        except AppError:
            return
        stored = await self.users.get_active_refresh_token(token_digest(payload["jti"]))
        if stored:
            stored.revoked_at = datetime.now(UTC)
            await self.session.commit()

    async def _issue_tokens(self, user: User) -> IssuedTokens:
        access_token, _access_jti, _access_expires = create_token(
            user.id, user.role.value, "access"
        )
        refresh_token, refresh_jti, refresh_expires = create_token(
            user.id, user.role.value, "refresh"
        )
        self.users.add_refresh_token(
            RefreshToken(
                user_id=user.id,
                jti_hash=token_digest(refresh_jti),
                expires_at=refresh_expires,
            )
        )
        return IssuedTokens(user, access_token, refresh_token)


def access_cookie_max_age() -> int:
    return settings.access_token_minutes * 60


def refresh_cookie_max_age() -> int:
    return settings.refresh_token_days * 24 * 60 * 60
