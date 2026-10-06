"""Read-only incident inspection of migration markers, with no data rows read."""

import asyncio

import asyncpg


async def main():
    conn = await asyncpg.connect(
        user="careerproof", password="careerproof", database="careerproof", host="127.0.0.1", port=5432
    )
    try:
        async with conn.transaction(readonly=True):
            print("database", await conn.fetchval("SELECT current_database()"))
            print("public_revision", await conn.fetchval("SELECT version_num FROM public.alembic_version"))
            print("public_target_job_column", await conn.fetchval("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='evidence_growth_tasks' AND column_name='target_job_id')"))
            print("public_draft_table", await conn.fetchval("SELECT to_regclass('public.growth_answer_drafts') IS NOT NULL"))
            for name in ("cp_test_9de577083ebb4d80be9a8beaf67a11f2", "cp_test_7f54eab143d94c80b7847e28a4006093"):
                print(name + "_exists", await conn.fetchval("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=$1)", name))
    finally:
        await conn.close()


asyncio.run(main())
