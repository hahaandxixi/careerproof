import test from 'node:test';
import assert from 'node:assert/strict';
import {reportPairLabel} from '../src/lib/report-pair.ts';
import * as pairLabels from '../src/lib/report-pair.ts';
import {displayJobTitle} from '../src/lib/demo-display-identity.js';
import * as reportDisplay from '../src/lib/report-display.ts';
import {studentFlowLocation} from '../src/lib/flow-steps.ts';
import * as sourceLabels from '../src/lib/source-label.ts';
import * as evidenceAnchors from '../src/lib/evidence-anchor.ts';
test('report fragment navigation preserves opaque router history state for route-away/back',()=>{
 assert.equal(typeof evidenceAnchors.navigateEvidenceFragment,'function');
 const opaque={routerTree:['reports','saved'],marker:'opaque-router-state'};
 const events=[],view={location:{hash:''},history:{state:opaque,pushState(state,_unused,url){this.state=state;view.location.hash=url;events.push('push');}},dispatchEvent(event){events.push(event.type);return true;}};
 evidenceAnchors.navigateEvidenceFragment('#report-materials',view);
 assert.equal(view.history.state,opaque);assert.equal(view.location.hash,'#report-materials');assert.deepEqual(events,['push','hashchange']);
 evidenceAnchors.navigateEvidenceFragment('#report-materials',view);assert.equal(events.length,2);
 assert.throws(()=>evidenceAnchors.navigateEvidenceFragment('/portfolio',view));
});
test('main text removes only a known frozen material path prefix, keeping unknown identifiers and source text intact',()=>{
 assert.equal(typeof sourceLabels.materialPathReadingText,'function');
 const materials=[{kind:'project',id:'c90a4283-f9ab-4247-8fdc-16ef6e7ae56a',title:'作品',versionNumber:2}];
 const raw='请核对 c90a4283-f9ab-4247-8fdc-16ef6e7ae56a/test_pipeline.py 与 unrelated-id/notes.md';
 assert.equal(sourceLabels.materialPathReadingText(raw,materials),'请核对 test_pipeline.py 与 unrelated-id/notes.md');
 assert.equal(sourceLabels.materialPathReadingText(raw,[]),raw);
});
test('application workspace uses the same location-only journey without inferring completion',()=>{
 assert.equal(studentFlowLocation('/applications','student'),'application');
 assert.equal(studentFlowLocation('/applications','enterprise'),null);
});
const saved=(id,extra={})=>({id,jobId:'6c8ad563-ebf8-427c-b4a3-82905f37dbd0',jobTitle:'数据工程实习生 · 合成流程验收',candidateId:'owner',createdAt:'2026-11-05T12:00:00Z',analysisMode:'rules',materials:[{kind:'project',id:'c90a4283-f9ab-4247-8fdc-16ef6e7ae56a',title:'数据清洗 · 本地验收',versionNumber:2}],...extra});
test('selector options expose named fixed materials and exact time before selection',()=>{
 assert.equal(typeof pairLabels.reportPairOptionLabel,'function');
 const value=pairLabels.reportPairOptionLabel(saved('option'));
 assert.match(value,/2026/);assert.match(value,/数据清洗工具 v2/);assert.doesNotMatch(value,/c90a4283|规则分析/);
 const first=saved('first'),second=saved('second',{materials:[{kind:'project',id:'other-version',title:'另一个具名项目',versionNumber:2}]});
 const peers=[first,second];
 assert.notEqual(pairLabels.reportPairOptionLabel(first,peers),pairLabels.reportPairOptionLabel(second,peers));
 assert.match(reportPairLabel(first,peers),/数据清洗工具 v2/);
 assert.match(reportPairLabel(second,peers),/另一个具名项目 v2/);
 assert.equal(second.materials[0].id,'other-version');
});
test('report selector uses natural job, exact time and named fixed versions, never short IDs or analysis jargon',()=>{
 const row=saved('1234abcd-0000-0000-0000-000000000000');const text=reportPairLabel(row);
 assert.match(text,/数据工程实习生/);assert.match(text,/数据清洗工具 v2/);assert.match(text,/2026/);
 assert.doesNotMatch(text,/1234abcd|c90a4283|规则分析|合成流程验收|本地验收/);
});
test('same-time same-version reports retain distinct stable values and understandable duplicate labels',()=>{
 const a=saved('report-a'),b=saved('report-b');const peers=[b,a];
 assert.notEqual(reportPairLabel(a,peers),reportPairLabel(b,peers));
 assert.match(reportPairLabel(a,peers),/同批第 1 份/);assert.match(reportPairLabel(b,peers),/同批第 2 份/);
 assert.equal(reportPairLabel(a,peers),reportPairLabel(a,[a,b]));
 assert.equal(a.id,'report-a');assert.equal(a.materials[0].id,'c90a4283-f9ab-4247-8fdc-16ef6e7ae56a');
});
test('historical diagnostic direct report gets a natural title without mutating unrelated titles',()=>{
 const raw='材料证据状态 · 三态合成验收';
 assert.equal(displayJobTitle(raw,'1233f1e2-169f-4ea5-a5a0-542fa940e897'),'材料证据阅读示例');
 assert.equal(displayJobTitle(raw,'real-job'),raw);
});
test('ordinary source labels distinguish AI success, unrequested analysis and budget-blocked fallback honestly',()=>{
 assert.equal(typeof reportDisplay.reportReadingStatus,'function');
 assert.equal(reportDisplay.reportReadingStatus(saved('x')).label,'规则分析结果');
 const blocked=reportDisplay.reportReadingStatus(saved('x',{analysisMode:'ai_evidence',aiFallbackUsed:true,items:[{aiStatus:'rules_only'}]}));
 assert.equal(blocked.label,'AI 分析未完成');assert.match(blocked.reason,/当前显示规则分析结果/);
 const invalid=reportDisplay.reportReadingStatus(saved('x',{analysisMode:'ai_evidence',aiFallbackUsed:true,aiProcess:{fallbackReason:'invalid_output_or_config'},items:[{aiStatus:'rules_only'}]}));
 assert.equal(invalid.label,'AI 结果未通过校验');assert.match(invalid.reason,/当前显示规则分析结果/);
 assert.equal(reportDisplay.reportReadingStatus(saved('x',{analysisMode:'ai_evidence',aiFallbackUsed:true})).label,'暂无可用分析结果');
 assert.equal(reportDisplay.reportReadingStatus(saved('x',{analysisMode:'ai_evidence',aiFallbackUsed:false,items:[{aiStatus:'validated'}]})).label,'AI 分析完成');
});
