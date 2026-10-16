"""Database admission before password hashing; no account or identity exemptions."""

import hashlib
import hmac
import ipaddress
import time

from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.login_limit import LoginLimit


def canonical_source(host: str | None) -> str:
    try:
        address = ipaddress.ip_address(host or "")
    except ValueError:
        return "unknown"
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        # IPv6 privacy addresses must not supply a fresh allowance per address.
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    # Keep separate IPv4 sources separate; do not aggregate an entire campus /24.
    return str(address)


def _key(scope: str, *parts: str) -> str:
    material = "\0".join(("login-limit-v1", scope, *parts)).encode()
    return hmac.new(settings.jwt_secret.encode(), material, hashlib.sha256).hexdigest()


class LoginLimiter:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _reserve(self, scope: str, key: str, limit: int, window: int, now: int) -> None:
        dialect = self.session.get_bind().dialect.name
        insert = {"postgresql": pg_insert, "sqlite": sqlite_insert}[dialect]
        expired = LoginLimit.expires_at <= now
        statement = insert(LoginLimit).values(
            key_hash=key, scope=scope, attempts=1, expires_at=now + window,
        ).on_conflict_do_update(
            index_elements=[LoginLimit.key_hash],
            set_={
                "attempts": case((expired, 1), else_=LoginLimit.attempts + 1),
                "expires_at": case((expired, now + window), else_=LoginLimit.expires_at),
            },
            where=or_(expired, LoginLimit.attempts < limit),
        ).returning(LoginLimit.expires_at)
        accepted = await self.session.scalar(statement)
        if accepted is None:
            expires = await self.session.scalar(select(LoginLimit.expires_at).where(
                LoginLimit.key_hash == key,
            ))
            # Commit a preceding source reservation even when the pair is denied.
            await self.session.commit()
            retry = max(1, (expires or now + window) - now)
            raise AppError(
                f"登录尝试过于频繁，请在{retry}秒后重试。账号未被停用。",
                code=4293, status_code=429, headers={"Retry-After": str(retry)},
            )

    async def admit(self, email: str, host: str | None) -> str:
        """Use only in the clean HTTP-login session, before reading credentials."""
        now = int(time.time())
        # Bound per-request maintenance. Expiry is enforced regardless of cleanup.
        expired = select(LoginLimit.key_hash).where(LoginLimit.expires_at <= now).order_by(
            LoginLimit.key_hash,
        ).limit(100)
        if self.session.get_bind().dialect.name == "postgresql":
            expired = expired.with_for_update(skip_locked=True)
        await self.session.execute(delete(LoginLimit).where(LoginLimit.key_hash.in_(expired)))
        # Never hold cleanup locks while waiting for another request's admission.
        # Otherwise two sources can deadlock when their expired rows are pruned.
        await self.session.commit()
        source = canonical_source(host)
        await self._reserve("source", _key("source", source), settings.login_source_limit,
                            settings.login_source_window_seconds, now)
        pair = _key("pair", email.strip().casefold(), source)
        await self._reserve("pair", pair, settings.login_pair_limit,
                            settings.login_pair_window_seconds, now)
        # Failed authentication and worker termination must not roll back admission.
        await self.session.commit()
        return pair
