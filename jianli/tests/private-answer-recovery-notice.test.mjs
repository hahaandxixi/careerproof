// 传智杯34：私人草稿清除提示与恢复闭环。
// 依据31号审查P1-1：hidden 清除后 clear() 发布的"未保存修改已丢弃"声明被恢复 load 的同步
// notice 清空，用户永远看不到，且面板事前无常驻警告。
// 本文件用真实 createPrivateAnswerSession 与真实面板组件（sucrase 转译 SSR）验证：
// - 实际发生未保存编辑丢弃时，非敏感固定提示在恢复读取中、成功、失败后都可见；
// - 没有未保存编辑时不得声称丢弃；清除提示只携带固定文案不携带旧数据；
// - 再次编辑/显式操作后提示生命周期明确；新会话不承接旧会话通知；
// - 旧回执与旧DOM不能复活；恢复后来源重验失败仍拒复制。
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
  privateAnswerReferenceKey, PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE, PRIVATE_ANSWER_CLEAR_CLEAN_NOTICE,
} = await import(pathToFileURL(path.join(SRC, "lib/private-answer-workflow.ts")).href);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const draftComponent = await import(pathToFileURL(path.join(SRC, "components/PrivateAnswerDraft.tsx")).href);

const BASE_REPORT = "11111111-1111-1111-1111-111111111111";
const REQUIREMENT = "99999999-9999-9999-9999-999999999999";

const baseOption = (over = {}) => ({
  reportId: BASE_REPORT, requirementId: REQUIREMENT, citationId: "R1-E1", reportKind: "base",
  filePath: "src/retry.ts", lineStart: 10, lineEnd: 20, provenance: "portfolio", ...over,
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
    listReferences: async () => [baseOption()],
    errorMessage: error => (error instanceof Error ? error.message : String(error)),
  };
  const merged = { ...defaults, ...overrides };
  const session = createPrivateAnswerSession({
    getDraft: async id => { calls.getDraft.push(id); return merged.getDraft(id); },
    saveDraft: async (id, payload) => { calls.saveDraft.push({ id, payload }); return merged.saveDraft(id, payload); },
    listReferences: async id => { calls.listReferences.push(id); return merged.listReferences(id); },
    errorMessage: merged.errorMessage,
  }, state => states.push(state));
  session.activate();
  return { session, state: () => states.at(-1) ?? initialPrivateAnswerState, calls };
}

// ---- 丢弃提示在恢复路径全程可见（P1-1 核心）----

test("丢弃提示：clear后恢复读取中与成功后都可见，不被同步notice清空", async () => {
  const gate = deferred();
  let reads = 0;
  const h = setup({
    getDraft: async () => { reads += 1; return reads === 1 ? savedView() : gate.promise.then(() => savedView()); },
    listReferences: async () => [],
  });
  await h.session.load("task-1");
  h.session.setText("未保存就要被丢弃的文字");
  h.session.clear();
  assert.match(h.state().notice, /未保存.*丢弃|丢弃.*未保存/, "清除时必须立即声明丢弃");
  h.session.activate();
  const reading = h.session.load("task-1");
  assert.equal(h.state().reading, true, "恢复进入读取态");
  assert.match(h.state().lossNotice, /未保存.*丢弃|丢弃.*未保存/, "读取中丢弃提示必须可见（不被同步notice清空）");
  gate.resolve(null);
  assert.ok(await reading);
  const state = h.state();
  assert.match(state.lossNotice, /未保存.*丢弃|丢弃.*未保存/, "成功恢复后丢弃提示仍可见");
  assert.ok(!/丢弃/.test(state.notice.replace(state.lossNotice, "")) || state.notice === "", "读取完成提示不吞并丢弃声明");
  assert.equal(state.text, "已保存的正文", "恢复读取以服务器内容为准（不复活本地丢弃文字）");
});

test("未保存的引用选择被清除后，恢复成功也可见丢弃提示", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.toggleReference(baseOption());
  assert.equal(privateAnswerIsDirty(h.state()), true, "引用选择也是未保存编辑");
  h.session.clear();
  h.session.activate();
  assert.ok(await h.session.load("task-1"));
  const state = h.state();
  assert.match(state.lossNotice, /丢弃/, "引用选择丢弃同样必须提示");
  assert.equal(state.selected.length, 0, "清除后引用选择不恢复");
  assert.equal(state.saved.references.length, 0);
});

test("恢复读取失败：错误可见且丢弃提示仍可见", async () => {
  let reads = 0;
  const h = setup({
    getDraft: async () => { reads += 1; if (reads > 1) throw new Error("读取失败（合成）"); return savedView(); },
    listReferences: async () => { if (reads > 1) throw new Error("读取失败（合成）"); return [baseOption()]; },
  });
  await h.session.load("task-1");
  h.session.setText("未保存的编辑");
  h.session.clear();
  h.session.activate();
  assert.equal(await h.session.load("task-1"), false);
  const state = h.state();
  assert.match(state.error, /读取失败/);
  assert.match(state.lossNotice, /丢弃/, "失败恢复后丢弃提示必须仍可见");
});

// ---- 布尔驱动：没有未保存编辑不声称丢弃 ----

test("没有未保存编辑时，清除提示不得声称丢弃了编辑", async () => {
  const h = setup();
  await h.session.load("task-1");
  assert.equal(privateAnswerIsDirty(h.state()), false);
  h.session.clear();
  const state = h.state();
  assert.equal(state.lossNotice, "", "无编辑时不得发布丢弃声明");
  assert.ok(!/丢弃/.test(state.notice), "无编辑时提示不得出现丢弃字样");
  h.session.activate();
  assert.ok(await h.session.load("task-1"));
  assert.equal(h.state().lossNotice, "");
});

// ---- 生命周期：再次编辑/显式操作结束提示 ----

test("提示生命周期：再次编辑后丢弃提示结束", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.setText("未保存的编辑");
  h.session.clear();
  h.session.activate();
  assert.ok(await h.session.load("task-1"));
  assert.match(h.state().lossNotice, /丢弃/);
  h.session.setText("重新开始编辑");
  assert.equal(h.state().lossNotice, "", "再次编辑后丢弃提示按生命周期结束");
});

test("提示生命周期：显式保存或复制后丢弃提示结束", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.setText("未保存的编辑");
  h.session.clear();
  h.session.activate();
  assert.ok(await h.session.load("task-1"));
  assert.match(h.state().lossNotice, /丢弃/);
  assert.ok(await h.session.save("task-1"));
  assert.equal(h.state().lossNotice, "", "显式保存后丢弃提示结束");

  h.session.setText("第二次未保存");
  h.session.clear();
  h.session.activate();
  assert.ok(await h.session.load("task-1"));
  assert.match(h.state().lossNotice, /丢弃/);
  const writes = [];
  assert.ok(await h.session.copy("预览文本", async t => { writes.push(t); }), "恢复且无编辑时允许复制");
  assert.equal(h.state().lossNotice, "", "显式复制后丢弃提示结束");
});

test("恢复读取期间的输入保护不变，编辑开始即结束丢弃提示", async () => {
  const gate = deferred();
  let reads = 0;
  const h = setup({
    getDraft: async () => { reads += 1; return reads === 1 ? savedView() : gate.promise.then(() => savedView()); },
    listReferences: async () => [],
  });
  await h.session.load("task-1");
  h.session.setText("丢弃的编辑");
  h.session.clear();
  h.session.activate();
  const reading = h.session.load("task-1");
  assert.match(h.state().lossNotice, /丢弃/);
  h.session.setText("恢复后重新输入的文字");
  assert.equal(h.state().lossNotice, "", "编辑开始后丢弃提示结束");
  gate.resolve(null);
  assert.ok(await reading);
  const state = h.state();
  assert.equal(state.text, "恢复后重新输入的文字", "读取期间的编辑保护行为不变");
  assert.equal(state.saved.revision, 1);
});

// ---- 固定文案与数据卫生 ----

test("清除提示是固定文案：不携带旧草稿文字等用户数据", async () => {
  const h = setup({ getDraft: async () => savedView({ text: "SECRET-DRAFT-CONTENT 标记正文", revision: 7 }) });
  await h.session.load("task-1");
  h.session.setText("用户SECRET-EDIT标记");
  h.session.clear();
  const state = h.state();
  assert.equal(typeof PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE, "string");
  assert.equal(state.notice, PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE, "丢弃文案必须是导出的固定常量");
  assert.equal(state.lossNotice, PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE);
  assert.ok(!state.notice.includes("SECRET-DRAFT-CONTENT"), "不得残留旧草稿正文");
  assert.ok(!state.notice.includes("SECRET-EDIT"), "不得残留未保存编辑文字");

  const h2 = setup();
  await h2.session.load("task-1");
  h2.session.clear();
  assert.equal(h2.state().notice, PRIVATE_ANSWER_CLEAR_CLEAN_NOTICE, "无编辑文案也是固定常量");
  assert.equal(h2.state().lossNotice, "");
});

test("新会话不承接旧会话通知；dispose后旧回执不复活", async () => {
  let send;
  const pending = new Promise(resolve => { send = resolve; });
  const first = setup({ saveDraft: () => pending.then(() => savedView({ revision: 2 })) });
  await first.session.load("task-1");
  first.session.setText("身份A的未保存编辑");
  const saving = first.session.save("task-1");
  first.session.clear();
  first.session.dispose();
  send(savedView({ revision: 2 }));
  await saving;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(first.state().text, "", "dispose后迟到回执不得写回文字");
  assert.match(first.state().lossNotice, /丢弃/, "清除时的丢弃提示保持");
  const second = setup();
  assert.equal(second.state().lossNotice, "", "新会话不得承接旧会话的丢弃通知");
  assert.equal(second.state().notice, "");
  await second.session.load("task-1");
  assert.equal(second.state().lossNotice, "");
  assert.equal(second.state().text, "已保存的正文");
});

// ---- 复活防护与门禁保留（回归锚点）----

test("clear时在途保存：迟到回执不复活任何状态，丢弃提示保持可见", async () => {
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
  assert.match(state.lossNotice, /丢弃/);
  assert.ok(!String(state.text).includes("迟到的保存结果"));
});

test("clear后旧DOM操作全部拒绝，恢复必须显式activate+load", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.clear();
  assert.equal(await h.session.save("task-1"), false, "clear后旧save不得发请求");
  assert.equal(h.calls.saveDraft.length, 0);
  const writes = [];
  assert.equal(await h.session.copy("文档", async t => { writes.push(t); }), false, "clear后copy不得写剪贴板");
  assert.equal(writes.length, 0);
  h.session.setText("clear后的输入");
  assert.equal(h.state().text, "", "clear后连输入也必须被拒绝");
  h.session.activate();
  assert.ok(await h.session.load("task-1"), "显式activate+load才恢复");
});

test("恢复后来源重验失败仍拒复制；门禁语义不变", async () => {
  let fail = false;
  const h = setup({
    getDraft: async () => savedView({ references: [savedReference()] }),
    listReferences: async () => { if (fail) throw new Error("引用读取失败（合成）"); return [baseOption()]; },
  });
  await h.session.load("task-1");
  h.session.setText("未保存的编辑");
  h.session.clear();
  h.session.activate();
  assert.ok(await h.session.load("task-1"), "恢复读取成功");
  fail = true;
  assert.equal(await h.session.refreshReferences("task-1"), false);
  assert.equal(h.state().sourceCheck, "failed");
  const writes = [];
  assert.equal(await h.session.copy("预览文本", async t => { writes.push(t); }), false, "来源重验失败仍拒复制");
  assert.equal(writes.length, 0);
  assert.equal(privateAnswerReferenceKey(BASE_REPORT, REQUIREMENT, "R1-E1"), JSON.stringify([BASE_REPORT, REQUIREMENT, "R1-E1"]));
});

// ---- 组件面板（真实 .tsx SSR）----

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

test("面板：普通切标签页保留编辑，刷新/切身份或任务前须保存，且不发送给企业", () => {
  const html = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, panelProps()));
  assert.match(html, /切换标签页[^<]*暂存/, "切标签页应保留当前任务编辑");
  assert.match(html, /刷新页面、退出账号或切换任务前请先/, "身份和任务边界仍需明确保存");
  assert.doesNotMatch(html, /离开或最小化窗口会清除未保存/, "不得继续宣称普通隐藏会丢弃");
  assert.match(html, /未保存/);
  assert.match(html, /先保存|保存草稿/);
  assert.match(html, /没有发送给企业|不会发送给企业|未发送给企业/);
});

test("面板：丢弃提示独立渲染且读取中可见；与notice相同内容不重复", () => {
  const readingHtml = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", reading: true, lossNotice: PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE },
  })));
  assert.match(readingHtml, /正在读取已保存草稿/);
  assert.match(readingHtml, /丢弃/, "读取中丢弃提示必须渲染");

  const withNotice = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", notice: "已保存版本 2 · 2026-10-06T01:02:03+00:00。", lossNotice: PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE },
  })));
  const fragments = withNotice.split("未保存的修改已丢弃").length - 1;
  assert.equal(fragments, 1, "丢弃声明恰好渲染一次");
  assert.match(withNotice, /已保存版本 2/, "普通notice与丢弃提示并存");

  const duplicated = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready", notice: PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE, lossNotice: PRIVATE_ANSWER_CLEAR_DISCARD_NOTICE },
  })));
  const duplicatedCount = duplicated.split("未保存的修改已丢弃").length - 1;
  assert.equal(duplicatedCount, 1, "notice与丢弃提示内容相同时不得重复渲染两遍");

  const cleanHtml = renderToStaticMarkup(React.createElement(draftComponent.PrivateAnswerDraftPanel, panelProps({
    state: { ...initialPrivateAnswerState, phase: "ready" },
  })));
  assert.ok(!/丢弃/.test(cleanHtml), "无丢弃事件时不得渲染丢弃提示");
});

// ---- 传智杯38：二次clear不得抹去仍然存活的丢弃提示 ----
// 以下保留显式身份/任务清理的提示和旧回执隔离边界；普通visibilitychange另由visibility测试覆盖。

test("恢复读取进行中再次清理身份/任务：第二次clear不得抹去丢弃提示", async () => {
  const gate = deferred();
  let reads = 0;
  const h = setup({
    getDraft: async () => { reads += 1; return reads <= 1 ? savedView() : gate.promise.then(() => savedView()); },
    listReferences: async () => [],
  });
  await h.session.load("task-1");
  h.session.setText("未保存就要被丢弃的文字");
  h.session.clear(); // 显式clear #1：丢弃提示发布
  assert.match(h.state().lossNotice, /丢弃/);
  h.session.activate(); // visible #1：恢复读取开始
  const reading = h.session.load("task-1");
  assert.equal(h.state().reading, true);
  h.session.clear(); // 显式clear #2：读取进行中再次隐藏（此时状态已干净）
  assert.match(h.state().lossNotice, /丢弃/, "第二次clear不得抹去已发布的丢弃提示");
  h.session.activate(); // visible #2：重新恢复
  gate.resolve(null);
  assert.equal(await reading, false, "被第二次clear作废的读取回执不得生效");
  assert.ok(await h.session.load("task-1"), "再次恢复读取成功");
  const state = h.state();
  assert.match(state.lossNotice, /丢弃/, "成功恢复后丢弃提示仍可见");
  assert.equal(state.text, "已保存的正文", "恢复读取以服务器内容为准");
});

test("恢复读取失败后再次清理身份/任务：丢弃提示仍保持", async () => {
  let reads = 0;
  const h = setup({
    getDraft: async () => { reads += 1; if (reads === 2) throw new Error("读取失败（合成）"); return savedView(); },
    listReferences: async () => { if (reads === 2) throw new Error("读取失败（合成）"); return []; },
  });
  await h.session.load("task-1");
  h.session.setText("未保存的编辑");
  h.session.clear();
  h.session.activate();
  assert.equal(await h.session.load("task-1"), false, "恢复读取失败");
  assert.match(h.state().error, /读取失败/);
  assert.match(h.state().lossNotice, /丢弃/);
  h.session.clear(); // 读取失败后再次隐藏
  assert.match(h.state().lossNotice, /丢弃/, "失败后再次clear不得抹去丢弃提示");
  h.session.activate();
  assert.ok(await h.session.load("task-1"), "再次恢复读取成功");
  assert.match(h.state().lossNotice, /丢弃/, "再次成功恢复后丢弃提示仍可见");
});

test("成功恢复后再次清理身份/任务（无新编辑）：丢弃提示保持，编辑仍按生命周期结束", async () => {
  const h = setup();
  await h.session.load("task-1");
  h.session.setText("未保存的编辑");
  h.session.clear();
  h.session.activate();
  assert.ok(await h.session.load("task-1"));
  assert.match(h.state().lossNotice, /丢弃/);
  h.session.clear(); // 无新编辑的再次清除
  assert.match(h.state().lossNotice, /丢弃/, "无新编辑的再次clear不得抹去丢弃提示");
  h.session.activate();
  assert.ok(await h.session.load("task-1"));
  assert.match(h.state().lossNotice, /丢弃/);
  h.session.setText("重新开始编辑");
  assert.equal(h.state().lossNotice, "", "编辑仍按生命周期结束提示（修复不得让提示永久化）");
});
