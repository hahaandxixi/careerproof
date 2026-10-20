from pathlib import Path
import httpx,json,time,hashlib
from uuid import uuid4
r=Path('D:/jbcode/web ai/jianli'); run=r/'backend/.tmp/r7-clean-20261021'; source=run/'source'; e=r/'docs/evidence/20261021-r7-clean-reproduction'; target=e/'flow.json'; assert not target.exists(),'Refuse duplicate flow'
creds=json.loads((run/'demo-test-credentials.json').read_text(encoding='utf-8')); calls=[]
with httpx.Client(base_url='http://127.0.0.1:3107/backend/api/v1',trust_env=False,timeout=30) as c:
 def data(method,path,**kw):
  response=c.request(method,path,**kw); calls.append({'method':method,'path':path,'status':response.status_code}); response.raise_for_status(); body=response.json(); assert body['code']==0,body; return body['data']
 def settle(task):
  for _ in range(90):
   result=data('GET',f'/analysis-tasks/{task}')
   if result['status']=='completed': return result
   assert result['status'] not in ['failed','cancelled'],result
   time.sleep(.5)
  raise AssertionError('Task timeout')
 user=data('POST','/auth/login',json={'email':creds['studentEmail'],'password':creds['password']})['user']
 jobs=data('GET','/jobs')['items']; job=next(x for x in jobs if x['title']=='Python 后端开发实习生')
 assets=source/'jianli/public/demo-assets/scenarios'
 resume=data('POST','/resumes',data={'title':'r7独立安装合成简历'},files={'file':('event-api-resume.txt',(assets/'event-api-resume.txt').read_bytes(),'text/plain')}); settle(resume['taskId'])
 project=data('POST','/projects',json={'name':'r7独立安装活动报名项目','requestId':str(uuid4())})
 version=data('POST',f"/projects/{project['id']}/versions",data={'requestId':str(uuid4())},files={'file':('event-api-project.zip',(assets/'event-api-project.zip').read_bytes(),'application/zip')}); settle(version['taskId'])
 task=data('POST','/matches',json={'jobId':job['id'],'resumeVersionId':resume['versionId'],'projectVersionIds':[version['versionId']],'externalAiConsent':False}); finished=settle(task['taskId']); report=data('GET',f"/match-reports/{finished['reportId']}")
 files=data('GET',f"/project-versions/{version['versionId']}/files"); assert files
 previews=[]
 for item in files:
  preview=data('GET',f"/project-files/{item['id']}"); previews.append(preview)
 (e/'report-first.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (e/'file-previews.json').write_text(json.dumps(previews,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (e/'http-calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 target.write_text(json.dumps({'backend':'http://127.0.0.1:8107','frontend':'http://127.0.0.1:3107','userId':user['id'],'jobId':job['id'],'projectId':project['id'],'resumeVersionId':resume['versionId'],'projectVersionId':version['versionId'],'taskId':task['taskId'],'reportId':report['id'],'reportSha256':hashlib.sha256(json.dumps(report,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'reportKeys':list(report),'items':len(report['items']),'projectFiles':len(files),'externalAiConsent':False,'executorReproductionOnly':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Flow completed; report',report['id'],'items',len(report['items']),'files',len(files)); print('Report fields:',list(report)); print('First item fields:',list(report['items'][0]))
