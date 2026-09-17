from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin
from app.models.enums import MembershipRole, UserRole


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RefreshToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    jti_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StudentProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "student_profiles"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    school: Mapped[str | None] = mapped_column(String(200), nullable=True)
    major: Mapped[str | None] = mapped_column(String(200), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(nullable=True)


class Enterprise(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "enterprises"

    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(String(2000), default="")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class EnterpriseMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "enterprise_memberships"
    __table_args__ = (UniqueConstraint("enterprise_id", "user_id"),)

    enterprise_id: Mapped[UUID] = mapped_column(
        ForeignKey("enterprises.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[MembershipRole] = mapped_column(Enum(MembershipRole, name="membership_role"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
