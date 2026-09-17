from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.exceptions import AppError

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, password_digest: str) -> bool:
    return password_hash.verify(password, password_digest)


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_token(
    subject: UUID,
    role: str,
    token_type: Literal["access", "refresh"],
) -> tuple[str, str, datetime]:
    now = datetime.now(UTC)
    expires = now + (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    jti = str(uuid4())
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": expires,
    }
    encoded = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded, jti, expires


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AppError("登录凭证无效或已过期", code=4010, status_code=401) from exc
    if payload.get("type") != expected_type:
        raise AppError("登录凭证类型错误", code=4011, status_code=401)
    return payload
