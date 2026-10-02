import test from "node:test";
import assert from "node:assert/strict";
import { notificationHref, applicationAnchorId, clearApplicationAnchor, includeApplicationTarget } from "../src/lib/notification-session.ts";
test("notification destinations permit only authorized application pages", () => {
  const id = "b7095e9d-b1d7-4dc5-bb74-a9961eec999f";
  assert.ok(notificationHref(`/applications#application-${id}`));
  assert.ok(notificationHref(`/jobs/${id}/applications#application-${id}`));
  for (const href of ["https://evil.example", "//evil.example", `/reports/${id}`, "/applications", `/applications#application-${id}?redirect=https://evil.example`]) assert.equal(notificationHref(href), false);
});

test("notification target outside recent 100 is fetched with a scoped read", async()=>{
  const id="b7095e9d-b1d7-4dc5-bb74-a9961eec999f";
  assert.equal(applicationAnchorId(`#application-${id}`),id);
  assert.equal(applicationAnchorId(`#application-${id}?evil=1`),null);
  const items=Array.from({length:100},(_,i)=>({id:`recent-${i}`,jobId:"job"}));let calls=0;
  const result=await includeApplicationTarget(items,async requested=>{calls++;assert.equal(requested,id);return {id,jobId:"job"};},id,"job");
  assert.equal(calls,1);assert.equal(result.length,101);assert.equal(result[100].id,id);
  assert.equal(await includeApplicationTarget(result,()=>{throw new Error("unexpected duplicate read");},id,"job"),result);
});
test("revoked or wrong-job notification target cannot enter an authorized board", async()=>{
  const items=[{id:"authorized",jobId:"job"}];let unavailable=0;
  const dismissed=()=>{unavailable++;};
  assert.equal(await includeApplicationTarget(items,async()=>{throw {status:404};},"a","job",dismissed),items);
  assert.equal(await includeApplicationTarget(items,async()=>({id:"a",jobId:"other"}),"a","job",dismissed),items);
  assert.equal(await includeApplicationTarget(items,async()=>({id:"other",jobId:"job"}),"a","job",dismissed),items);
  assert.equal(unavailable,3);
  await assert.rejects(includeApplicationTarget(items,async()=>{throw new Error("network down");},"a","job",dismissed),/network down/);
  assert.equal(unavailable,3);
});

test("only the stale application anchor is removed without dropping query parameters",()=>{
  const id="b7095e9d-b1d7-4dc5-bb74-a9961eec999f";
  const previousLocation=globalThis.location, previousHistory=globalThis.history;
  const calls=[];
  try {
    globalThis.location={hash:`#application-${id}`,pathname:"/applications",search:"?page=2"};
    globalThis.history={state:{tab:1},replaceState:(...args)=>calls.push(args)};
    clearApplicationAnchor("other");
    assert.equal(calls.length,0);
    clearApplicationAnchor(id);
    assert.deepEqual(calls,[[{tab:1},"","/applications?page=2"]]);
  } finally {
    if(previousLocation===undefined)delete globalThis.location;else globalThis.location=previousLocation;
    if(previousHistory===undefined)delete globalThis.history;else globalThis.history=previousHistory;
  }
});
