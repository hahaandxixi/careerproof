from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import RefreshToken, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    def add(self, user: User) -> None:
        self.session.add(user)

    def add_refresh_token(self, token: RefreshToken) -> None:
        self.session.add(token)

    async def consume_active_refresh_token(self, jti_hash: str) -> UUID | None:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(RefreshToken).where(
                RefreshToken.jti_hash == jti_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            ).values(revoked_at=now).returning(RefreshToken.user_id)
            .execution_options(synchronize_session="fetch")
        )
        return result.scalar_one_or_none()

    async def get_refresh_token(self, jti_hash: str) -> RefreshToken | None:
        return await self.session.scalar(select(RefreshToken).where(
            RefreshToken.jti_hash == jti_hash,
        ).execution_options(populate_existing=True))

    async def get_active_refresh_token(self, jti_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.jti_hash == jti_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()
