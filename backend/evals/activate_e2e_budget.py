"""Run the real budget activation audit in a strictly isolated synthetic E2E database."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.ai_budget import AiBudgetCutover
from app.models.enums import UserRole
from app.models.identity import User
from app.models.recruitment import Application
from app.services.ai_budget import GATE_ID, SharedBudgetService
from evals.e2e_verification import validate_environment


async def snapshot_hashes(session):
    rows = (await session.scalars(select(Application))).all()
    return {str(row.id): hashlib.sha256(json.dumps(
        row.report_snapshot, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"),
    ).encode()).hexdigest() for row in rows}


async def activate(run):
    validate_environment(run, settings.database_url, settings.storage_base_dir,
                         settings.ai_external_enabled, settings.ai_provider)
    engine = create_async_engine(settings.database_url, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            before = await snapshot_hashes(session)
            email = f"budget-audit-{run}@e2e.invalid"
            actor = await session.scalar(select(User).where(User.email == email))
            if actor is None:
                actor = User(email=email, password_hash=hash_password(secrets.token_urlsafe(48)),
                             display_name="合成预算审计管理员", role=UserRole.ADMIN, is_active=True)
                session.add(actor)
                await session.flush()
            elif actor.role != UserRole.ADMIN or not actor.is_active:
                raise ValueError("Existing synthetic administrator identity is not authorized")
            digest = await SharedBudgetService().activate(
                session, actor_id=actor.id,
                reason=f"Synthetic E2E {run}: inventory audit before local mock verification",
            )
            gate = await session.get(AiBudgetCutover, GATE_ID)
            if await snapshot_hashes(session) != before:
                raise ValueError("Budget activation changed original application snapshots")
            await session.commit()
            return {"run": run, "gateEnabled": gate.enabled,
                    "inventoryDigest": gate.inventory_digest, "auditedActor": str(actor.id),
                    "activationDigest": digest, "snapshotHashes": before,
                    "syntheticOnly": True}
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(activate(args.run)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
