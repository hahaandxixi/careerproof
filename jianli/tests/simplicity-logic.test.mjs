import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import path from 'node:path';
registerHooks({resolve(specifier,context,next){
 if(specifier.startsWith('.')&&!path.extname(specifier))return next(new URL(specifier+'.ts',context.parentURL).href,context);
 return next(specifier,context);
}});
const { combineDraftRequirements, createDraftRequestGuard, quoteStillMatches } = await import('../src/lib/job-draft.ts');
const { invalidNarrativeCitations } = await import('../src/lib/report-citations.ts');
const { sourceLimit, unsentRuleSources, historicalScopeOnly } = await import('../src/lib/source-limits.ts');

const row={rawText:'手工编辑',skillName:'SQL',weight:3,isRequired:true};
test('append preserves manual edits; explicit replacement and capacity remain separate',()=>{
 const next={...row,rawText:'AI草稿',skillName:'Python'};
 assert.deepEqual(combineDraftRequirements([row],[next],'append'),[row,next]);
 assert.deepEqual(combineDraftRequirements([row],[next],'replace'),[next]);
 assert.throws(()=>combineDraftRequirements(Array(50).fill(row),[next],'append'),/50/);
 assert.throws(()=>combineDraftRequirements([row],[{...next,skillName:''}],'append'),/技能/);
 assert.equal(row.rawText,'手工编辑');
});
test('failed or out-of-order draft requests cannot replace the retained draft',async()=>{
 const gate=createDraftRequestGuard(); let draft='原草稿'; const first=gate.start();
 gate.sourceChanged(); assert.equal(gate.accepts(first),false); assert.equal(gate.isLatest(first),true);
 const second=gate.start(); if(gate.accepts(second))draft='新草稿';
 if(gate.accepts(first))draft='迟到结果'; assert.equal(draft,'新草稿');
 const third=gate.start(); try{await Promise.reject(Error('offline'));}catch{assert.equal(draft,'新草稿');}
 assert.equal(gate.accepts(third),true);gate.invalidate();assert.equal(gate.accepts(third),false);
});
test('changed description invalidates saved source coordinates',()=>{
 const r={...row,sourceQuote:'SQL',sourceStart:0,sourceEnd:3};
 assert.equal(quoteStillMatches('SQL查询',r),true);assert.equal(quoteStillMatches('先SQL查询',r),false);
});
test('history cross references are flagged without redirecting or rewriting original text',()=>{
 const item={aiExplanation:'R1-E1 与 R2-E1',aiInformationGap:null,aiSuggestion:null,aiCitationIds:['R2-E1'],evidenceList:[{citationId:'R2-E1'}]};
 assert.deepEqual(invalidNarrativeCitations(item),['R1-E1']);assert.equal(item.aiExplanation,'R1-E1 与 R2-E1');
});
test('source limitation distinguishes history, scope, unavailable text and local excerpts',()=>{
 const report={evidenceContextVersion:'source-context-v3',materials:[{id:'old'}]};
 const source={projectVersionId:'old',snippet:'old code',lineStart:1,lineEnd:2,contextComplete:false};
 assert.equal(sourceLimit(report,source).label,'局部原文');
 assert.equal(sourceLimit({...report,evidenceContextVersion:null},source).label,'历史完整性信息不足');
 assert.equal(sourceLimit(report,{...source,projectVersionId:'new'}).readable,false);
 assert.equal(sourceLimit(report,{...source,snippet:''}).label,'来源暂不可读');
 const item={evidenceList:[{...source,citationId:'R1-E1'},source],aiInformationGap:'未展示运行记录'};
 assert.equal(unsentRuleSources(item).length,1);assert.equal(item.aiInformationGap,'未展示运行记录');
 assert.equal(historicalScopeOnly(item),false);
});
