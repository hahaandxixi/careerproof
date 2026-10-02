import test from "node:test";
import assert from "node:assert/strict";
import { notificationHref, applicationAnchorId, includeApplicationTarget } from "../src/lib/notification-session.ts";
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
  await assert.rejects(includeApplicationTarget([],async()=>{throw new Error("404 revoked");},"a","job"),/revoked/);
  await assert.rejects(includeApplicationTarget([],async()=>({id:"a",jobId:"other"}),"a","job"),/不一致/);
  await assert.rejects(includeApplicationTarget([],async()=>({id:"other",jobId:"job"}),"a","job"),/不一致/);
});
