import test from 'node:test';
import assert from 'node:assert/strict';
import {demoJobAlias,displayJobTitle,displayMaterialTitle} from '../src/lib/demo-display-identity.js';
import * as planDisplay from '../src/lib/career-plan-display.ts';
const jobs=[['72e49e95-4f27-4412-ac94-f1675a5f8970','Django 后端开发实习生'],['6c8ad563-ebf8-427c-b4a3-82905f37dbd0','数据工程实习生'],['f05872f3-1b5f-4bb3-bfcd-9629d170b471','数据处理实习生']];
test('verified technical fixture ids use neutral display names and an explicitly example employer',()=>{
 for(const [id,title] of jobs){assert.equal(displayJobTitle('数据工程实习生 · 本地合成验收',id),title);assert.equal(demoJobAlias(id).companyName,'示例企业');}
 assert.equal(displayMaterialTitle('本地验收简历','4df0cd38-f8d1-45d5-91b5-6f97958eb1dc'),'数据工程方向简历');
});
test('unregistered identities are never renamed by keyword and diagnostic has an explicit example alias',()=>{
 const title='本地验收简历';assert.equal(displayJobTitle(title,'unregistered'),title);
 assert.equal(displayMaterialTitle(title,'unregistered'),title);
 assert.equal(demoJobAlias('1233f1e2-169f-4ea5-a5a0-542fa940e897').title,'材料证据阅读示例');
});
test('saved planning identities are display projections only, including materials and changes',()=>{
 const raw={planId:'saved-plan',aiStatus:'validated',aiUsage:{input_tokens:2376},aiPlan:{comparison:'模型原文保持'},
  materials:[{id:'4df0cd38-f8d1-45d5-91b5-6f97958eb1dc',title:'本地验收简历',versionNumber:1}],
  recommendations:[{jobId:jobs[1][0],jobTitle:'数据工程实习生 · 合成流程验收',companyName:'验收企业（合成）',evidence:[{citationId:'J2-E1'}]}],
  changes:[{jobId:jobs[1][0],jobTitle:'数据工程实习生 · 合成流程验收',detail:'历史判定原文'}]};
 const before=structuredClone(raw);
 assert.equal(typeof planDisplay.careerPlanDisplayIdentity,'function');
 const shown=planDisplay.careerPlanDisplayIdentity(raw);
 assert.equal(shown.recommendations[0].jobTitle,'数据工程实习生');assert.equal(shown.recommendations[0].companyName,'示例企业');
 assert.equal(shown.materials[0].title,'数据工程方向简历');assert.equal(shown.materials[0].versionNumber,1);
 assert.equal(shown.changes[0].jobTitle,'数据工程实习生');assert.equal(shown.aiPlan,raw.aiPlan);
 assert.equal(shown.recommendations[0].evidence,raw.recommendations[0].evidence);assert.deepEqual(raw,before);
});

test('the known acceptance resume id gets the same neutral display name without renaming raw data',()=>{ assert.equal(displayMaterialTitle('验收补证简历-20261107','d18b3087-99dc-4657-9a0d-7d26dc9d1a84'),'数据工程方向简历'); });

