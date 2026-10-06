// Independent diagnosis against immutable copies; no API, browser or clipboard used.
import { registerHooks } from 'node:module';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
registerHooks({resolve(specifier,context,next){
  if(specifier.startsWith('.') && !/\.[a-z]+$/i.test(specifier)){
    try { return next(specifier+'.ts',context); } catch {}
  }
  return next(specifier,context);
}});
const source=process.env.PRIVATE_ANSWER_SOURCE_FILE ? pathToFileURL(resolve(process.env.PRIVATE_ANSWER_SOURCE_FILE)).href : './private-answer-workflow.ts';
const { createPrivateAnswerSession }=await import(source);
const view=(revision=1)=>({taskId:'task',requirementId:'req',text:'stored',references:[],revision,updatedAt:'2026-10-06',boundary:'private'});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function setup(overrides={}){
  let state, puts=0, gets=0;
  const session=createPrivateAnswerSession({
    getDraft:async()=>{gets++;return view();},listReferences:async()=>[],
    saveDraft:async()=>{puts++;return view(2);},errorMessage:String,...overrides,
  },value=>state=value);
  session.activate();
  return {session,state:()=>state,puts:()=>puts,gets:()=>gets};
}
test('copy cannot invalidate a successful in-flight save or strand busy',async()=>{
  const d=deferred(); const h=setup({saveDraft:async()=>d.promise});
  await h.session.load('task');
  const saving=h.session.save('task');
  await h.session.copy('confirmed preview',async()=>{});
  d.resolve(view(2));
  assert.equal(await saving,true);
  assert.equal(h.state().saving,false);
  assert.equal(h.state().saved.revision,2);
});
test('clear rejects an old save callback until owner explicitly reactivates',async()=>{
  const h=setup(); await h.session.load('task'); h.session.clear();
  await h.session.save('task');
  assert.equal(h.puts(),0);
});
test('a read response preserves edits typed after the read began',async()=>{
  const d=deferred(); const h=setup({getDraft:async()=>d.promise});
  const reading=h.session.load('task'); h.session.setText('typed after request');
  d.resolve(view()); await reading;
  assert.equal(h.state().text,'typed after request');
});
test('reload cannot invalidate an in-flight save and strand its busy flag',async()=>{
  const d=deferred(); const h=setup({saveDraft:async()=>d.promise});
  await h.session.load('task');
  const saving=h.session.save('task');
  await h.session.load('task');
  d.resolve(view(2));
  assert.equal(await saving,true);
  assert.equal(h.state().saving,false);
  assert.equal(h.state().saved.revision,2);
});
