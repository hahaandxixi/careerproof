import { test } from "node:test";
import assert from "node:assert/strict";
import { createApplicationBoardSession } from "../src/lib/application-board-session.ts";

const row = (id = "a") => ({ id, jobId: "job-a", reportId: `report-${id}`, status: "viewed", replyText: null });
const fixed = (id = "a") => ({ ...row(id), report: { id: `report-${id}`, summary: `private report ${id}` } });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
function setup() {
  let state, failure = "", responseError, remote = row();
  const calls = { reply: 0, view: 0, detail: 0, list: 0 };
  const api = {
    async list() { calls.list++; if (failure === "list") throw new Error("list unavailable"); return [remote]; },
    async open(id) { calls.view++; return id === remote.id ? { ...fixed(id), ...remote } : fixed(id); },
    async detail(id) {
      calls.detail++;
      if (failure === "detail") throw new Error("detail unavailable");
      if (failure === "denied") throw Object.assign(new Error("no access"), { status: 404, code: 4049 });
      return id === remote.id ? remote : row(id);
    },
    async reply(id, kind, text) {
      calls.reply++;
      if (responseError) throw responseError;
      remote = { ...row(id), status: "replied", replyKind: kind, replyText: text };
      return remote;
    },
    download: async () => { throw new Error("unused"); }, errorMessage: e => e.message,
  };
  const session = createApplicationBoardSession(api, value => { state = value; });
  session.activate();
  return { session, api, calls, state: () => state, fail: value => { failure = value; },
    reject: error => { responseError = error; }, remote: value => { remote = value; } };
}

for (const failure of ["detail", "list"]) {
  test(`confirmed reply + ${failure} read failure remains confirmed; recovery uses only GETs`, async () => {
    const h = setup();
    await h.session.open("a"); h.fail(failure);
    const result = await h.session.reply("continue", "private reply", []);
    assert.equal(result.write, "confirmed");
    assert.equal(result.refresh, "failed");
    assert.equal(result.applied, true);
    assert.equal(h.state().errorScope, failure === "list" ? "list" : "detail");
    assert.equal(h.state().selected, null);
    assert.equal(h.calls.reply, 1);
    assert.equal(h.calls.view, 1, "post-write refresh must not POST another viewed event");
    const failedRecovery = await h.session.refreshReply();
    assert.equal(failedRecovery.write, "confirmed");
    assert.equal(failedRecovery.refresh, "failed");
    h.fail("");
    const recovered = await h.session.refreshReply();
    assert.equal(recovered.write, "confirmed");
    assert.equal(recovered.refresh, "complete");
    assert.equal(h.state().selected.status, "replied");
    assert.equal(h.state().selected.replyText, "private reply");
    assert.equal(h.state().selected.report.id, "report-a");
    assert.equal(h.calls.reply, 1); assert.equal(h.calls.view, 1);
  });
}

test("initial list errors and empty results remain distinct; retry is only a list GET", async () => {
  const h = setup(); h.fail("list");
  assert.equal(await h.session.refresh(), false);
  assert.equal(h.state().errorScope, "list"); assert.equal(h.state().loading, false);
  h.fail(""); h.api.list = async () => [];
  assert.equal(await h.session.refresh(), true);
  assert.equal(h.state().error, ""); assert.equal(h.state().errorScope, undefined);
  assert.deepEqual(h.state().items, []);
  assert.equal(h.calls.reply, 0); assert.equal(h.calls.view, 0);
});

test("a normal successful reply is confirmed independently of its authorization read", async () => {
  const h = setup(); await h.session.open("a");
  const result = await h.session.reply("continue", "one reply");
  assert.equal(result.write, "confirmed"); assert.equal(result.refresh, "complete");
  assert.equal(h.state().selected.status, "replied");
  assert.equal(h.calls.reply, 1); assert.equal(h.calls.view, 1); assert.equal(h.calls.detail, 1);
});

for (const [status, code] of [[409, 4098], [422, 4220], [422, 4224], [404, 4049]]) {
  test(`explicit rejection (${status}/${code}) does not claim this request succeeded`, async () => {
    const h = setup(); await h.session.open("a");
    h.reject(Object.assign(new Error("server rejected reply"), { status, code }));
    const result = await h.session.reply("continue", "rejected draft");
    assert.equal(result.write, "rejected"); assert.equal(h.state().selected, null);
    assert.equal(result.accessLost, status === 404);
    if (status !== 404) {
      h.remote({ ...row(), status: "replied", replyText: "existing reply from another request" });
      const checked = await h.session.refreshReply();
      assert.equal(checked.write, "rejected", "409 plus a saved reply is not proof this request wrote it");
      assert.equal(checked.refresh, "complete");
      assert.equal(h.state().selected.replyText, "existing reply from another request");
    }
    assert.equal(h.calls.reply, 1); assert.equal(h.calls.view, 1);
  });
}

for (const error of [new Error("network timeout; reply rejected"), Object.assign(new Error("timeout"), { status: 408 }),
  Object.assign(new Error("server failed after commit"), { status: 500 }), Object.assign(new Error("bad response"), { status: 200 }),
  Object.assign(new Error("unknown conflict"), { status: 409, code: 4999 })]) {
  test(`uncertain result (${error.status ?? "network"}/${error.code ?? "none"}) stays unknown until a read, without resend`, async () => {
    const h = setup(); await h.session.open("a"); h.reject(error);
    const result = await h.session.reply("continue", "uncertain draft");
    assert.equal(result.write, "unknown"); assert.equal(h.state().selected, null);
    h.remote({ ...row(), status: "replied", replyText: "saved response" });
    const checked = await h.session.refreshReply();
    assert.equal(checked.write, "unknown", "a read cannot attribute the existing reply to this request");
    assert.equal(checked.refresh, "complete"); assert.equal(h.state().selected.status, "replied");
    assert.equal(h.calls.reply, 1); assert.equal(h.calls.view, 1);
  });
}

test("no duplicate write while sending, including when a new read changes the visible selection", async () => {
  const h = setup(), pending = deferred(); await h.session.open("a");
  h.api.reply = () => { h.calls.reply++; return pending.promise; };
  const sending = h.session.reply("continue", "first");
  assert.equal((await h.session.reply("continue", "duplicate")).write, "not_sent");
  await h.session.open("b");
  assert.equal(h.state().selected.id, "b");
  assert.equal((await h.session.reply("continue", "new while old is pending")).write, "not_sent");
  const newer = h.state(); pending.resolve({ ...row(), status: "replied" });
  assert.equal((await sending).applied, false);
  assert.equal(h.state(), newer); assert.equal(h.calls.reply, 1);
});

for (const lifecycle of ["suspend", "clear", "dispose"]) {
  test(`late write result after ${lifecycle} cannot restore content or a recovery target`, async () => {
    const h = setup(), pending = deferred(); await h.session.open("a");
    h.api.reply = () => { h.calls.reply++; return pending.promise; };
    const sending = h.session.reply("continue", "old identity draft");
    h.session[lifecycle](); h.session.activate(); await h.session.refresh();
    const newer = h.state(); pending.resolve({ ...row(), status: "replied" });
    const result = await sending;
    assert.equal(result.write, "confirmed"); assert.equal(result.applied, false);
    assert.equal(h.state(), newer); assert.equal(h.state().selected, null);
    assert.equal((await h.session.refreshReply()).write, "not_sent");
    assert.equal(h.calls.detail, 0); assert.equal(h.calls.reply, 1); assert.equal(h.calls.view, 1);
  });
}

test("permission loss after a confirmed write removes all report caches and blocks restoration", async () => {
  const h = setup(); await h.session.open("a"); await h.session.selectComparison(["a"]);
  h.fail("denied");
  const result = await h.session.reply("continue", "sent before withdrawal");
  assert.equal(result.write, "confirmed"); assert.equal(result.accessLost, true);
  assert.equal(h.state().selected, null); assert.deepEqual(h.state().comparison, []);
  assert.equal((await h.session.refreshReply()).write, "not_sent");
  h.fail(""); await h.session.resume(["a"]);
  assert.equal(h.state().selected, null); assert.ok(!h.state().comparison.some(item => item.report));
});

test("changed fixed report identity cannot reuse the old private snapshot", async () => {
  const h = setup(); await h.session.open("a"); h.fail("detail");
  await h.session.reply("continue", "sent"); h.fail("");
  h.remote({ ...row(), status: "replied", reportId: "different-report" });
  const checked = await h.session.refreshReply();
  assert.equal(checked.write, "confirmed"); assert.equal(checked.accessLost, true);
  assert.equal(h.state().selected, null);
});

test("a repeated recovery shares no extra operation and a late read cannot restore another application", async () => {
  const h = setup(), reading = deferred(); await h.session.open("a"); h.fail("list");
  await h.session.reply("continue", "confirmed"); h.fail("");
  const before = { ...h.calls };
  h.api.detail = () => {h.calls.detail++; return reading.promise;};
  const recovery = h.session.refreshReply();
  assert.equal((await h.session.refreshReply()).write, "not_sent");
  h.api.list = async () => [row("b")];
  await h.session.open("b"); const newer = h.state();
  reading.resolve({...row(),status:"replied"});
  assert.equal((await recovery).applied, false); assert.equal(h.state(), newer);
  assert.equal(h.calls.detail, before.detail + 1); assert.equal(h.calls.reply, 1);
  assert.equal(h.calls.view, before.view + 1, "only the explicit user open of B may add a view");
});

for (const lifecycle of ["suspend", "clear", "dispose"]) {
  test(`authorization read after write cannot restore private content after ${lifecycle}`, async () => {
    const h = setup(), reading = deferred(); await h.session.open("a");
    h.api.detail = () => {h.calls.detail++; return reading.promise;};
    const sending = h.session.reply("continue", "confirmed before leaving");
    await Promise.resolve(); await Promise.resolve();
    assert.equal(h.calls.detail, 1);
    h.session[lifecycle](); h.session.activate(); await h.session.refresh(); const newer = h.state();
    reading.resolve({...row(),status:"replied"});
    const result = await sending;
    assert.equal(result.write, "confirmed"); assert.equal(result.applied, false);
    assert.equal(h.state(), newer); assert.equal(h.state().selected, null);
    assert.equal((await h.session.refreshReply()).write, "not_sent");
    assert.equal(h.calls.reply, 1); assert.equal(h.calls.view, 1);
  });
}

test("a withdrawn list row after a successful detail read cannot restore the saved report", async () => {
  const h = setup(); await h.session.open("a");
  h.api.list = async () => [{...row(),status:"withdrawn"}];
  const result = await h.session.reply("continue", "already sent");
  assert.equal(result.write,"confirmed"); assert.equal(result.accessLost,true);
  assert.equal(h.state().selected,null); assert.equal((await h.session.refreshReply()).write,"not_sent");
});
