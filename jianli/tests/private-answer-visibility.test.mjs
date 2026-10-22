// Actual production session regression: tab hiding must not discard private edits.
// PRODUCT-01 前端回归：私人回答草稿的保存/刷新/冲突/身份清理/引用选择/预览复制。
// 无浏览器依赖：注入合成 API 驱动真实 workflow 会话；组件面板用 sucrase 转译后做 SSR 与直接 props 断言。
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(here, "../src");
const require = createRequire(import.meta.url);
const { transform } = require("sucrase");

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("next/") && !specifier.endsWith(".js")) {
      try { return nextResolve(specifier + ".js", context); } catch {}
      return nextResolve(specifier, context);
    }
    if (specifier.startsWith("@/")) {
      const base = path.join(SRC, specifier.slice(2));
      for (const candidate of [base, base + ".ts", base + ".tsx", path.join(base, "index.ts"), path.join(base, "index.tsx")]) {
        try { return nextResolve(pathToFileURL(candidate).href, context); } catch {}
      }
      throw new Error(`无法解析别名导入：${specifier}`);
    }
    if ((specifier.startsWith("./") || specifier.startsWith("../")) && !path.extname(specifier)) {
      for (const suffix of ["", ".ts", ".tsx", "/index.ts", "/index.tsx", ".js", "/index.js"]) {
        try { return nextResolve(new URL(specifier + suffix, context.parentURL).href, context); } catch {}
      }
      return nextResolve(specifier, context);
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".ts") || url.endsWith(".tsx")) {
      const out = transform(readFileSync(fileURLToPath(url), "utf8"), {
        transforms: ["typescript", "jsx"], jsxRuntime: "automatic", production: false, filePath: url,
      });
      return { format: "module", source: out.code, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});

const { createPrivateAnswerSession, initialPrivateAnswerState, privateAnswerIsDirty } =
  await import(pathToFileURL(path.join(SRC, "lib/private-answer-workflow.ts")).href);

const BASE_REPORT = "11111111-1111-1111-1111-111111111111";
const TARGET_REPORT = "22222222-2222-2222-2222-222222222222";
const REQUIREMENT = "99999999-9999-9999-9999-999999999999";

const baseOption = (over = {}) => ({
  reportId: BASE_REPORT, requirementId: REQUIREMENT, citationId: "R1-E1", reportKind: "base",
  filePath: "src/retry.ts", lineStart: 10, lineEnd: 20, provenance: "portfolio", ...over,
});
const targetOption = (over = {}) => baseOption({
  reportId: TARGET_REPORT, citationId: "T9-E1", reportKind: "target",
  filePath: "src/target.py", lineStart: 5, lineEnd: 9, provenance: "reference", ...over,
});
const savedView = (over = {}) => ({
  taskId: "task-1", requirementId: REQUIREMENT, text: "已保存的正文", revision: 1,
  updatedAt: "2026-10-06T01:02:03+00:00", boundary: "私人草稿仅本人可见。", references: [], ...over,
});
const savedReference = (over = {}) => ({
  reportId: BASE_REPORT, requirementId: REQUIREMENT, citationId: "R1-E1", available: true,
  snippet: "保存回执里的真实片段", filePath: "src/retry.ts", lineStart: 10, lineEnd: 20,
  provenance: "portfolio", ...over,
});

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function setup(overrides = {}) {
  const states = [];
  const calls = { getDraft: [], saveDraft: [], listReferences: [] };
  const defaults = {
    getDraft: async () => savedView(),
    saveDraft: async (id, payload) => savedView({
      text: payload.text, revision: payload.expectedRevision + 1,
      references: payload.references.map(r => savedReference({ ...r })),
    }),
    listReferences: async () => [baseOption(), targetOption()],
    errorMessage: error => (error instanceof Error ? error.message : String(error)),
  };
  const merged = { ...defaults, ...overrides };
  // 调用记录独立于替身实现：overrides 只替换行为，不得丢失请求计数（否则409等流程无法断言）。
  const session = createPrivateAnswerSession({
    getDraft: async id => { calls.getDraft.push(id); return merged.getDraft(id); },
    saveDraft: async (id, payload) => { calls.saveDraft.push({ id, payload }); return merged.saveDraft(id, payload); },
    listReferences: async id => { calls.listReferences.push(id); return merged.listReferences(id); },
    errorMessage: merged.errorMessage,
  }, state => states.push(state));
  session.activate();
  return { session, state: () => states.at(-1) ?? initialPrivateAnswerState, calls };
}


test("ordinary hidden/visible preserves unsaved text and selected references", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.setText("查询代码前的未保存编辑");
  h.session.toggleReference(baseOption());
  await h.session.visibilityChanged(false, "task-1");
  await h.session.visibilityChanged(true, "task-1");
  assert.equal(h.state().text, "查询代码前的未保存编辑");
  assert.equal(h.state().selected.length, 1);
  assert.equal(privateAnswerIsDirty(h.state()), true);
  assert.equal(h.calls.saveDraft.length, 0, "切标签页不自动发出保存或企业消息");
});

test("failed explicit save survives hide/resume and only explicit retry sends PUT", async () => {
  let saves = 0;
  const h = setup({ saveDraft: async (_id, payload) => {
    if (++saves === 1) throw new Error("保存失败（合成）");
    return savedView({ text: payload.text, revision: payload.expectedRevision + 1 });
  }});
  await h.session.load("task-1");
  h.session.setText("保存失败后不能丢弃"); h.session.toggleReference(baseOption());
  assert.equal(await h.session.save("task-1"), false);
  assert.match(h.state().error, /保存失败/);
  await h.session.visibilityChanged(false, "task-1");
  await h.session.visibilityChanged(true, "task-1");
  assert.equal(h.state().text, "保存失败后不能丢弃");
  assert.equal(h.state().selected.length, 1);
  assert.equal(saves, 1);
  assert.equal(h.state().saving, false);
  assert.ok(await h.session.save("task-1"));
  assert.equal(saves, 2);
});

test("hide invalidates pending save response; resume reconciles server revision without replacing edit", async () => {
  const gate = deferred(); let stored = savedView();
  const h = setup({ getDraft: async () => stored, saveDraft: () => gate.promise });
  await h.session.load("task-1"); h.session.setText("发起保存的文字");
  const pending = h.session.save("task-1");
  h.session.setText("保存期间继续编辑的文字");
  await h.session.visibilityChanged(false, "task-1");
  assert.equal(await h.session.save("task-1"), false, "隐藏期间拒绝旧DOM动作");
  stored = savedView({ text: "发起保存的文字", revision: 2 }); gate.resolve(stored);
  assert.equal(await pending, false);
  assert.equal(h.state().saved.revision, 1, "迟到回执不得更新暂停会话");
  await h.session.visibilityChanged(true, "task-1");
  assert.equal(h.state().saved.revision, 2);
  assert.equal(h.state().text, "保存期间继续编辑的文字");
  assert.equal(privateAnswerIsDirty(h.state()), true);
  assert.equal(h.state().saving, false);
});

test("second hide invalidates old resume read and later recovery still preserves local edits", async () => {
  const oldRead = deferred(); let reads = 0;
  const h = setup({ getDraft: async () => ++reads === 2 ? oldRead.promise : savedView({ revision: reads }) });
  await h.session.load("task-1"); h.session.setText("两个恢复请求之间的编辑");
  await h.session.visibilityChanged(false, "task-1");
  const firstResume = h.session.visibilityChanged(true, "task-1");
  await h.session.visibilityChanged(false, "task-1");
  assert.ok(await h.session.visibilityChanged(true, "task-1"));
  oldRead.resolve(savedView({ text: "旧读取结果", revision: 9 }));
  assert.equal(await firstResume, false);
  assert.equal(h.state().text, "两个恢复请求之间的编辑");
  assert.equal(h.state().saved.revision, 3);
  assert.equal(h.state().reading, false);
});

test("task/account disposal prevents old save/load and visibility callbacks from reaching new session", async () => {
  const oldSave = deferred(); const oldLoad = deferred();
  const alice = setup({ saveDraft: () => oldSave.promise, getDraft: async () => oldLoad.promise });
  const reading = alice.session.load("task-A");
  alice.session.setText("A的私有编辑");
  const saving = alice.session.save("task-A");
  alice.session.dispose();
  const bob = setup({ getDraft: async () => savedView({ taskId:"task-B", text:"B的已保存内容" }) });
  await bob.session.load("task-B");
  assert.equal(await alice.session.visibilityChanged(true, "task-A"), false);
  alice.session.activate();
  assert.equal(await alice.session.save("task-A"), false);
  oldLoad.resolve(savedView({text:"A的迟到读取"})); oldSave.resolve(savedView({ text:"A的迟到保存", revision:2 }));
  assert.equal(await reading, false); assert.equal(await saving, false);
  assert.equal(bob.state().text, "B的已保存内容");
  assert.equal(bob.calls.getDraft.length, 1);
  assert.equal(bob.calls.saveDraft.length, 0);
});

test("restore read failure keeps local draft recoverable and copy remains blocked until source check succeeds", async () => {
  let fail = false;
  const h = setup({ listReferences: async () => { if (fail) throw new Error("重读失败"); return [baseOption()]; } });
  await h.session.load("task-1"); h.session.setText("恢复失败仍应保留的文字");
  await h.session.visibilityChanged(false,"task-1"); fail=true;
  assert.equal(await h.session.visibilityChanged(true,"task-1"),false);
  assert.equal(h.state().text,"恢复失败仍应保留的文字");
  assert.match(h.state().error,/重读失败/);
  assert.equal(h.state().sourceCheck,"failed");
  const copies=[];
  assert.equal(await h.session.copy("不能发送",async t=>copies.push(t)),false);
  assert.deepEqual(copies,[]);
  fail=false;
  assert.ok(await h.session.visibilityChanged(true,"task-1"));
  assert.equal(h.state().text,"恢复失败仍应保留的文字");
});
