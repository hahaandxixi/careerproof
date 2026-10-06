"""Reviewed 0014 -> 0015 upgrade of the existing synthetic closure database only."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT=Path(__file__).resolve().parents[3]
BACKEND=ROOT/'backend'
URL='postgresql+asyncpg://careerproof:careerproof@127.0.0.1:5432/cp_e2e_closure-20261005'
REV14='0014_growth_target_job'
REV15='0015_growth_answer_drafts'
parsed=make_url(URL)
assert parsed.host=='127.0.0.1' and parsed.port==5432
assert parsed.database=='cp_e2e_closure-20261005'

async def snapshot(expected):
    engine=create_async_engine(URL)
    try:
        async with engine.connect() as c:
            await c.execute(text('SET TRANSACTION READ ONLY'))
            assert await c.scalar(text('SELECT current_database()'))==parsed.database
            assert await c.scalar(text('SHOW transaction_read_only'))=='on'
            assert await c.scalar(text('SELECT version_num FROM public.alembic_version'))==expected
            tables=list(await c.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")))
            result={}
            for table in tables:
                if table in ('alembic_version','growth_answer_drafts'):
                    continue
                assert table.replace('_','').isalnum()
                rows=list(await c.scalars(text(f'SELECT row_to_json(t)::text FROM public."{table}" t ORDER BY id')))
                normalized=[json.loads(row) for row in rows]
                digest=hashlib.sha256(json.dumps(normalized,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                result[table]={'rows':len(rows),'sha256':digest}
            if expected==REV15:
                assert await c.scalar(text('SELECT COUNT(*) FROM public.growth_answer_drafts'))==0
            await c.rollback()
            return result
    finally:
        await engine.dispose()

before=asyncio.run(snapshot(REV14))
print('BEFORE: confirmed closure 0014, all existing public table row hashes captured',flush=True)
env=dict(os.environ,DATABASE_URL=URL,AI_PROVIDER='mock',AI_EXTERNAL_ENABLED='false')
completed=subprocess.run([sys.executable,'-m','alembic','upgrade',REV15],cwd=BACKEND,env=env,capture_output=True,text=True)
print(completed.stdout,flush=True)
print(completed.stderr,flush=True)
print(f'ALEMBIC_EXIT={completed.returncode}',flush=True)
assert completed.returncode==0
after=asyncio.run(snapshot(REV15))
assert before==after,'Existing synthetic rows changed; do not auto-restore'
print(json.dumps({'database':parsed.database,'from':REV14,'to':REV15,'legacyTables':before,'allLegacyRowsUnchanged':True,'newDraftRows':0},ensure_ascii=False,indent=2),flush=True)
