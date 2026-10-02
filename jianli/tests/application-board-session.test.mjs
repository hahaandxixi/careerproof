import { test } from "node:test";
import assert from "node:assert/strict";
import { createApplicationBoardSession } from "../src/lib/application-board-session.ts";

const candidate = { id: "a", status: "viewed", report: { summary: "合成授权报告" } };
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function setup(overrides = {}) {
  const snapshots = [];
  const session = createApplicationBoardSession({
    list: async () => [{ id: "a", status: "viewed" }],
    open: async () => candidate,
    download: async () => ({ blob: new Blob(["合成简历"]), filename: "CP08.txt" }),
    reply: async () => ({ id: "a", status: "replied" }),
    errorMessage: e => e.message,
    ...overrides,
  }, state => snapshots.push(state));
  session.activate();
  return { session, snapshots, state: () => snapshots.at(-1) };
}

test("pending list does not claim an empty result; refresh immediately removes the opened report", async () => {
  const list = deferred();
  let wait = false;
  const h = setup({ list: () => wait ? list.promise : Promise.resolve([{ id: "a" }]) });
  await h.session.open("a");
  assert.equal(h.state().selected.report.summary, "合成授权报告");
  wait = true;
  const refreshing = h.session.refresh();
  assert.equal(h.state().loading, true);
  assert.equal(h.state().selected, null);
  list.resolve([]);
  await refreshing;
  assert.equal(h.state().loading, false);
  assert.deepEqual(h.state().items, []);
});

test("withdrawal between report response and authorization refresh prevents exporting that report", async () => {
  const list = deferred();
  const h = setup({ list: () => list.promise });
  const opening = h.session.open("a");
  list.resolve([]);
  await opening;
  assert.equal(h.state().selected, null);
  assert.match(h.state().notice, /不可访问/);
});

test("a response started before a newer refresh cannot restore revoked content", async () => {
  const open = deferred();
  const h = setup({ open: () => open.promise, list: async () => [] });
  const opening = h.session.open("a");
  await h.session.refresh();
  open.resolve(candidate);
  await opening;
  assert.equal(h.state().selected, null);
  assert.deepEqual(h.state().items, []);
});

test("switching between two applications keeps the selected report and reply target aligned", async () => {
  const first = deferred();
  const calls = [];
  const h = setup({
    list: async () => [{ id: "a" }, { id: "b" }],
    open: async id => id === "a" ? first.promise : {
      id: "b", status: "viewed", report: { summary: "合成 B 报告" },
    },
    reply: async (id, kind, text, references) => {
      calls.push({ id, kind, text, references });
      return { id, status: "replied" };
    },
  });
  const oldOpen = h.session.open("a");
  assert.equal(await h.session.open("b"), true);
  first.resolve(candidate);
  assert.equal(await oldOpen, false);
  assert.equal(h.state().selected.id, "b");
  assert.equal(h.state().selected.report.summary, "合成 B 报告");
  const references = [{ requirementId: "b-requirement", citationIds: ["B-E1"] }];
  assert.equal(await h.session.reply("continue", "合成 B 的人工核验问题", references), true);
  assert.deepEqual(calls, [{
    id: "b", kind: "continue", text: "合成 B 的人工核验问题", references,
  }]);
});

test("window hiding and effect disposal invalidate requests, including across reactivation", async () => {
  for (const action of ["clear", "dispose"]) {
    const open = deferred();
    const h = setup({ open: () => open.promise });
    const opening = h.session.open("a");
    h.session[action]();
    h.session.activate();
    await h.session.refresh();
    const current = h.state();
    open.resolve(candidate);
    await opening;
    assert.equal(h.state(), current);
    assert.equal(h.state().selected, null);
  }
});

test("download bytes are not delivered after a withdrawal or an intervening window clear", async () => {
  for (const outcome of ["withdrawn", "hidden"]) {
    const file = deferred();
    let authorized = true, deliveries = 0;
    const h = setup({ list: async () => authorized ? [{ id: "a" }] : [], download: () => file.promise });
    await h.session.open("a");
    const downloading = h.session.download(() => deliveries++);
    if (outcome === "withdrawn") authorized = false;
    else h.session.clear();
    file.resolve({ blob: new Blob(["合成简历"]), filename: "CP08.txt" });
    await downloading;
    assert.equal(deliveries, 0);
    assert.equal(h.state().selected, null);
  }
});

test("failed read, download, or reply leaves no stale report and remains retryable", async () => {
  for (const operation of ["open", "download", "reply"]) {
    let fail = false;
    const failure = async () => { throw new Error("授权失效（合成错误）"); };
    const h = setup({ [operation]: async (...args) => {
      if (fail) return failure();
      return operation === "download" ? { blob: new Blob(), filename: "CP08.txt" } : candidate;
    } });
    await h.session.open("a");
    fail = true;
    if (operation === "open") await h.session.open("a");
    else if (operation === "download") await h.session.download(() => assert.fail("must not deliver"));
    else assert.equal(await h.session.reply("continue", "合成测试回复，不是招聘决定"), false);
    assert.equal(h.state().selected, null);
    assert.deepEqual(h.state().items, []);
    assert.equal(h.state().loading, false);
    assert.match(h.state().error, /授权失效/);
    fail = false;
    await h.session.open("a");
    assert.equal(h.state().selected.id, "a");
  }
});

test("reply only reports confirmed delivery after detail and authorization reread", async () => {
  const h = setup();
  await h.session.open("a");
  assert.equal(await h.session.reply("continue", "合成测试回复", []), true);
  assert.equal(h.state().selected.id, "a");
});

test("a successful download reports browser delivery without claiming disk persistence", async () => {
  const h = setup();
  await h.session.open("a");
  let file;
  await h.session.download(value => { file = value; });
  assert.equal(await file.blob.text(), "合成简历");
  assert.match(h.state().notice, /不证明文件已保存/);
  assert.equal(h.state().selected.id, "a");
});

test("window cleanup triggered by browser download cannot restore the old report", async () => {
  const h = setup();
  await h.session.open("a");
  await h.session.download(() => h.session.clear());
  assert.equal(h.state().selected, null);
  assert.equal(h.state().notice, "");
});
