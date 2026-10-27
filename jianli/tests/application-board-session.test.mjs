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
  assert.match(h.state().notice, /不在当前列表/);
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
    const h = setup({ [operation]: async () => {
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


test("server filtering retains an opened snapshot only after fresh exact authorization", async () => {
  let filtered = false, checks = 0;
  const h = setup({
    list: async () => filtered ? [] : [{ id: "a" }],
    detail: async id => { checks += 1; assert.equal(id, "a"); return { id, status: "viewed" }; },
  });
  await h.session.open("a");
  filtered = true;
  assert.equal(await h.session.filter(), true);
  assert.equal(checks, 1);
  assert.equal(h.state().selected.report.summary, candidate.report.summary);
  assert.deepEqual(h.state().items, []);
});
test("filter absence cannot retain a revoked snapshot or restore after tab hiding", async () => {
  let filtered = false;
  const auth = deferred();
  const h = setup({ list: async () => filtered ? [] : [{id:"a"}], detail: () => auth.promise });
  await h.session.open("a");
  filtered = true;
  const filtering = h.session.filter();
  await Promise.resolve(); await Promise.resolve();
  h.session.clear();
  auth.resolve({id:"a"});
  assert.equal(await filtering, false);
  assert.equal(h.state().selected, null);
  const revoked = setup({ list: async () => filtered ? [] : [{id:"a"}], detail: async () => { throw new Error("授权已撤回"); } });
  filtered = false;
  await revoked.session.open("a");
  filtered = true;
  assert.equal(await revoked.session.filter(), false);
  assert.equal(revoked.state().selected, null);
  assert.equal(revoked.state().error, "授权已撤回");
});


for (const presentInList of [true, false]) {
  test(`filter refreshes authoritative reply metadata while preserving only fixed report (present=${presentInList})`, async () => {
    let replied = false;
    const fixedReport = { id: "fixed-report", summary: "immutable authorization snapshot" };
    const references = [{ requirementId: "requirement-a", citationIds: ["R1-E1"] }];
    const remote = () => ({ id: "a", jobId: "job-a", status: replied ? "replied" : "viewed",
      replyKind: replied ? "continue" : null, replyText: replied ? "企业在另一窗口已回复" : null,
      replyReferences: replied ? references : [], events: replied ? [{ type: "replied", at: "2026-10-22T10:00:00Z", detail: "已回复" }] : [],
    });
    let checks = 0;
    const h = setup({
      list: async () => replied && !presentInList ? [] : [remote()],
      open: async () => ({...remote(), report: fixedReport}),
      detail: async () => { checks++; return remote(); },
    });
    await h.session.open("a");
    replied = true;
    assert.equal(await h.session.filter(), true);
    const selected = h.state().selected;
    assert.equal(selected.status, "replied");
    assert.equal(selected.replyKind, "continue");
    assert.equal(selected.replyText, "企业在另一窗口已回复");
    assert.deepEqual(selected.replyReferences, references);
    assert.equal(selected.events[0].type, "replied");
    assert.equal(selected.report, fixedReport);
    assert.equal(checks, presentInList ? 0 : 1);
  });
}

const fixed = { ...candidate, jobId: "job-a", reportId: "report-a", report: {id:"report-a", summary:"固定快照"} };
const metadata = (id = "a") => ({ id, jobId:"job-a", reportId:`report-${id}`, status:"viewed", replyText:null });

test("resume gates the cached immutable report behind a fresh read and never opens it again", async () => {
  const pending = deferred(); let paused = false, opens = 0;
  const h = setup({ list: () => paused ? pending.promise : Promise.resolve([metadata()]),
    open: async () => { opens++; return fixed; } });
  await h.session.open("a"); paused = true; h.session.suspend();
  assert.equal(h.state().selected, null);
  const resuming = h.session.resume(["a"]);
  assert.equal(h.state().selected, null); assert.equal(h.state().loading, true);
  pending.resolve([{...metadata(), status:"replied", replyText:"合成企业在其他窗口的回复"}]);
  const result = await resuming;
  assert.deepEqual(result.authorizedIds,["a"]);
  assert.equal(h.state().selected.report,fixed.report);
  assert.equal(h.state().selected.status,"replied");
  assert.equal(h.state().selected.replyText,"合成企业在其他窗口的回复");
  assert.equal(opens,1,"restoration must not POST another viewed event");
});

test("resume rechecks off-page comparison IDs with read-only detail and excludes withdrawn ones", async () => {
  const checks=[]; const h=setup({list:async()=>({items:[metadata()],total:5,page:1,pageSize:1}),open:async()=>fixed,
    detail:async id=>{checks.push(id);return {...metadata(id),status:id==="c"?"withdrawn":"viewed"};}});
  await h.session.open("a"); h.session.suspend();
  const result=await h.session.resume(["a","b","c"]);
  assert.deepEqual(checks,["b","c"]);
  assert.deepEqual(result.authorizedIds,["a","b"]);
  assert.deepEqual(h.state().items.map(x=>x.id),["a","b"]);
  assert.equal(h.state().pagination.total,5);
  assert.equal(h.state().pagination.pageItemCount,1);
  assert.match(h.state().notice,/清除/);
});

test("withdrawn permission, identity mismatch or failed authorization never restores a report", async () => {
  for(const reason of ["withdrawn","report_changed","denied"]){
    let paused=false;
    const h=setup({list:async()=>paused?reason==="report_changed"?[{...metadata(),reportId:"another-report"}]:[]:[metadata()],
      open:async()=>fixed,detail:async()=>{throw new Error("无权访问");}});
    await h.session.open("a");paused=true;h.session.suspend();
    const result=await h.session.resume(["a"]);
    assert.equal(h.state().selected,null,reason);
    assert.deepEqual(result.authorizedIds,[],reason);
    assert.match(h.state().notice,/清除/,reason);
    assert.equal((await h.session.resume()).selectedId,null,"revoked cache must be discarded");
  }
});

test("rapid hidden/visible events share in-flight reads and stale authorization cannot win", async () => {
  const first=deferred(),last=deferred();let reads=0,opens=0;
  const h=setup({list:()=>++reads===1?Promise.resolve([metadata()]):reads===2?first.promise:last.promise,
    open:async()=>{opens++;return fixed;}});
  await h.session.open("a");h.session.suspend();
  const a=h.session.resume(["a"]),b=h.session.resume(["a"]);
  assert.equal(a,b);assert.equal(reads,2);
  h.session.suspend();const c=h.session.resume(["a"]);assert.equal(a,c);
  first.resolve([metadata()]);await Promise.resolve();await Promise.resolve();
  assert.equal(h.state().selected,null,"a response from before the second hide is insufficient");
  last.resolve([metadata()]);await c;
  assert.equal(reads,3);assert.equal(opens,1);
  assert.equal(h.state().selected.report,fixed.report);
});

test("dispose and explicit clear discard restoration cache, including after reactivation",async()=>{
  for(const action of ["clear","dispose"]){
    const h=setup({list:async()=>[metadata()],open:async()=>fixed});
    await h.session.open("a");h.session.suspend();h.session[action]();h.session.activate();
    await h.session.resume();assert.equal(h.state().selected,null);
  }
});
