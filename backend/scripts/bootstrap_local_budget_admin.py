"""Explicitly initialize the local budget audit identity for CareerProof V1."""

from __future__ import annotations

import argparse
import asyncio
import secrets

from sqlalchemy import select, text

from app.core.database import async_session_factory, engine
from app.core.security import hash_password
from app.models import AuditLog, User
from app.models.enums import UserRole

ADMIN_EMAIL = "budget-audit@careerproof.local"
AUDIT_ACTION = "user.local_budget_admin_initialized"


async def initialize(database: str) -> str:
    url = engine.url
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != database
    ):
        raise ValueError("Configured database must be the explicitly named local PostgreSQL database")

    async with async_session_factory.begin() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(1824472911)"))
        existing = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if existing is not None:
            audit = await session.scalar(
                select(AuditLog.id).where(
                    AuditLog.action == AUDIT_ACTION,
                    AuditLog.resource_id == str(existing.id),
                )
            )
            if existing.role != UserRole.ADMIN or not existing.is_active or audit is None:
                raise ValueError("Reserved identity already exists without a valid bootstrap record")
            return "Existing local budget audit administrator verified"

        # The local operator uses this identity for audited database commands.
        # It has no retained password for web login.
        admin = User(
            email=ADMIN_EMAIL,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            display_name="本地预算审计管理员",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.flush()
        session.add(
            AuditLog(
                action=AUDIT_ACTION,
                resource_type="user",
                resource_id=str(admin.id),
                details={"source": "local_cli", "database": database},
            )
        )
    return "Local budget audit administrator created"


async def run(database: str) -> None:
    try:
        print(await initialize(database))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm", required=True, action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.database))
