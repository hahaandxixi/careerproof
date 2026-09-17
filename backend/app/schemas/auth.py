from __future__ import annotations

from uuid import UUID

from pydantic import EmailStr, Field

from app.models.enums import UserRole
from app.schemas.common import APIModel


class RegisterRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    role: UserRole


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserView(APIModel):
    id: UUID
    email: EmailStr
    display_name: str
    role: UserRole
    is_active: bool


class AuthData(APIModel):
    user: UserView
    access_token_expires_in: int


class RefreshData(APIModel):
    access_token_expires_in: int
