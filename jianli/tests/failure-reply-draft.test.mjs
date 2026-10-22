// E2E-02-R1 回归：回复失败（请求失败/响应丢失）后草稿必须真实可编辑。
// 测试环境没有浏览器 DOM 且禁止安装依赖：这里用 sucrase 同步转译加载真实 .tsx 组件代码，
// 再用 react-dom/server 渲染真实元素并直接调用真实 onChange 管线——不匹配源码字符串。
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

const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const board = await import(pathToFileURL(path.join(SRC, "components/ApplicationBoard.tsx")).href);
const { createApplicationBoardSession, initialApplicationBoardState } = await import(
  pathToFileURL(path.join(SRC, "lib/application-board-session.ts")).href);

function findTextareas(node, found = []) {
  if (!node || typeof node !== "object") return found;
  if (node.type === "textarea") found.push(node);
  const children = node.props?.children;
  if (Array.isArray(children)) for (const child of children) findTextareas(child, found);
  else if (children) findTextareas(children, found);
  return found;
}

test("回复失败后的草稿面板真实渲染为可编辑文本框：无 readOnly、限2000字、无发送按钮", () => {
  const html = renderToStaticMarkup(React.createElement(board.UnconfirmedReplyDraft, {
    text: "响应丢失前写好的核验问题草稿", onEdit: () => {},
  }));
  const openTag = /<textarea[^>]*>/.exec(html)?.[0] ?? "";
  assert.ok(openTag.includes('aria-label="未确认发送的回复草稿"'), html);
  // React 19 SSR 按驼峰原样输出 maxLength；HTML 属性名大小写不敏感，浏览器按 maxlength=2000 生效。
  assert.ok(/maxlength="2000"/i.test(openTag), html);
  assert.ok(!/\breadonly\b/i.test(openTag), `草稿不得只读：${openTag}`);
  assert.ok(html.includes("响应丢失前写好的核验问题草稿"), "草稿内容应保留以便复制");
  assert.ok(html.includes("请先刷新授权投递并核对该投递的回复状态"), "必须保留先核对状态的提示");
  assert.ok(html.includes("不会自动重发"), "必须明示不自动重发");
  assert.ok(!html.includes("<button"), `失败态不得出现任何发送入口：${html}`);
  assert.ok(!html.includes("已发送回复"), "失败态不得显示已送达");
});

test("在失败草稿文本框中输入会触发真实 onChange，把新文本交给页面状态", () => {
  let received = null;
  const element = board.UnconfirmedReplyDraft({ text: "原始草稿", onEdit: next => { received = next; } });
  const textarea = findTextareas(element)[0];
  assert.ok(textarea, "面板必须渲染出文本框元素");
  textarea.props.onChange({ target: { value: "企业编辑后的草稿" } });
  assert.equal(received, "企业编辑后的草稿");
});

test("编辑草稿的统一行为：更新正文并撤销人工发送确认（正常编辑与失败草稿共用）", () => {
  const edits = [], confirms = [];
  board.applyReplyDraftEdit("修改后的正文", text => edits.push(text), on => confirms.push(on));
  assert.deepEqual(edits, ["修改后的正文"]);
  assert.deepEqual(confirms, [false], "任何编辑都必须清除发送确认");
});

test("草稿被删空后未确认草稿面板仍渲染为可编辑文本框，可重新输入", () => {
  const html = renderToStaticMarkup(React.createElement(board.UnconfirmedReplyDraft, { text: "", onEdit: () => {} }));
  const openTag = /<textarea[^>]*>/.exec(html)?.[0] ?? "";
  assert.ok(openTag.includes('aria-label="未确认发送的回复草稿"'), html);
  assert.ok(!/\breadonly\b/i.test(openTag), `空草稿不得只读：${openTag}`);
  assert.ok(/maxlength="2000"/i.test(openTag), html);
  assert.ok(html.includes("请先刷新授权投递并核对该投递的回复状态"), "空草稿时仍须保留先核对状态的提示");
  let received = null;
  const element = board.UnconfirmedReplyDraft({ text: "", onEdit: next => { received = next; } });
  findTextareas(element)[0].props.onChange({ target: { value: "删空后重新输入的草稿" } });
  assert.equal(received, "删空后重新输入的草稿");
});

test("旧失败→清理→新草稿→旧回调迟到：代际不一致一律忽略，不得改变新状态", () => {
  let generation = 0;      // 组件内的清理代际（resetReply/报告不可用清理各递增一次）
  let unconfirmed = false; // 未确认草稿状态
  const cleanup = () => { generation += 1; unconfirmed = false; };
  // 旧发送在代际 0 发出；等待期间清理发生（随后可能已产生新草稿），旧回调最终以失败结束
  const oldGeneration = generation;
  cleanup();
  cleanup();
  const outcome = board.replySendOutcome(false, generation === oldGeneration);
  assert.equal(outcome, "ignore", "迟到的旧失败回调不得把新草稿标为未确认");
  assert.equal(unconfirmed, false);
  // 旧发送以成功结束同样不得清掉清理后产生的新草稿状态
  assert.equal(board.replySendOutcome(true, generation === oldGeneration), "ignore");
});

test("代际一致时发送结果才生效：失败标记未确认，成功重置草稿状态", () => {
  assert.equal(board.replySendOutcome(false, true), "mark-unconfirmed");
  assert.equal(board.replySendOutcome(true, true), "reset");
});

test("筛选空结果或已打开报告在筛选外时，提示原因、保留报告并给出清除入口", () => {
  let cleared = 0;
  const emptyHtml = renderToStaticMarkup(React.createElement(board.CandidateFilterNotice, {
    empty: true, selectedName: "合成候选人乙", onClear: () => { cleared += 1; },
  }));
  assert.match(emptyHtml, /本岗位没有符合关键词、状态、岗位要求和证据状态组合的候选人/);
  assert.doesNotMatch(emptyHtml, /只作用于当前页/);
  assert.match(emptyHtml, /合成候选人乙 不在筛选结果中/);
  assert.match(emptyHtml, /报告与未发送草稿仍保留/);
  const emptyButton = board.CandidateFilterNotice({
    empty: true, selectedName: "合成候选人乙", onClear: () => { cleared += 1; },
  });
  const buttons = [];
  const collect = node => {
    if (!node || typeof node !== "object") return;
    if (node.type === "button") buttons.push(node);
    [node.props?.children].flat(Infinity).forEach(collect);
  };
  collect(emptyButton);
  assert.equal(buttons.length, 1);
  buttons[0].props.onClick();
  assert.equal(cleared, 1);

  const outsideHtml = renderToStaticMarkup(React.createElement(board.CandidateFilterNotice, {
    empty: false, selectedName: "合成候选人乙", onClear: () => {},
  }));
  assert.match(outsideHtml, /当前打开的 合成候选人乙 不在本页筛选结果中/);
  assert.match(outsideHtml, /以下保留先前选中的固定报告与未发送草稿/);
  assert.match(outsideHtml, /回复仍指向 合成候选人乙 对应的投递/);
  assert.match(outsideHtml, /不会因筛选改变收件人/);
  assert.equal(renderToStaticMarkup(React.createElement(board.CandidateFilterNotice, {
    empty: false, onClear: () => {},
  })), "");
});

function setup(overrides = {}) {
  const snapshots = [];
  const session = createApplicationBoardSession({
    list: async () => [{ id: "a", status: "viewed" }],
    open: async () => ({ id: "a", status: "viewed", report: { summary: "合成授权报告" } }),
    download: async () => ({ blob: new Blob(["合成简历"]), filename: "CP08.txt" }),
    reply: async () => ({ id: "a", status: "replied" }),
    errorMessage: e => e.message,
    ...overrides,
  }, state => snapshots.push(state));
  session.activate();
  return { session, state: () => snapshots.at(-1) ?? initialApplicationBoardState };
}

for (const [variant, failure] of [
  ["请求失败", new Error("注入请求失败（合成错误）")],
  ["响应丢失（服务器已收到）", new Error("响应丢失（合成错误）")],
]) {
  test(`${variant}的回复失败：只发出一次请求、不自动重发、不留旧报告`, async () => {
    let replyCalls = 0, openCalls = 0;
    const h = setup({
      reply: async () => { replyCalls += 1; throw failure; },
      open: async () => { openCalls += 1; return { id: "a", status: "viewed", report: { summary: "合成授权报告" } }; },
    });
    await h.session.open("a");
    assert.equal(openCalls, 1);
    assert.equal(await h.session.reply("continue", `${variant}前写好的草稿`, []), false);
    // 留出事件循环：若存在自动重发或后台重试，会在此显现为第二次 reply 调用。
    await new Promise(resolve => setImmediate(resolve));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(replyCalls, 1, "失败后不得自动重发");
    assert.equal(h.state().selected, null, "失败后不得保留旧报告");
    assert.deepEqual(h.state().items, []);
    assert.match(h.state().error, /合成错误/);
  });
}
