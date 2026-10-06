"""Inspect only migration metadata after isolated chain harness failure."""
import asyncio
import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine=create_async_engine('postgresql+asyncpg://careerproof:careerproof@127.0.0.1:5432/careerproof')
    try:
        async with engine.connect() as connection:
            await connection.execute(text('SET TRANSACTION READ ONLY'))
            assert await connection.scalar(text('SELECT current_database()'))=='careerproof'
            assert await connection.scalar(text('SHOW transaction_read_only'))=='on'
            version=await connection.scalar(text('SELECT version_num FROM public.alembic_version'))
            target_column=await connection.scalar(text("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='evidence_growth_tasks' AND column_name='target_job_id')"))
            draft_table=await connection.scalar(text("SELECT to_regclass('public.growth_answer_drafts')"))
            test_schema=await connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='cp_test_9de577083ebb4d80be9a8beaf67a11f2')"))
            print(json.dumps({'readOnly':True,'publicVersion':version,'publicTargetJobColumn':target_column,'publicDraftTable':str(draft_table) if draft_table else None,'firstAttemptSchemaStillExists':test_schema,'writes':0}))
            await connection.rollback()
    finally:
        await engine.dispose()

asyncio.run(main())
