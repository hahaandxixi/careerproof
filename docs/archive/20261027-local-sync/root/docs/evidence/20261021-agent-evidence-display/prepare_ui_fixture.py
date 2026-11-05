from pathlib import Path
import asyncio,json,secrets,time,io,zipfile
from uuid import UUID,uuid4
import httpx
from sqlalchemy import select,text
from app.core.config import settings
from app.core.database import async_session_factory
from app.models.analysis import MatchReport,MatchItem
from app.models.portfolio import ProjectFile
r=Path('D:/jbcode/web ai/jianli'); run=r/'backend/.tmp/agent-display-20261021'; e=r/'docs/evidence/20261021-agent-evidence-display'; assert not (run/'state.json').exists()
async def check():
 async with async_session_factory() as s: assert (await s.execute(text('select current_database()'))).scalar_one()=='cp_agent_display_20261021'
asyncio.run(check()); assert not settings.ai_external_enabled
packet=json.loads((run/'source/docs/evidence/20261019-agent-boundary/agent-live-preflight-20261020.json').read_text(encoding='utf-8'))['cases'][0]; offline=json.loads((e/'offline-agent-result.json').read_text(encoding='utf-8'))['results'][0]; assert offline['accepted']
lines=['']*14
for ev in packet['evidence']: lines[ev['lineStart']-1:ev['lineEnd']]=ev['snippet'].splitlines()
source='\n'.join(lines)+'\n'; buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w') as z: z.writestr('project/order.py',source)
(run/'order-v1.zip').write_bytes(buffer.getvalue()); (run/'resume.txt').write_text('合成人物：'+packet['resume']+'；无运行结果或本人贡献证明。',encoding='utf-8')
password=secrets.token_urlsafe(24); creds={'studentEmail':'agent-ui-student@example.com','enterpriseEmail':'agent-ui-enterprise@example.com','password':password}; (run/'credentials.json').write_text(json.dumps(creds),encoding='utf-8')
with httpx.Client(base_url='http://127.0.0.1:3108/backend/api/v1',timeout=30,trust_env=False) as client:
 def data(method,path,**kwargs):
  response=client.request(method,path,**kwargs); response.raise_for_status(); body=response.json(); assert body['code']==0,body; return body['data']
 def settle(task):
  for _ in range(100):
   t=data('GET','/analysis-tasks/'+task)
   if t['status']=='completed': return t
   assert t['status']!='failed',t; time.sleep(.3)
  raise AssertionError('timeout')
 data('POST','/auth/register',json={'email':creds['enterpriseEmail'],'password':password,'displayName':'Mock界面虚构企业','role':'enterprise'}); org=data('POST','/enterprises',json={'name':'Mock Agent界面实验室（虚构）'})
 job=data('POST','/jobs',json={'enterpriseId':org['id'],'title':'Mock界面验证：Python订单处理','companyName':org['name'],'description':'仅界面与合成流程验证，不是真实招聘或真实模型运行。','status':'published','category':'software','city':'合成城市','employmentType':'internship','requirements':[{'rawText':packet['requirement'],'skillName':'Python','weight':5,'isRequired':True}]})
 data('POST','/auth/register',json={'email':creds['studentEmail'],'password':password,'displayName':'Mock界面合成学生','role':'student'}); req=job['requirements'][0]['id']
 resume=data('POST','/resumes',data={'title':'合成订单处理简历'},files={'file':('resume.txt',(run/'resume.txt').read_bytes(),'text/plain')}); settle(resume['taskId']); project=data('POST','/projects',json={'name':'合成订单处理','requestId':str(uuid4())})
 version=data('POST','/projects/'+project['id']+'/versions',data={'requestId':str(uuid4())},files={'file':('order-v1.zip',buffer.getvalue(),'application/zip')}); settle(version['taskId'])
 task=data('POST','/matches',json={'jobId':job['id'],'resumeVersionId':resume['versionId'],'projectVersionIds':[version['versionId']],'externalAiConsent':False}); rid=settle(task['taskId'])['reportId']
 async def patch_fixture():
  async with async_session_factory() as session:
   report=await session.get(MatchReport,UUID(rid)); assert str(report.job_id)==job['id']; file=(await session.scalars(select(ProjectFile).where(ProjectFile.project_version_id==UUID(version['versionId'])))).one(); item=(await session.scalars(select(MatchItem).where(MatchItem.report_id==report.id))).one(); evidence=[]
   for index,row in enumerate(packet['evidence'],1):
    evidence.append({'citation_id':f'R1-E{index}','provenance':'portfolio','context_complete':False,'context_note':'Mock界面：合成材料的实际冻结片段，非真实模型运行。','skill':'Python','evidence_type':'python_code','file_path':file.relative_path,'line_start':row['lineStart'],'line_end':row['lineEnd'],'snippet':row['snippet'],'strength':row['strength'],'explanation':row['explanation'],'content_hash':file.content_hash,'project_file_id':str(file.id),'project_version_id':str(file.project_version_id),'source_id':None})
   ai=offline['analysis']['items'][0]; snapshot=dict(item.evidence_snapshot); snapshot.update(evidenceList=evidence,evidence=evidence[0]); snapshot['ai']={**snapshot.get('ai',{}),'status':'validated','explanation':ai['explanation'],'citationIds':ai['citation_ids'],'informationGap':ai['information_gap'],'suggestion':ai['suggestion'],'rating':ai['rating'],'taskPlan':None}; item.evidence_snapshot=snapshot
   metadata=dict(report.analysis_metadata); metadata.update(mode='ai_evidence',provider='mock-ui',model='MockTransport预设（非真实模型）',fallbackUsed=False,modelToolCalls=[{**call,'requirementId':req} for call in offline['toolCalls']],fixtureSource='Offline MockTransport imported for UI; original task was rules-only'); report.analysis_metadata=metadata; report.summary='Mock界面验证：离线工作流补到回滚片段，预设解释引用了它，但没有完整订单异常处理链或运行证明。工具选择和回答均为预设，不是真实Agent运行。'; await session.commit()
 asyncio.run(patch_fixture()); result=data('GET','/match-reports/'+rid); assert result['aiProvider']=='mock-ui' and result['items'][0]['aiCitationIds']==['R1-E3']
 (e/'ui-fixture-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); fixture=r/'jianli/tests/fixtures/agent-evidence-report.json'; fixture.parent.mkdir(exist_ok=True); fixture.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 state={'reportId':rid,'taskId':task['taskId'],'jobId':job['id'],'requirementId':req,'projectId':project['id'],'resumeVersionId':resume['versionId'],'projectVersionId':version['versionId'],'realModelRequests':0,'uiFixtureOnly':True,'note':'MockTransport output deliberately imported into a new isolated synthetic report; not live Agent execution.'}; (run/'state.json').write_text(json.dumps(state,indent=2),encoding='utf-8'); (e/'page-entry.json').write_text(json.dumps({'reportUrl':'http://127.0.0.1:3108/reports/'+rid,**state},ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print('Isolated UI fixture ready:',rid)
