// Independent controlled scheduling; no network, model or real clipboard.
import { registerHooks } from 'node:module';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
registerHooks({resolve(specifier,context,next){
  if(specifier.startsWith('.') && !/\.[a-z]+$/i.test(specifier)) {
    try { return next(specifier+'.ts',context); } catch {}
  }
  return next(specifier,context);
}});
const source=process.env.PRIVATE_ANSWER_SOURCE_FILE ? pathToFileURL(resolve(process.env.PRIVATE_ANSWER_SOURCE_FILE)).href : './private-answer-workflow.ts';
const {createPrivateAnswerSession,buildPrivateAnswerPreviewDocument}=await import(source);
const ref={reportId:'target-old',requirementId:'req',citationId:'old-evidence',available:true,snippet:'STALE TARGET ORIGINAL',filePath:'portfolio.md',lineStart:1,lineEnd:1,provenance:'portfolio'};
const draft=(revision=1)=>({taskId:'task',requirementId:'req',text:'stored',references:[ref],revision,updatedAt:'2026-10-06',boundary:'private'});
const option={...ref,reportKind:'target'};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function setup(overrides={}) {
  let state;
  const session=createPrivateAnswerSession({getDraft:async()=>draft(),listReferences:async()=>[option],saveDraft:async()=>draft(2),errorMessage:String,...overrides},s=>state=s);
  session.activate();
  return {session,state:()=>state};
}
const preview=h=>buildPrivateAnswerPreviewDocument({saved:h.state().saved,requirementTitle:'original',jobTitle:'job',baseReportId:'base',targetReportId:null});

test('successful source revalidation prevents old target original from being copied as valid evidence',async()=>{
  let options=[option];
  const h=setup({listReferences:async()=>options});
  await h.session.load('task'); options=[];
  await h.session.refreshReferences('task',{crossJob:false,hasTargetReport:false});
  let copied=''; await h.session.copy(preview(h),async s=>{copied=s;});
  assert.equal(copied.includes('STALE TARGET ORIGINAL'),false);
  assert.equal(h.state().saved.references.length,1,'retain original reference identity');
});

test('source revalidation pending rejects confirmation based on the old preview',async()=>{
  const d=deferred(); let refreshing=false;
  const h=setup({listReferences:async()=>refreshing ? d.promise : [option]});
  await h.session.load('task'); const oldPreview=preview(h); refreshing=true;
  const run=h.session.refreshReferences('task');
  let writes=0; await h.session.copy(oldPreview,async()=>{writes++;});
  d.resolve([]); await run;
  assert.equal(writes,0);
});

test('failed source revalidation rejects confirmation based on the old preview',async()=>{
  let fail=false;
  const h=setup({listReferences:async()=>{if(fail)throw new Error('offline');return [option];}});
  await h.session.load('task'); const oldPreview=preview(h); fail=true;
  await h.session.refreshReferences('task');
  let writes=0; await h.session.copy(oldPreview,async()=>{writes++;});
  assert.equal(writes,0);
});

test('late save receipt cannot downgrade a newer baseline read from the server',async()=>{
  const saved=deferred(); let readingNew=false;
  const h=setup({getDraft:async()=>draft(readingNew?3:1),saveDraft:async()=>saved.promise});
  await h.session.load('task');
  const saving=h.session.save('task'); readingNew=true;
  await h.session.load('task');
  saved.resolve(draft(2)); await saving;
  assert.equal(h.state().saved.revision,3);
  assert.equal(h.state().saving,false);
});
