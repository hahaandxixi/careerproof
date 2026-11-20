from pathlib import Path
import asyncio,json
from decimal import Decimal
import httpx
from app.core.config import settings
from app.agents.provider import DeepSeekProvider
from app.tests.test_agent_evidence_smoke import packet, answer, tool_response
from evals import bounded_evidence_smoke as smoke
r=Path('D:/jbcode/web ai/jianli'); run=r/'backend/.tmp/agent-display-20261021'; e=r/'docs/evidence/20261021-agent-evidence-display'; data=packet(); holder={}; posts=[]
original=smoke.AgentRequestGuard
class CapturingGuard(original):
 def __init__(self,*a,**kw): super().__init__(*a,**kw); holder['guard']=self
smoke.AgentRequestGuard=CapturingGuard

def handler(request):
 body=json.loads(request.content); case=next(row for row in data['cases'] if row['id']==holder['guard'].case_id); posts.append({'case':case['id'],'stage':holder['guard'].stage,'transport':'MockTransport'})
 if 'tools' in body: return tool_response('get_previous_report_context' if case['id']=='AG-03' else 'retrieve_more_evidence',case)
 citation='R1-E3' if case['id']=='AG-01' else 'R1-E1'; output=answer(case,citation)
 if case['id']=='AG-01':
  item=output['items'][0]; item['explanation']='预设界面输出：补充片段中可见 store.rollback() 调用；未展示它与订单写入失败的完整联动。'; item['information_gap']='补充订单写入失败时触发回滚的完整实现与验证材料；当前没有运行记录和本人贡献核验。'; item['suggestion']='提交具名的异常回滚实现及对应测试输入、结果与未覆盖情况。'
  item['rating']['level']=1; item['rating']['reason']='预设界面初评：可见回滚调用，完整订单异常处理链未展示。'; item['rating']['criteria'][1].update(supported=False,citation_ids=[],reason='当前允许的初评级别仅支持相关线索。'); item['rating']['criteria'][2]['reason']='未展示订单写入与回滚衔接的完整路径。'
 return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(output,ensure_ascii=False)}}],'usage':{'prompt_tokens':150,'completion_tokens':100}})
provider=DeepSeekProvider(api_key='synthetic-not-real',base_url='https://api.deepseek.com',model='deepseek-flash',timeout_seconds=5,max_attempts=1,transport=httpx.MockTransport(handler))
smoke.STATE_ROOT=run/'offline-only-claims-r2'; smoke.get_ai_provider=lambda:provider; settings.ai_external_enabled=True; settings.ai_provider='deepseek'; settings.ai_max_retrieval_calls=2
result=asyncio.run(smoke.execute_agent(data,e/'offline-agent-result.json',(Decimal(2),Decimal(8))))
assert len(posts)==5,result; assert result['results'][0]['toolCalls'][0]['citationId']=='R1-E3'; assert result['results'][0]['analysis']['items'][0]['citation_ids']==['R1-E3']
(e/'mock-transport-summary.json').write_text(json.dumps({'realExternalRequests':0,'mockPhysicalRequests':len(posts),'posts':posts,'syntheticOnly':True,'decisions':'pre-scripted MockTransport, not a real model choice','newEvidence':'actual workflow executed retrieval over frozen AG-01 sources','claimRoot':str(smoke.STATE_ROOT),'productionClaimsTouched':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Offline actual workflow: 5 MockTransport POSTs, no real network; AG-01 added and used R1-E3.')
