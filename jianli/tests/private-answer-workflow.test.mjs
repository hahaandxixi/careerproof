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

const {
  createPrivateAnswerSession, initialPrivateAnswerState, privateAnswerIsDirty,
  privateAnswerSaveProblem, privateAnswerReferenceKey, privateAnswerReferenceScopeNotice,
  buildPrivateAnswerPreviewDocument, PRIVATE_ANSWER_MAX_TEXT, PRIVATE_ANSWER_MAX_REFERENCES,
} = await import(pathToFileURL(path.join(SRC, "lib/private-answer-workflow.ts")).href);
const { api, ApiError } = await import(pathToFileURL(path.join(SRC, "lib/api/client.ts")).href);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const draftComponent = await import(pathToFileURL(path.join(SRC, "components/PrivateAnswerDraft.tsx")).href);

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

test("读取：无草稿也能先选原要求引用，首存 expectedRevision=0", async () => {
  const h = setup({ getDraft: async () => null });
  await h.session.load("task-1");
  const state = h.state();
  assert.equal(state.phase, "ready");
  assert.equal(state.text, "");
  assert.equal(state.saved, null);
  assert.equal(state.options.length, 2, "草稿不存在也要能读可选引用");
  h.session.toggleReference(baseOption());
  assert.equal(h.state().selected.length, 1);
  assert.ok(await h.session.save("task-1"));
  assert.deepEqual(h.calls.saveDraft[0].payload, {
    text: "",
    references: [{ reportId: BASE_REPORT, requirementId: REQUIREMENT, citationId: "R1-E1" }],
    expectedRevision: 0,
  });
  assert.equal(h.state().saved.revision, 1);
  assert.equal(privateAnswerIsDirty(h.state()), false);
});

test("保存期间继续编辑：旧回执只更新已存基线，不覆盖后来的文字", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.setText("第一版文字");
  const saved = h.session.save("task-1");
  h.session.setText("保存期间的新编辑");
  h.session.setText("更后来的编辑");
  await saved;
  const state = h.state();
  assert.equal(state.text, "更后来的编辑", "迟到回执不得覆盖保存期间的编辑");
  assert.equal(state.saved.revision, 2);
  assert.equal(state.saving, false);
  assert.equal(privateAnswerIsDirty(state), true);
  assert.equal(h.calls.saveDraft[0].payload.text, "第一版文字", "保存快照应是发起时的文字");
});

test("退出身份/任务清理：未保存内容丢弃，迟到的保存回执不得恢复任何状态", async () => {
  let send;
  const pending = new Promise(resolve => { send = resolve; });
  const h = setup({ saveDraft: () => pending.then(() => savedView({ text: "迟到的保存结果", revision: 2 })) });
  await h.session.load("task-1");
  h.session.setText("未保存就要被丢弃的文字");
  const saved = h.session.save("task-1");
  h.session.clear();
  send(savedView({ text: "迟到的保存结果", revision: 2 }));
  await saved;
  await new Promise(resolve => setImmediate(resolve));
  const state = h.state();
  assert.equal(state.text, "", "清理后不得被迟到回执写回文字");
  assert.equal(state.saved, null);
  assert.match(state.notice, /未保存.*丢弃|丢弃.*未保存/, "清理必须明确告知未保存内容会丢弃");
});

test("409：保留本人编辑；读服务器仅作对照不改基线；明确重存才用新 revision", async () => {
  const conflict = new ApiError("草稿已在其他保存中更新，请刷新读取最新版本后重试", 409, 4240, "req-409");
  let draftReads = 0;
  const savedPayloads = [];
  const h = setup({
    getDraft: async () => {
      draftReads += 1;
      return draftReads === 1
        ? savedView({ revision: 1, text: "本人保存过的旧版本" })
        : savedView({ revision: 5, text: "另一页面保存的新版本" });
    },
    saveDraft: async (id, payload) => {
      savedPayloads.push(payload);
      if (payload.expectedRevision !== 5) throw conflict;
      return savedView({ text: payload.text, revision: payload.expectedRevision + 1 });
    },
  });
  await h.session.load("task-1");
  h.session.setText("本人的编辑");
  assert.equal(await h.session.save("task-1"), false);
  let state = h.state();
  assert.equal(state.text, "本人的编辑", "409 必须保留本人编辑");
  assert.equal(state.conflict, true);
  assert.match(state.notice + state.error, /新版本|其他保存/);
  assert.equal(draftReads, 1, "409 后不得自动重读");
  // 显式读取服务器版本作对照：不得替换本人编辑、不得改写保存基线的 revision
  assert.ok(await h.session.compareWithServer("task-1"));
  state = h.state();
  assert.equal(state.serverCopy.revision, 5);
  assert.equal(state.text, "本人的编辑");
  assert.equal(state.saved.revision, 1, "对照读取不得取得新 revision 后自动覆盖基线");
  // 未明确选择覆盖时再次保存仍用旧 revision（会再次 409），不得借用对照读到的 revision
  assert.equal(await h.session.save("task-1"), false);
  assert.equal(h.calls.saveDraft.at(-1).payload.expectedRevision, 1);
  // 明确选择“以本人编辑重新保存”才使用服务器新 revision
  assert.ok(await h.session.saveOverServer("task-1"));
  state = h.state();
  assert.equal(h.calls.saveDraft.at(-1).payload.expectedRevision, 5, "明确重存才使用服务器新 revision");
  assert.equal(state.text, "本人的编辑");
  assert.equal(state.saved.revision, 6);
  assert.equal(state.conflict, false);
  assert.equal(state.serverCopy, null);
});

test("网络失败：保留文字与选择，不自动重试", async () => {
  let attempts = 0;
  const h = setup({ saveDraft: async () => { attempts += 1; throw new Error("无法连接服务，请确认网络和后端运行状态后重试。"); } });
  await h.session.load("task-1");
  h.session.setText("失败前写好的文字");
  h.session.toggleReference(baseOption());
  assert.equal(await h.session.save("task-1"), false);
  const state = h.state();
  assert.equal(state.text, "失败前写好的文字");
  assert.equal(state.selected.length, 1);
  assert.match(state.error, /无法连接服务/);
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(attempts, 1, "失败后不得自动重试");
});

test("重复点击：保存进行中再次保存不发出第二个 PUT", async () => {
  const gate = deferred();
  let calls = 0;
  const h = setup({ saveDraft: (id, payload) => { calls += 1; return gate.promise.then(() => savedView({ text: payload.text, revision: 2 })); } });
  await h.session.load("task-1");
  h.session.setText("只应保存一次");
  const first = h.session.save("task-1");
  assert.equal(await h.session.save("task-1"), false, "保存中的重复点击必须被拒绝");
  gate.resolve(null);
  assert.ok(await first);
  assert.equal(calls, 1);
});

test("刷新重读已保存内容：显式读取替换本地编辑", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.setText("本地未保存编辑");
  assert.ok(await h.session.load("task-1"));
  assert.equal(h.state().text, "已保存的正文");
  assert.equal(privateAnswerIsDirty(h.state()), false);
});

test("清空内容也需明确保存；仅清空不删除服务端记录", async () => {
  const h = setup({ getDraft: async () => savedView({ text: "旧文字", revision: 2, references: [savedReference()] }) });
  await h.session.load("task-1");
  h.session.setText("");
  assert.equal(h.calls.saveDraft.length, 0, "只清空不保存不得发出请求");
  assert.ok(await h.session.save("task-1"));
  assert.equal(h.calls.saveDraft[0].payload.text, "");
  assert.equal(h.calls.saveDraft[0].payload.expectedRevision, 2);
  assert.equal(h.state().saved.revision, 3, "清空是保存空草稿，不是删除服务端记录");
});

test("引用键为三元组：两个报告同 citationId 不合并", async () => {
  const h = setup({ listReferences: async () => [baseOption(), targetOption({ citationId: "R1-E1" })] });
  await h.session.load("task-1");
  const options = h.state().options;
  h.session.toggleReference(options[0]);
  h.session.toggleReference(options[1]);
  assert.equal(h.state().selected.length, 2);
  assert.notEqual(
    privateAnswerReferenceKey(options[0].reportId, options[0].requirementId, options[0].citationId),
    privateAnswerReferenceKey(options[1].reportId, options[1].requirementId, options[1].citationId),
  );
  await h.session.save("task-1");
  assert.deepEqual(h.calls.saveDraft[0].payload.references, [
    { reportId: BASE_REPORT, requirementId: REQUIREMENT, citationId: "R1-E1" },
    { reportId: TARGET_REPORT, requirementId: REQUIREMENT, citationId: "R1-E1" },
  ]);
});

test("跨岗位目标没有原要求：解释为何不能用新要求回答原问题", () => {
  const notice = privateAnswerReferenceScopeNotice({ options: [baseOption()], crossJob: true, hasTargetReport: true });
  assert.match(notice, /原要求|原问题/);
  assert.match(notice, /新要求/);
  assert.equal(privateAnswerReferenceScopeNotice({ options: [baseOption(), targetOption()], crossJob: true, hasTargetReport: true }), "");
  assert.equal(privateAnswerReferenceScopeNotice({ options: [baseOption()], crossJob: false, hasTargetReport: false }), "");
});

test("预览只用保存回执的 snippet；失效引用不作为有效来源复制", () => {
  const saved = savedView({
    text: "本人的回答草稿",
    revision: 4,
    references: [
      savedReference({ provenance: "reference", reportId: TARGET_REPORT, citationId: "T9-E1" }),
      savedReference(),
      savedReference({ citationId: "GONE-E7", available: false, snippet: null, filePath: null, lineStart: null, lineEnd: null }),
    ],
  });
  const document = buildPrivateAnswerPreviewDocument({
    saved, requirementTitle: "异常处理", jobTitle: "后端工程师",
    baseReportId: BASE_REPORT, targetReportId: TARGET_REPORT,
  });
  assert.match(document, /异常处理/);
  assert.match(document, /本人的回答草稿/);
  assert.match(document, /保存回执里的真实片段/, "预览只能展示保存响应里的 snippet");
  assert.match(document, /第三方参考/, "参考证据要标第三方参考");
  const [sources, invalid] = document.split("已失效");
  assert.match(sources, /R1-E1/);
  assert.match(sources, /T9-E1/);
  assert.ok(!sources.includes("GONE-E7"), "失效引用不得出现在有效引用来源里");
  assert.match(invalid ?? "", /GONE-E7/, "失效引用要被提示");
  assert.match(document, /未发送给企业|不代表企业回复/);
});

test("复制：未保存编辑要求先保存；成功只写本机剪贴板一次；失败不自动重试", async () => {
  const h = setup({
    getDraft: async () => savedView({ text: "已保存正文", revision: 3, references: [savedReference()] }),
  });
  await h.session.load("task-1");
  const writes = [];
  const write = async text => { writes.push(text); };
  h.session.setText("未保存的新文字");
  assert.equal(await h.session.copy("预览文本", write), false);
  assert.equal(writes.length, 0, "有未保存编辑时不得复制");
  assert.match(h.state().notice, /先保存/);
  // 保存后复制成功
  await h.session.save("task-1");
  assert.ok(await h.session.copy("预览文本", write));
  assert.equal(writes.length, 1);
  assert.equal(writes[0], "预览文本");
  assert.match(h.state().notice, /剪贴板/);
  assert.match(h.state().notice, /没有发送给企业|未发送给企业/);
  assert.equal(h.calls.saveDraft.length, 1, "复制不得触发任何保存或发送请求");
  // 复制失败：只调用一次，错误可见，不自动重试
  let failures = 0;
  const failing = async () => { failures += 1; throw new Error("clipboard denied"); };
  assert.equal(await h.session.copy("预览文本", failing), false);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(failures, 1);
  assert.match(h.state().error, /复制失败/);
});

test("重复点击复制：上一次写入未完成时拒绝第二次", async () => {
  const h = setup();
  await h.session.load("task-1");
  await h.session.save("task-1");
  const gate = deferred();
  const writes = [];
  const write = async text => { writes.push(text); await gate.promise; };
  const first = h.session.copy("文档", write);
  assert.equal(await h.session.copy("文档", write), false);
  gate.resolve(null);
  assert.ok(await first);
  assert.equal(writes.length, 1);
});

test("422 来源不可用：保留编辑并提示，不进入冲突态", async () => {
  const unavailable = new ApiError("引用的报告当前不可用", 422, 4241, "req-422");
  const h = setup({ saveDraft: async () => { throw unavailable; } });
  await h.session.load("task-1");
  h.session.setText("要保留的编辑");
  assert.equal(await h.session.save("task-1"), false);
  const state = h.state();
  assert.equal(state.text, "要保留的编辑");
  assert.equal(state.conflict, false);
  assert.match(state.error, /引用的报告当前不可用/);
});

test("读取失败：错误可见且不清空已有本地输入", async () => {
  const h = setup({ getDraft: async () => { throw new Error("读取失败（合成）"); }, listReferences: async () => { throw new Error("读取失败（合成）"); } });
  await h.session.load("task-1");
  assert.equal(h.state().phase, "ready");
  assert.match(h.state().error, /读取失败/);
  h.session.setText("读取失败后输入的文字");
  assert.equal(await h.session.load("task-1"), false);
  assert.equal(h.state().text, "读取失败后输入的文字", "再次读取失败不得清掉本地输入");
});

test("本地限制：6000 字与 20 条引用在保存前被拦截", () => {
  assert.equal(PRIVATE_ANSWER_MAX_TEXT, 6000);
  assert.equal(PRIVATE_ANSWER_MAX_REFERENCES, 20);
  assert.equal(privateAnswerSaveProblem("x".repeat(6000), 0), "");
  assert.match(privateAnswerSaveProblem("x".repeat(6001), 0), /6000/);
  assert.equal(privateAnswerSaveProblem("x", 20), "");
  assert.match(privateAnswerSaveProblem("x", 21), /20/);
});

test("api client：三个调用的路径、方法与载荷完全匹配协议", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body) : undefined });
    const data = calls.at(-1).method === "PUT"
      ? savedView()
      : calls.length === 1 ? savedView() : [baseOption()];
    return new Response(JSON.stringify({ code: 0, message: "success", data, requestId: "r" }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    await api.getAnswerDraft("task-1");
    await api.saveAnswerDraft("task-1", { text: "正文", references: [{ reportId: BASE_REPORT, requirementId: REQUIREMENT, citationId: "R1-E1" }], expectedRevision: 3 });
    await api.listAnswerDraftReferences("task-1");
    assert.deepEqual(calls.map(call => [call.method, call.url]), [
      ["GET", "/backend/api/v1/growth-tasks/task-1/answer-draft"],
      ["PUT", "/backend/api/v1/growth-tasks/task-1/answer-draft"],
      ["GET", "/backend/api/v1/growth-tasks/task-1/answer-draft/references"],
    ]);
    assert.deepEqual(calls[1].body, {
      text: "正文",
      references: [{ reportId: BASE_REPORT, requirementId: REQUIREMENT, citationId: "R1-E1" }],
      expectedRevision: 3,
    }, "PUT 载荷不得携带额外字段（后端 extra=forbid）");
  } finally { globalThis.fetch = original; }
});

// ---- Codex固定快照20261006三项真实复现与交错回归（先红后修复；copy+save本就通过，作回归保持）----

test("复现1：clear后旧save/compare/copy不得发请求或复活会话，直到显式activate", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.clear();
  assert.equal(await h.session.save("task-1"), false, "clear后旧save不得发请求");
  assert.equal(h.calls.saveDraft.length, 0);
  assert.equal(await h.session.compareWithServer("task-1"), false, "clear后compare不得发请求");
  assert.equal(h.calls.getDraft.length, 1, "clear后compare不得触发GET");
  const writes = [];
  assert.equal(await h.session.copy("文档", async text => { writes.push(text); }), false, "clear后copy不得写剪贴板");
  assert.equal(writes.length, 0);
  h.session.setText("clear之后的输入");
  assert.equal(h.state().text, "", "clear后连输入也必须被拒绝");
  // 只有owner显式reactivate（当前身份/任务的effect）才恢复
  h.session.activate();
  assert.ok(await h.session.load("task-1"));
  assert.ok(await h.session.save("task-1"));
  assert.equal(h.calls.saveDraft.length, 1, "显式reactivate后保存恢复正常");
});

test("复现2：读取期间新输入保留，GET回执不覆盖请求发起后的编辑", async () => {
  const d = deferred();
  const h = setup({ getDraft: async () => d.promise });
  const reading = h.session.load("task-1");
  h.session.setText("读取期间输入的文字");
  d.resolve(savedView());
  assert.ok(await reading);
  const state = h.state();
  assert.equal(state.text, "读取期间输入的文字", "读取回执不得覆盖读取期间的新输入");
  assert.equal(state.saved.revision, 1, "读取回执仍更新已存基线");
  assert.equal(privateAnswerIsDirty(state), true, "基线与新输入不一致必须标记未保存");
});

test("复现3：reload不废弃在途save，回执照常落账且busy正常复位", async () => {
  const d = deferred();
  const h = setup({ saveDraft: async () => d.promise.then(() => savedView({ revision: 2 })) });
  await h.session.load("task-1");
  const saving = h.session.save("task-1");
  assert.ok(await h.session.load("task-1"), "保存进行中也允许重读");
  d.resolve(null);
  assert.ok(await saving, "在途save不得被reload废弃");
  const state = h.state();
  assert.equal(state.saving, false, "busy必须由回执正常复位，不得搁浅");
  assert.equal(state.saved.revision, 2);
  assert.equal(state.reading, false);
});

test("复现3b：save回执先于reload的GET到达时，旧GET不得降级基线或覆盖文字", async () => {
  const saveGate = deferred(), readGate = deferred();
  let draftReads = 0;
  const h = setup({
    saveDraft: async (id, payload) => saveGate.promise.then(() => savedView({ text: payload.text, revision: payload.expectedRevision + 1 })),
    getDraft: async () => {
      draftReads += 1;
      return draftReads === 1 ? savedView() : readGate.promise.then(() => savedView({ revision: 1, text: "旧的GET结果" }));
    },
  });
  await h.session.load("task-1");
  h.session.setText("本人的本地编辑");
  const saving = h.session.save("task-1");
  const reading = h.session.load("task-1");
  saveGate.resolve(null);
  assert.ok(await saving);
  readGate.resolve(null);
  assert.ok(await reading);
  const state = h.state();
  assert.equal(state.saved.revision, 2, "旧GET不得把基线降回revision 1");
  assert.equal(state.text, "本人的本地编辑", "旧GET不得覆盖本地编辑");
  assert.equal(state.reading, false);
  assert.equal(state.saving, false);
});

test("回归：copy与在途save交错互不废弃（Codex快照通过项保持）", async () => {
  const d = deferred();
  const h = setup({ saveDraft: async () => d.promise.then(() => savedView({ revision: 2 })) });
  await h.session.load("task-1");
  const saving = h.session.save("task-1");
  assert.ok(await h.session.copy("预览文本", async () => {}), "本地复制不得被保存忙态拒绝");
  d.resolve(null);
  assert.ok(await saving);
  assert.equal(h.state().saving, false);
  assert.equal(h.state().saved.revision, 2, "copy不得废弃在途save回执");
});

test("回归：clear后迟到的读取回执不得恢复状态或搁浅读取busy", async () => {
  const d = deferred();
  const h = setup({ getDraft: async () => d.promise });
  const reading = h.session.load("task-1");
  h.session.clear();
  d.resolve(savedView());
  assert.equal(await reading, false, "clear后的读取回执必须被丢弃");
  const state = h.state();
  assert.equal(state.text, "");
  assert.equal(state.saved, null);
  assert.equal(state.reading, false, "clear必须复位读取busy");
});

test("目标绑定变化：refreshReferences只刷新可选引用与scope提示，不重置未存编辑", async () => {
  const h = setup({ listReferences: async () => [baseOption()] });
  await h.session.load("task-1");
  h.session.setText("未保存的编辑");
  h.session.toggleReference(baseOption());
  assert.ok(await h.session.refreshReferences("task-1", { crossJob: true, hasTargetReport: true }));
  const state = h.state();
  assert.equal(state.text, "未保存的编辑", "绑定刷新不得重置文字");
  assert.equal(state.selected.length, 1, "绑定刷新不得重置引用选择");
  assert.equal(state.saved.revision, 1);
  assert.deepEqual(state.options.map(o => o.citationId), ["R1-E1"]);
  assert.match(state.optionsNotice, /跨岗位/, "scope提示按新绑定计算");
});

test("目标绑定变化与在途读取交错：最后发起的引用请求生效，读取回执不覆盖新options", async () => {
  const readGate = deferred(), refreshGate = deferred();
  const oldOptions = [baseOption()];
  const newOptions = [baseOption(), targetOption()];
  let reads = 0;
  const h = setup({
    listReferences: async () => {
      reads += 1;
      if (reads === 1) return oldOptions;
      if (reads === 2) return readGate.promise.then(() => oldOptions);
      return refreshGate.promise.then(() => newOptions);
    },
  });
  await h.session.load("task-1");
  const reading = h.session.load("task-1");
  const refreshing = h.session.refreshReferences("task-1", { crossJob: false, hasTargetReport: true });
  refreshGate.resolve(null);
  assert.ok(await refreshing);
  assert.deepEqual(h.state().options, newOptions, "刷新结果先生效");
  readGate.resolve(null);
  assert.ok(await reading);
  assert.deepEqual(h.state().options, newOptions, "更早发起的读取回执不得覆盖刷新后的options");
  assert.equal(h.state().text, "已保存的正文");
});

test("目标绑定刷新失败：错误可见且不清空已有options与编辑", async () => {
  let reads = 0;
  const h = setup({
    listReferences: async () => {
      reads += 1;
      if (reads > 1) throw new Error("引用读取失败（合成）");
      return [baseOption()];
    },
  });
  await h.session.load("task-1");
  h.session.setText("刷新失败前的编辑");
  assert.equal(await h.session.refreshReferences("task-1", { crossJob: false, hasTargetReport: false }), false);
  assert.match(h.state().error, /引用读取失败/);
  assert.equal(h.state().text, "刷新失败前的编辑");
  assert.deepEqual(h.state().options.map(o => o.citationId), ["R1-E1"], "失败不得清空已有options");
});

// ---- 来源重验边界（Codex binding快照20261006四项：先红后修复）----

test("来源重验成功：旧目标引用降级失效但保留身份，预览/复制不再含其原文", async () => {
  let options = [targetOption({ citationId: "OLD-E1" })];
  const h = setup({
    getDraft: async () => savedView({
      text: "已保存正文", revision: 2,
      references: [savedReference({ reportId: TARGET_REPORT, citationId: "OLD-E1", snippet: "STALE TARGET 原文", provenance: "reference" })],
    }),
    listReferences: async () => options,
  });
  await h.session.load("task-1");
  assert.equal(h.state().saved.references[0].available, true);
  options = [];
  assert.ok(await h.session.refreshReferences("task-1", { crossJob: false, hasTargetReport: false }));
  const state = h.state();
  assert.equal(state.sourceCheck, "current");
  assert.equal(state.saved.references.length, 1, "引用身份保留，不删除");
  assert.equal(state.saved.references[0].available, false, "绑定变化后来源不在可选列表 → 失效");
  assert.equal(state.saved.revision, 2, "版本不因重验变化");
  assert.equal(state.text, "已保存正文", "本地文字保留");
  assert.equal(state.selected.length, 1, "选中引用身份保留");
  const writes = [];
  assert.ok(await h.session.copy("预览文本", async t => { writes.push(t); }), "重验成功后允许确认复制");
  assert.equal(writes.length, 1);
  const document = buildPrivateAnswerPreviewDocument({
    saved: state.saved, requirementTitle: "原要求", jobTitle: "岗位",
    baseReportId: BASE_REPORT, targetReportId: TARGET_REPORT,
  });
  assert.ok(!document.includes("STALE TARGET 原文"), "失效引用原文不得作为有效来源复制");
  assert.match(document, /OLD-E1/, "失效引用要被提示");
});

test("来源重验 pending：旧预览确认被拒绝，不写剪贴板", async () => {
  const gate = deferred();
  let refreshing = false;
  const h = setup({
    getDraft: async () => savedView({ references: [savedReference({ reportId: TARGET_REPORT, citationId: "OLD-E1", snippet: "STALE TARGET 原文" })] }),
    listReferences: async () => (refreshing ? gate.promise : [targetOption({ citationId: "OLD-E1" })]),
  });
  await h.session.load("task-1");
  refreshing = true;
  const run = h.session.refreshReferences("task-1");
  assert.equal(h.state().sourceCheck, "pending");
  const writes = [];
  assert.equal(await h.session.copy("旧预览文本", async t => { writes.push(t); }), false, "重验中不得确认旧来源");
  assert.equal(writes.length, 0);
  gate.resolve([]);
  assert.ok(await run);
  assert.equal(h.state().sourceCheck, "current");
});

test("来源重验失败：复制被拒；保存回执或重验成功恢复确认资格", async () => {
  let fail = false;
  const h = setup({
    getDraft: async () => savedView({ references: [savedReference({ reportId: TARGET_REPORT, citationId: "OLD-E1", snippet: "STALE TARGET 原文" })] }),
    listReferences: async () => { if (fail) throw new Error("offline"); return [targetOption({ citationId: "OLD-E1" })]; },
  });
  await h.session.load("task-1");
  fail = true;
  assert.equal(await h.session.refreshReferences("task-1"), false);
  assert.equal(h.state().sourceCheck, "failed");
  const writes = [];
  assert.equal(await h.session.copy("旧预览文本", async t => { writes.push(t); }), false, "重验失败不得确认旧来源");
  assert.equal(writes.length, 0);
  assert.ok(await h.session.save("task-1"), "失败仍可明确保存，由服务端重新验证");
  assert.equal(h.state().sourceCheck, "current", "保存回执重新建立可信");
  assert.ok(await h.session.copy("预览文本", async t => { writes.push(t); }), "保存后复制恢复");
  fail = false;
  assert.ok(await h.session.refreshReferences("task-1"), "重验失败后可重试成功");
  assert.equal(h.state().sourceCheck, "current");
});

test("迟到保存回执：不降级已读取的新基线，saving正常结束，读取期间编辑保留", async () => {
  const gate = deferred();
  let readingNew = false;
  const h = setup({
    getDraft: async () => savedView(readingNew ? { revision: 3, text: "另一窗口的新版本" } : {}),
    saveDraft: async () => gate.promise.then(() => savedView({ revision: 2, text: "本窗口迟到回执" })),
  });
  await h.session.load("task-1");
  const saving = h.session.save("task-1");
  readingNew = true;
  const reading = h.session.load("task-1");
  h.session.setText("读取期间输入的文字");
  assert.ok(await reading, "保存进行中也允许重读到 revision 3");
  assert.equal(h.state().saved.revision, 3);
  gate.resolve(null);
  assert.ok(await saving, "迟到的回执照常结束保存");
  const state = h.state();
  assert.equal(state.saving, false, "busy正常复位");
  assert.equal(state.saved.revision, 3, "回执 revision 2 不得把基线从 3 降回 2");
  assert.equal(state.text, "读取期间输入的文字", "读取期间的编辑保留");
});

// ---- 来源代际（Codex source-ordering快照20261006三项：先红后修复）----
// 协议：来源新旧按发起顺序（sourceRun 代际），与草稿 revision 无关。GET/PUT 回执若发起于
// 更近一次来源重验之前，不得恢复该重验判失效的引用 available，也不得把 sourceCheck 改回
// current（pending/failed 门禁由较新重验决定）；revision、saving、编辑保护责任不受影响。

test("旧GET回执不得恢复较新重验判失效的引用", async () => {
  const readGate = deferred();
  let reads = 0, lists = 0;
  const h = setup({
    getDraft: async () => {
      reads += 1;
      return reads === 1 ? savedView({ references: [savedReference()] }) : readGate.promise.then(() => savedView({ references: [savedReference()] }));
    },
    listReferences: async () => { lists += 1; return lists >= 3 ? [] : [baseOption()]; },
  });
  await h.session.load("task-1");
  const reading = h.session.load("task-1");
  assert.ok(await h.session.refreshReferences("task-1"), "较新重验成功并把引用判失效");
  assert.equal(h.state().saved.references[0].available, false);
  readGate.resolve(null);
  assert.ok(await reading, "旧GET回执照常结束读取");
  const state = h.state();
  assert.equal(state.saved.references[0].available, false, "旧GET回执不得恢复被较新重验否决的引用");
  assert.equal(state.saved.revision, 1, "基线revision不受来源代际影响");
  assert.equal(state.reading, false, "读取busy正常复位");
});

test("旧PUT回执不得恢复较新重验判失效的引用；新revision与saving复位照常", async () => {
  const saveGate = deferred();
  let lists = 0;
  const h = setup({
    getDraft: async () => savedView({ references: [savedReference()] }),
    saveDraft: (id, payload) => saveGate.promise.then(() => savedView({ revision: payload.expectedRevision + 1, references: [savedReference()] })),
    listReferences: async () => { lists += 1; return lists >= 2 ? [] : [baseOption()]; },
  });
  await h.session.load("task-1");
  const saving = h.session.save("task-1");
  assert.ok(await h.session.refreshReferences("task-1"), "较新重验成功并把引用判失效");
  assert.equal(h.state().saved.references[0].available, false);
  saveGate.resolve(null);
  assert.ok(await saving, "旧PUT回执照常落账");
  const state = h.state();
  assert.equal(state.saved.revision, 2, "新revision照常前进");
  assert.equal(state.saved.references[0].available, false, "迟到PUT不得恢复被较新重验否决的引用");
  assert.equal(state.saving, false, "保存busy正常复位");
});

test("重验pending期间旧GET回执不得解除门禁放行旧预览复制", async () => {
  const readGate = deferred(), refreshGate = deferred();
  let reads = 0, lists = 0;
  const h = setup({
    getDraft: async () => {
      reads += 1;
      return reads === 1 ? savedView({ references: [savedReference()] }) : readGate.promise.then(() => savedView({ references: [savedReference()] }));
    },
    listReferences: async () => { lists += 1; return lists >= 3 ? refreshGate.promise.then(() => [baseOption()]) : [baseOption()]; },
  });
  await h.session.load("task-1");
  const reading = h.session.load("task-1");
  const refreshing = h.session.refreshReferences("task-1");
  readGate.resolve(null);
  assert.ok(await reading, "旧GET回执到达");
  assert.equal(h.state().sourceCheck, "pending", "旧GET回执不得把sourceCheck改回current");
  const writes = [];
  assert.equal(await h.session.copy("旧预览文本", async t => { writes.push(t); }), false, "较新重验pending期间不得确认复制");
  assert.equal(writes.length, 0);
  refreshGate.resolve(null);
  assert.ok(await refreshing);
  assert.equal(h.state().sourceCheck, "current", "重验完成后按其结果恢复");
});

test("较新重验failed后旧GET/PUT回执不得解除失败门禁", async () => {
  const saveGate = deferred();
  let lists = 0;
  const h = setup({
    getDraft: async () => savedView({ references: [savedReference()] }),
    saveDraft: (id, payload) => saveGate.promise.then(() => savedView({ revision: payload.expectedRevision + 1, references: [savedReference()] })),
    listReferences: async () => { lists += 1; if (lists >= 2) throw new Error("重验失败（合成）"); return [baseOption()]; },
  });
  await h.session.load("task-1");
  const saving = h.session.save("task-1");
  assert.equal(await h.session.refreshReferences("task-1"), false, "较新重验失败");
  assert.equal(h.state().sourceCheck, "failed");
  saveGate.resolve(null);
  assert.ok(await saving, "PUT回执照常落账");
  assert.equal(h.state().saved.revision, 2);
  assert.equal(h.state().saving, false);
  assert.equal(h.state().sourceCheck, "failed", "旧PUT回执不得解除较新重验的失败门禁");
  const writes = [];
  assert.equal(await h.session.copy("旧预览文本", async t => { writes.push(t); }), false);
  assert.equal(writes.length, 0);
  // 重验失败后由用户明确发起的读取/保存仍可重新建立可信（发起晚于失败）
  assert.ok(await h.session.save("task-1"));
  assert.equal(h.state().sourceCheck, "current", "失败后新发起的保存回执重新建立可信");
});

// ---- 组件面板（真实 .tsx，SSR + 直接 props 调用）----

test("面板：来源重验 pending/failed 状态可见且复制确认被禁用", () => {
  const saved = { text: "a", revision: 1, updatedAt: null, references: [] };
  const pendingHtml = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", sourceCheck: "pending", text: "a", saved }, previewOpen: true,
  })));
  assert.ok(pendingHtml.includes("正在重新验证引用来源"), pendingHtml);
  const failedProps = panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", sourceCheck: "failed", text: "a", saved }, previewOpen: true,
  });
  const failedHtml = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, failedProps));
  assert.match(failedHtml, /重验失败/, failedHtml);
  const element = draftComponent.PrivateAnswerDraftPanel(failedProps);
  const copyButton = buttons(element).find(b => String(b.props.children ?? "").includes("复制草稿"));
  assert.ok(copyButton, "预览仍可查看，复制按钮保留");
  assert.equal(copyButton.props.disabled, true, "重验失败时复制确认必须禁用");
});

function panelProps(over = {}) {
  return {
    state: { ...initialPrivateAnswerState, phase: "ready" },
    requirementTitle: "异常处理", jobTitle: "后端工程师",
    baseReportId: BASE_REPORT, targetReportId: null, crossJob: false,
    previewOpen: false,
    onPreviewToggle: () => {}, onText: () => {}, onToggle: () => {}, onRemove: () => {},
    onSave: () => {}, onReload: () => {}, onCompare: () => {}, onSaveOverServer: () => {}, onCopy: () => {},
    ...over,
  };
}

function findElements(node, predicate, found = []) {
  if (!node || typeof node !== "object") return found;
  if (predicate(node)) found.push(node);
  const children = node.props?.children;
  if (Array.isArray(children)) for (const child of children) findElements(child, predicate, found);
  else if (children) findElements(children, predicate, found);
  return found;
}

const textareas = node => findElements(node, n => n.type === "textarea");
const buttons = node => findElements(node, n => n.type === "button");

test("面板：正文可编辑不受保存忙态锁死，边界说明不含任何发送入口", () => {
  const props = panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", text: "正在编辑的草稿", saving: true, saved: { text: "旧", revision: 1, updatedAt: "2026-10-06T01:02:03+00:00", references: [] } },
  });
  const html = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, props));
  const openTag = /<textarea[^>]*>/.exec(html)?.[0] ?? "";
  assert.ok(openTag.includes('aria-label="私人回答草稿正文"'), html);
  assert.ok(/maxlength="6000"/i.test(openTag), html);
  assert.ok(!/\breadonly\b/i.test(openTag), "保存期间也要允许继续编辑");
  assert.ok(html.includes("正在编辑的草稿"));
  assert.ok(!/<button[^>]*>[^<]*发送/.test(html), "不得出现任何发送入口");
  assert.ok(html.includes("不发送给企业") || html.includes("未发送给企业"));
  assert.ok(html.includes("正在保存"));
});

test("面板：引用列表区分基准/目标与第三方参考，选中可切换", () => {
  let received = null;
  const option = targetOption({ provenance: "reference" });
  const props = panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", options: [baseOption(), option], selected: [{ ...baseOption(), reportKind: "base", available: true, snippet: null }] },
    onToggle: next => { received = next; },
  });
  const html = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, props));
  assert.ok(html.includes("基准报告"));
  assert.ok(html.includes("目标报告"));
  assert.ok(html.includes("第三方参考，不计入评级"));
  const element = draftComponent.PrivateAnswerDraftPanel(props);
  const checkboxes = findElements(element, n => n.type === "input" && n.props.type === "checkbox");
  assert.ok(checkboxes.length >= 2);
  checkboxes.at(-1).props.onChange({ target: {} });
  assert.deepEqual(received, option);
});

test("面板：409 冲突块提供读取对照与以本人编辑重存，且不自动覆盖", () => {
  const props = panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", text: "本人的编辑", conflict: true,
      saved: { text: "旧版本", revision: 1, updatedAt: null, references: [] },
      serverCopy: savedView({ text: "服务器上的新版本", revision: 5 }) },
  });
  const html = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, props));
  assert.ok(html.includes("新版本"));
  assert.ok(html.includes("读取服务器版本作对照"));
  assert.ok(html.includes("以本人编辑重新保存"));
  assert.ok(html.includes("服务器上的新版本"));
  assert.ok(html.includes("仅对照"));
  assert.ok(html.includes("本人的编辑"));
});

test("面板：预览先看后复制；未保存编辑时明确要求先保存且不出复制按钮", () => {
  const savedRefs = [savedReference()];
  const selected = [{ ...savedReference(), reportKind: "base", snippet: null }];
  const dirtyState = {
    ...initialPrivateAnswerState, phase: "ready", text: "本地新编辑", selected,
    saved: { text: "已保存正文", revision: 2, updatedAt: "2026-10-06T01:02:03+00:00", references: savedRefs },
  };
  const dirtyHtml = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, panelProps({ state: dirtyState, previewOpen: true })));
  assert.ok(dirtyHtml.includes("未保存"), "未保存编辑必须明确标识");
  assert.ok(!dirtyHtml.includes("复制草稿"), "有未保存编辑时不得提供复制按钮");

  const cleanState = { ...dirtyState, text: "已保存正文" };
  const cleanHtml = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, panelProps({ state: cleanState, previewOpen: true })));
  assert.ok(cleanHtml.includes("复制草稿"));
  assert.ok(cleanHtml.includes("保存回执里的真实片段"), "预览要展示服务端验证引用");
  let copied = null;
  const interactive = draftComponent.PrivateAnswerDraftPanel(panelProps({
    state: cleanState, previewOpen: true, onCopy: doc => { copied = doc; },
  }));
  const copyButton = buttons(interactive).find(b => String(b.props.children ?? "").includes("复制草稿"));
  assert.ok(copyButton, "必须有复制草稿按钮");
  copyButton.props.onClick({ preventDefault: () => {} });
  assert.match(copied, /已保存正文/);
  assert.match(copied, /保存回执里的真实片段/);
  assert.match(copied, /未发送给企业|不代表企业回复/);
});

test("面板：正文输入与失效引用移除走真实回调", () => {
  let text = null, removed = null;
  const unavailable = { reportId: BASE_REPORT, requirementId: REQUIREMENT, citationId: "GONE-E7", reportKind: "saved", available: false, filePath: null, lineStart: null, lineEnd: null, provenance: null, snippet: null };
  const props = panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", text: "a", selected: [unavailable],
      saved: { text: "a", revision: 1, updatedAt: null, references: [] } },
    onText: next => { text = next; }, onRemove: key => { removed = key; },
  });
  const element = draftComponent.PrivateAnswerDraftPanel(props);
  textareas(element)[0].props.onChange({ target: { value: "面板输入的新文字" } });
  assert.equal(text, "面板输入的新文字");
  const removeButton = buttons(element).find(b => String(b.props.children ?? "").includes("移除"));
  assert.ok(removeButton, "失效引用必须可以移除");
  removeButton.props.onClick({ preventDefault: () => {} });
  assert.equal(removed, privateAnswerReferenceKey(BASE_REPORT, REQUIREMENT, "GONE-E7"));
  const html = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, props));
  assert.ok(html.includes("已失效"), "失效引用要标明");
});
