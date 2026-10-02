import test from "node:test";
import assert from "node:assert/strict";
import { createApplicationListSession } from "../src/lib/application-list-session.ts";
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; }
function setup(overrides={}) {
  const snapshots=[];
  const session=createApplicationListSession({list:async()=>[{id:"a",replyText:"private reply"}],withdraw:async()=>({}),errorMessage:e=>e.message,...overrides}, state=>snapshots.push(state));
  session.activate(); return {session,state:()=>snapshots.at(-1)};
}
test("student list errors clear prior reply and do not masquerade as empty success",async()=>{
  let failed=false; const h=setup({list:async()=>{if(failed)throw new Error("connection failed");return [{id:"a",replyText:"private reply"}];}});
  await h.session.refresh(); failed=true; const refreshing=h.session.refresh(); assert.deepEqual(h.state().items,[]); assert.equal(h.state().loading,true);
  await refreshing; assert.deepEqual(h.state().items,[]); assert.equal(h.state().error,"connection failed");
});
test("hidden, disposed and replaced student requests cannot restore old replies",async()=>{
  for(const action of ["clear","dispose"]){ const read=deferred();let delayed=true;const h=setup({list:()=>delayed?read.promise:Promise.resolve([])});
    const loading=h.session.refresh();h.session[action]();h.session.activate();delayed=false;await h.session.refresh();const current=h.state();
    read.resolve([{id:"a",replyText:"stale private reply"}]);await loading;assert.equal(h.state(),current);assert.deepEqual(h.state().items,[]);
  }
});
test("withdrawal is single-flight and a late result cannot restore a hidden page",async()=>{
  const mutation=deferred();let calls=0,listCalls=0;
  const h=setup({withdraw:()=>{calls++;return mutation.promise;},list:async()=>{listCalls++;return [{id:"a"}];}});
  const first=h.session.withdraw("a");await h.session.withdraw("a");assert.equal(calls,1);h.session.clear();mutation.resolve({});await first;
  assert.equal(listCalls,0);assert.deepEqual(h.state().items,[]);
});
test("withdrawal success rereads current status rather than fabricating a state",async()=>{
  const h=setup({list:async()=>[{id:"a",status:"withdrawn"}]});await h.session.withdraw("a");assert.equal(h.state().items[0].status,"withdrawn");assert.equal(h.state().error,"");
});

test("focus refresh during withdrawal waits for committed status",async()=>{
  const mutation=deferred();let committed=false,reads=0;
  const h=setup({withdraw:async()=>{await mutation.promise;committed=true;},list:async()=>{reads++;assert.equal(committed,true);return [{id:"a",status:"withdrawn"}];}});
  const withdrawing=h.session.withdraw("a");await h.session.refresh();assert.equal(reads,0);mutation.resolve({});await withdrawing;
  assert.equal(h.state().items[0].status,"withdrawn");assert.equal(h.state().error,"");
});
