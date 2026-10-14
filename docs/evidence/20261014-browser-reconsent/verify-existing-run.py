import asyncio
import hashlib
import json
from pathlib import Path
import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from evals.release_smoke import snapshot_hashes, validate_run

root = Path.cwd()
run = 'release-owner-20261012'
folder = root.parent/'docs/evidence/20261014-browser-reconsent'
old = '2b2031bd-0e42-41e4-ba40-62d3945c9deb'
new = '5dfe5952-3af0-4467-8a73-12a786df6fde'
report = '77af85c6-0e78-49d7-be70-4a41f2167592'

async def main():
 validate_run(root,run)
 fixture=json.loads((root/'.tmp/e2e'/f'{run}.json').read_text(encoding='utf-8-sig'))
 smoke=json.loads((root/'.tmp/release-smoke'/f'{run}.credentials.json').read_text())
 checks=[]
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8001',trust_env=False,timeout=20) as hr, httpx.AsyncClient(base_url='http://127.0.0.1:8001',trust_env=False,timeout=20) as student:
  for client,account in [(hr,fixture['accounts']['enterprise']),(student,smoke)]:
   response=await client.post('/api/v1/auth/login',json={'email':account['email'],'password':account['password']})
   assert response.status_code==200, 'Synthetic login rejected'
  for method,suffix in [('GET',''),('POST','/view'),('POST','/resume-download'),('POST','/reply')]:
   kwargs={'json':{'kind':'continue','text':'隔离验证：旧授权不得发送'}} if suffix=='/reply' else {}
   response=await hr.request(method,'/api/v1/applications/'+old+suffix,**kwargs)
   checks.append({'endpoint':method+' old'+suffix,'status':response.status_code})
   assert response.status_code==404
  response=await hr.get('/api/v1/applications/'+new)
  assert response.status_code==200
  detail=response.json()['data']
  assert detail['reportId']==report and detail['status']=='replied'
  target=await student.get('/api/v1/match-reports/'+report)
  assert target.status_code==200
  target=target.json()['data']
  engine=create_async_engine(make_url(settings.database_url).set(database='cp_e2e_'+run),hide_parameters=True)
  async with engine.connect() as connection:
   await connection.execute(text('SET TRANSACTION READ ONLY'))
   value=await connection.scalar(text('SELECT report_snapshot FROM applications WHERE id=:id'),{'id':new})
   assert value==target
   notices=(await connection.execute(text('SELECT n.id FROM notifications n JOIN application_events e ON e.id=n.event_id JOIN users u ON u.id=n.recipient_id WHERE e.application_id=:old AND u.email=:email'),{'old':old,'email':fixture['accounts']['enterprise']['email']})).scalars().all()
  await engine.dispose()
  for notice in notices:
   response=await hr.get('/api/v1/notifications/'+str(notice)+'/target')
   assert response.status_code==404
  checks.append({'oldEnterpriseNotificationsDenied':len(notices)})
 before=json.loads((folder/'before-hashes.json').read_text())
 after=await snapshot_hashes(run)
 assert all(after.get(key)==value for key,value in before.items())
 assert len(after)==len(before)+1
 expected=hashlib.sha256(json.dumps(target,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 assert after[new]==expected
 result={'checks':checks,'oldApplication':old,'newApplication':new,'newReport':report,'newSnapshotEqualsSavedReport':True,'allPreviousSnapshotsUnchanged':len(before),'newSnapshotHash':expected,'newStatus':detail['status']}
 (folder/'independent-api.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False))

asyncio.run(main())
