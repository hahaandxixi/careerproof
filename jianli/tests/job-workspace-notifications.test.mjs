import test from "node:test";
import assert from "node:assert/strict";
import { openStudentNotification } from "../src/lib/notification-session.ts";

const outsidePage = "d6dc7c07-4f10-4b5a-94de-b0a34a3cef93";
const href = `/applications#application-${outsidePage}`;

test("an out-of-page notification opens only its authorized detail and then marks the notice read", async () => {
  const calls = [];
  const result = await openStudentNotification("notice", {
    async notificationTarget(id) { calls.push(["target", id]); return { href }; },
    async applicationDetail(id) { calls.push(["detail", id]); return { id }; },
    async readNotification(id) { calls.push(["read", id]); },
  }, () => true, () => calls.push(["count"]));
  assert.deepEqual(result, {id:outsidePage});
  assert.deepEqual(calls, [["target","notice"], ["detail",outsidePage], ["read","notice"], ["count"]]);
});

test("loss of access or invalid destinations never mark a student notification read", async () => {
  const api = {
    async notificationTarget() { return { href }; },
    async applicationDetail() { throw new Error("投递不可访问"); },
    async readNotification() { assert.fail("read must not run"); },
  };
  await assert.rejects(openStudentNotification("notice", api, () => true, assert.fail), /投递不可访问/);
  await assert.rejects(openStudentNotification("notice", { ...api,
    async notificationTarget() { return { href: `/jobs/${outsidePage}${href}` }; },
  }, () => true, assert.fail), /目的地无效/);
});

test("closing during a delayed read prevents selection but permits recount after successful write", async () => {
  let open = true;
  let finish;
  let counts = 0;
  let pending = false;
  const operation = openStudentNotification("notice", {
    async notificationTarget() { return { href }; },
    async applicationDetail(id) { return { id }; },
    readNotification() { pending = true; return new Promise(resolve => { finish=resolve; }); },
  }, () => open, () => { counts++; });
  await Promise.resolve();
  await Promise.resolve();
  assert.ok(pending);
  open = false;
  finish();
  assert.equal(await operation, undefined);
  assert.equal(counts, 1);
});
