// Controlled races on finalized source, no real API/clipboard.
import {registerHooks} from 'node:module';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
registerHooks({resolve(s,c,next){if(s.startsWith('.')&&!/\.[a-z]+$/i.test(s)){try{return next(s+'.ts',c);}catch{}}return next(s,c);}});
assert.ok(process.env.PRIVATE_ANSWER_SOURCE_FILE);
const {createPrivateAnswerSession}=await import(pathToFileURL(process.env.PRIVATE_ANSWER_SOURCE_FILE).href);
const ref={reportId:'old-target',requirementId:'req',citationId:'cite',available:true,snippet:'original',filePath:'x.md',lineStart:1,lineEnd:1,provenance:'portfolio'};
const draft=(revision=1)=>({taskId:'task',requirementId:'req',text:'saved',references:[ref],revision,updatedAt:'today'});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function setup(){
 let state,reads=0,options=[{...ref,reportKind:'target'}],nextRead=null,nextOptions=null,nextSave=null;
 const session=createPrivateAnswerSession({getDraft:async()=>{reads++;return nextRead?.promise??draft();},listReferences:async()=>nextOptions?.promise??options,saveDraft:async()=>nextSave?.promise??draft(2),errorMessage:String},s=>state=s);
 session.activate();
 return {session,state:()=>state,read:d=>nextRead=d,options:o=>options=o,refresh:d=>nextOptions=d,save:d=>nextSave=d};
}
test('old GET cannot revive a citation rejected by a newer source validation',async()=>{
 const h=setup();await h.session.load('task');const d=deferred();h.read(d);
 const load=h.session.load('task');h.options([]);await h.session.refreshReferences('task');
 d.resolve(draft());await load;
 assert.equal(h.state().saved.references[0].available,false);
});
test('old successful PUT cannot revive a citation rejected after it was sent',async()=>{
 const h=setup();await h.session.load('task');const d=deferred();h.save(d);
 const save=h.session.save('task');h.options([]);await h.session.refreshReferences('task');
 d.resolve(draft(2));await save;
 assert.equal(h.state().saved.revision,2);
 assert.equal(h.state().saved.references[0].available,false);
 assert.equal(h.state().saving,false);
});
test('old GET cannot clear a newer pending source gate and permit confirmation',async()=>{
 const h=setup();await h.session.load('task');const read=deferred();h.read(read);
 const load=h.session.load('task');const check=deferred();h.refresh(check);
 const validation=h.session.refreshReferences('task');read.resolve(draft());await load;
 let writes=0;await h.session.copy('stale preview',async()=>{writes++;});
 check.resolve([]);await validation;
 assert.equal(writes,0);
});
