import test from "node:test";
import assert from "node:assert/strict";
import { createReportReviewSession } from "../src/lib/report-review-session.ts";

const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};
const failure=status=>Object.assign(new Error(`error-${status}`),{status});
const report=(id="r",revision=0)=>({id,revision,items:[{requirementId:"a"},{requirementId:"b"}]});
async function fixture(overrides={}){
 let state,reads=0,writes=0;
 const session=createReportReviewSession("r",{get:async()=>{reads++;return overrides.get?overrides.get(reads):report("r",reads);},review:async(...args)=>{writes++;return overrides.review?.(...args);},errorMessage:e=>e.message},value=>state=value);
 session.activate();await session.load();return{session,get state(){return state;},get reads(){return reads;},get writes(){return writes;}};
}
test("a confirmed write rejection stays local and retains the report",async()=>{
 const h=await fixture({review:async()=>{throw failure(409);}});const before=h.state.report;
 await h.session.review("a","accepted","private note");assert.equal(h.state.report,before);assert.equal(h.state.error,"");assert.equal(h.state.issues.a.outcome,"rejected");assert.equal(h.state.needsSync,false);assert.equal(h.reads,1);
});
test("a successful write with a failed GET retries only reading and preserves the report",async()=>{
 const h=await fixture({get:n=>n===2?Promise.reject(new Error("offline")):report("r",n)});const before=h.state.report;
 await h.session.review("a","accepted");assert.equal(h.state.report,before);assert.equal(h.state.issues.a.outcome,"saved");assert.equal(h.state.needsSync,true);
 await h.session.review("b","accepted");assert.equal(h.writes,1);
 await h.session.refresh("a");assert.equal(h.writes,1);assert.equal(h.reads,3);assert.equal(h.state.report.revision,3);assert.equal(h.state.needsSync,false);assert.equal(h.state.issues.a,undefined);
});
test("network, timeout, 5xx and invalid success envelopes have unknown outcomes until reread",async()=>{
 for(const status of [undefined,0,200,408,500]){
  const h=await fixture({review:async()=>{throw status===undefined?new Error("network"):failure(status);}});
  await h.session.review("a","rejected");assert.equal(h.state.issues.a.outcome,"unknown");assert.equal(h.state.needsSync,true);
  await h.session.review("b","corrected");assert.equal(h.writes,1);
  await h.session.refresh("a");assert.equal(h.writes,1);assert.equal(h.state.needsSync,false);
 }
});
test("one full write/read cycle blocks duplicate and different-requirement writes until synchronized",async()=>{
 const write=deferred(),read=deferred();let stored=[];
 const h=await fixture({review:async(_id,req,status,note)=>{stored.push([req,status,note]);await write.promise;},get:n=>n===2?read.promise:report("r",n)});
 const pending=h.session.review("a","accepted","note a");await h.session.review("a","accepted");await h.session.review("b","rejected");assert.equal(h.writes,1);
 write.resolve();await Promise.resolve();assert.equal(h.state.reviewing,"a");await h.session.review("b","corrected");assert.equal(h.writes,1);
 read.resolve(report("r",2));await pending;assert.equal(h.state.reviewing,null);assert.deepEqual(stored,[["a","accepted","note a"]]);
 await h.session.review("b","rejected","note b");assert.equal(h.writes,2);assert.equal(h.state.report.revision,3);
});
test("permission loss during either write or reread clears private report data",async()=>{
 for(const status of [401,403,404]){
  const write=await fixture({review:async()=>{throw failure(status);}});await write.session.review("a","accepted");assert.equal(write.state.report,null);assert.ok(write.state.error);
  const read=await fixture({get:n=>n===1?report():Promise.reject(failure(status))});await read.session.review("a","accepted");assert.equal(read.state.report,null);assert.ok(read.state.error);
 }
});
test("old reads and writes cannot publish after account/report disposal",async()=>{
 const old=deferred();let reads=0,state,published=0;
 const session=createReportReviewSession("old",{get:()=>{reads++;return old.promise;},review:async()=>{},errorMessage:String},next=>{state=next;published++;});
 session.activate();const pending=session.load();session.dispose();const count=published;old.resolve(report("old"));await pending;assert.equal(published,count);assert.equal(state.report,null);assert.equal(reads,1);
 const write=deferred();const h=await fixture({review:()=>write.promise});const p=h.session.review("a","accepted");h.session.dispose();write.resolve();await p;assert.equal(h.reads,1);
});
test("a response for another report is rejected instead of replacing the current one",async()=>{
 const h=await fixture({get:n=>report(n===1?"r":"other")});await h.session.review("a","accepted");assert.equal(h.state.report,null);assert.match(h.state.error,/报告身份不匹配/);
});
