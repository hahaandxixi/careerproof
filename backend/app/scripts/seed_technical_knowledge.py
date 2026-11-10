"""Seed or refresh the curated technical cards without duplicating rows.

Run from ``backend``:  python -m app.scripts.seed_technical_knowledge
This is the explicit load step for the separate technical scope; requests never
read a file index as a fallback.
"""

import asyncio

from app.core.database import async_session_factory
from app.services.technical_knowledge import seed_technical_knowledge


async def main() -> int:
    async with async_session_factory() as session:
        changed = await seed_technical_knowledge(session)
        await session.commit()
        return changed


if __name__ == "__main__":
    print(f"technical_knowledge_changed={asyncio.run(main())}")
