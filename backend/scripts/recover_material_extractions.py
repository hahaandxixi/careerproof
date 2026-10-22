"""Auditable orphan recovery; requires explicit target identity and defaults to dry-run."""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.database import async_session_factory
from app.services.material_cleanup import recover_extractions
from app.tools.storage import LocalStorage


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--expected-storage", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if make_url(settings.database_url).database != args.expected_database:
        parser.error("Database differs from the explicitly named target; stopped")
    if settings.storage_base_dir.resolve() != Path(args.expected_storage).resolve():
        parser.error("Storage differs from the explicitly named target; stopped")
    storage = LocalStorage(settings.storage_base_dir)
    async with async_session_factory() as session:
        results = await recover_extractions(session, storage, apply=args.apply)
        await session.rollback()  # Recovery only holds locks/reads; never updates material rows.
    print(json.dumps({"apply": args.apply, "attempts": results}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
