import asyncio
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import quote
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # Register the actual production metadata.
from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus, UserRole
from app.models.identity import StudentProfile, User
from app.models.notification import Notification
from app.models.recruitment import Application, ApplicationEvent, Job
from app.services.report_history import _owner_history_query

root=Path(r'D:\jbcode\web ai\jianli')
out=root/'docs/evidence/20261015-index-plans'
out.mkdir(exist_ok=False)
private=json.loads((root/'backend/.tmp/ci49-pg-private-20261014.json').read_text())
container=private['container']
info=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
assert info['Config']['Labels']['careerproof.purpose']=='ci49-isolated-review-20261014'
assert info['State']['Status']=='exited'
database='cp_index_review_20261015'
url=f"postgresql+asyncpg://ci:{quote(private['password'])}@127.0.0.1:55433/{database}"
summary={'source_commit':'2048417','database':database,'rows_per_fact_table':5000,'planner_forced':False,'plans':{}}

async def exercise():
    engine=create_async_engine(url)
    now=datetime.now(UTC)
    users=[uuid4() for _ in range(100)]
    students=[uuid4() for _ in users]
    jobs=[uuid4() for _ in users]
    tasks=[uuid4() for _ in range(5000)]
    reports=[uuid4() for _ in tasks]
    apps=[uuid4() for _ in tasks]
    events=[uuid4() for _ in tasks]
    try:
        async with engine.begin() as c:
            await c.execute(sa.insert(User),[dict(id=id,email=f'index-{i}@example.invalid',password_hash='synthetic-no-login',display_name='synthetic',role=UserRole.STUDENT) for i,id in enumerate(users)])
            await c.execute(sa.insert(StudentProfile),[dict(id=id,user_id=users[i]) for i,id in enumerate(students)])
            await c.execute(sa.insert(Job),[dict(id=id,created_by=users[0],title='synthetic',company_name='synthetic',status='published') for id in jobs])
            await c.execute(sa.insert(AnalysisTask),[dict(id=id,created_by=users[i%100],task_type='career_plan' if i%3 else 'matching',status=TaskStatus.COMPLETED,created_at=now+timedelta(seconds=i)) for i,id in enumerate(tasks)])
            await c.execute(sa.insert(MatchReport),[dict(id=id,analysis_task_id=tasks[i],job_id=jobs[(i//100)%100],candidate_ref=str(users[i%100]),summary='synthetic',created_at=now+timedelta(seconds=i)) for i,id in enumerate(reports)])
            await c.execute(sa.insert(Application),[dict(id=id,job_id=jobs[i%100],student_id=students[(i//100)%100],status='withdrawn' if i%7==0 else 'submitted',report_id=reports[i],consent_at=now,report_snapshot={'synthetic':True},created_at=now+timedelta(seconds=i)) for i,id in enumerate(apps)])
            await c.execute(sa.insert(ApplicationEvent),[dict(id=id,application_id=apps[i],actor_id=users[0],event_type='viewed') for i,id in enumerate(events)])
            await c.execute(sa.insert(Notification),[dict(event_id=events[i],recipient_id=users[i%100],read_at=None if i%3==0 else now) for i in range(5000)])
            for table in ['applications','analysis_tasks','match_reports','notifications']:
                await c.execute(sa.text(f'ANALYZE {table}'))
            queries={
                'student_applications':sa.select(Application).where(Application.student_id==students[7],Application.consent_at.is_not(None)).order_by(Application.created_at.desc()).limit(100),
                'job_candidates':sa.select(Application).where(Application.job_id==jobs[7],Application.consent_at.is_not(None),Application.status!='withdrawn').order_by(Application.created_at.desc()).limit(100),
                'latest_career_plan':sa.select(AnalysisTask).where(AnalysisTask.created_by==users[7],AnalysisTask.task_type=='career_plan',AnalysisTask.status==TaskStatus.COMPLETED).order_by(AnalysisTask.created_at.desc(),AnalysisTask.id.desc()).limit(1),
                'owner_history':_owner_history_query(users[7],jobs[7]).order_by(MatchReport.created_at.desc(),MatchReport.id.desc()).limit(1),
                'unread_count':sa.select(sa.func.count()).select_from(Notification).where(Notification.recipient_id==users[7],Notification.read_at.is_(None)),
            }
            for name,query in queries.items():
                sql=str(query.compile(dialect=engine.dialect,compile_kwargs={'literal_binds':True}))
                plan=await c.scalar(sa.text('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql))
                if isinstance(plan,str): plan=json.loads(plan)
                summary['plans'][name]={'sql':sql,'explain':plan}
    finally:
        await engine.dispose()

subprocess.run(['docker','start',container],check=True,capture_output=True)
created=False
try:
    for _ in range(60):
        if subprocess.run(['docker','exec',container,'pg_isready','-U','ci'],capture_output=True).returncode==0: break
        time.sleep(1)
    subprocess.run(['docker','exec',container,'psql','-U','ci','-d','cp_ci','-v','ON_ERROR_STOP=1','-c',f'CREATE DATABASE {database} OWNER ci'],check=True,capture_output=True)
    created=True
    env=os.environ.copy()
    env.update(DATABASE_URL=url,APP_ENV='test',DEBUG='false',AI_PROVIDER='mock',AI_EXTERNAL_ENABLED='false')
    with (out/'migration.raw.out').open('wb') as log:
        subprocess.run([str(root/'backend/.venv-dependency23/Scripts/python.exe'),'-m','alembic','upgrade','head'],cwd=root/'backend',env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    asyncio.run(exercise())
finally:
    if created:
        summary['drop_database_exit_code']=subprocess.run(['docker','exec',container,'psql','-U','ci','-d','cp_ci','-v','ON_ERROR_STOP=1','-c',f'DROP DATABASE {database}'],capture_output=True).returncode
    summary['container_stop_exit_code']=subprocess.run(['docker','stop',container],capture_output=True).returncode
    (out/'plans.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('Recorded query plans:',list(summary['plans']))
