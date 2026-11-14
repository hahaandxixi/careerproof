"""Preview or confirm the historical audit for a local budget cutover."""

import argparse
import asyncio
import json

from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.models import User
from app.services.ai_budget import SharedBudgetService, inventory_hash
from scripts.bootstrap_local_budget_admin import ADMIN_EMAIL


async def run(database, digest, reason):
    url = engine.url
    if (url.get_backend_name() != "postgresql" or url.database != database
            or url.host not in {"localhost", "127.0.0.1", "::1"}):
        raise ValueError("Use the explicitly named local PostgreSQL database")
    try:
        async with async_session_factory.begin() as session:
            actor = await session.scalar(select(User.id).where(User.email == ADMIN_EMAIL))
            service = SharedBudgetService()
            if digest is not None:
                result = await service.activate(
                    session, actor_id=actor, reason=reason, legacy_digest=digest,
                )
                payload = {"inventoryDigest": result, "enabled": True}
            else:
                inventory = await service.legacy_cutover_inventory(session, actor_id=actor)
                payload = {"inventory": inventory, "reviewDigest": inventory_hash(inventory)}
        print(json.dumps(payload, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-digest")
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.confirm_digest is not None and not args.reason:
        parser.error("--confirm-digest requires --reason")
    asyncio.run(run(args.database, args.confirm_digest, args.reason))
