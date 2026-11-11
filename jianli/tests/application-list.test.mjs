// 传智杯44：我的投递卡片回归。突出岗位/公司/状态/回复/下一动作，事件默认折叠，
// 撤回二次确认与重新投递入口可用，查看/下载不得推断录用。
// 沿用 sucrase 转译加载真实 .tsx 的做法；卡片是无状态组件，可直接调用于交互验证。
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
const list = await import(pathToFileURL(path.join(SRC, "components/ApplicationList.tsx")).href);
const { ApplicationItemCard } = list;

function fixture(overrides = {}) {
  return {
    id: "app-1", jobId: "j1", jobTitle: "前端工程师", companyName: "示例公司", candidateName: "张三",
    reportId: "r-9", status: "viewed", createdAt: "2026-10-12T08:00:00Z", overallScore: 65,
    consentVersion: "v1", replyKind: null, replyText: null,
    replyReferences: [],
    events: [
      { type: "submitted", at: "2026-10-12T08:00:00Z", detail: "已确认授权投递" },
      { type: "viewed", at: "2026-10-12T09:00:00Z", detail: "企业已查看报告" },
    ],
    dimensions: [{ requirementId: "q1", title: "React 基础", skill: "前端", score: 65, verdict: "supported", weight: 3, evidenceLevel: 2, evidenceLevelSource: "test", evidenceLevelVersion: "v1", formulaVersion: "evidence-v3" }],
    comparisonBasis: "固定报告",
    ...overrides,
  };
}
const noop = { onRequestWithdraw() {}, onConfirmWithdraw() {}, onCancelWithdraw() {} };
function element(item, extra = {}) { return ApplicationItemCard({ item, confirming: false, busy: false, ...noop, ...extra }); }
function renderCard(item, extra = {}) { return renderToStaticMarkup(React.createElement(ApplicationItemCard, { item, confirming: false, busy: false, ...noop, ...extra })); }
function findButtons(node, found = []) {
  if (!node || typeof node !== "object") return found;
  if (node.type === "button") found.push(node);
  const children = node.props?.children;
  if (Array.isArray(children)) for (const child of children) findButtons(child, found);
  else if (children) findButtons(children, found);
  return found;
}
function buttonText(node) {
  const children = node.props?.children;
  return Array.isArray(children) ? children.join("") : String(children ?? "");
}

test("卡片突出岗位/公司/状态/下一动作，锚点 id 保留", () => {
  const html = renderCard(fixture());
  assert.ok(html.includes("前端工程师"), html);
  assert.ok(html.includes("示例公司"), html);
  assert.ok(html.includes("企业已查看"), html);
  assert.ok(html.includes("等待企业回复即可。"), html);
  assert.ok(html.includes('id="application-app-1"'), html);
});

test("完整投递记录默认折叠，摘要给条数，内容仍可展开", () => {
  const html = renderCard(fixture());
  const details = /<details[^>]*>[\s\S]*?<\/details>/.exec(html)?.[0] ?? "";
  assert.ok(details, "投递记录必须用 details 承载");
  assert.ok(!/<details[^>]*\bopen[\s>]/i.test(details), "投递记录默认必须折叠");
  assert.ok(details.includes("投递记录（2 条）"), details);
  assert.ok(details.includes("企业已查看报告"), "展开后应能看到完整事件");
});

test("查看与下载状态的卡片不推断录用", () => {
  for (const status of ["viewed", "downloaded"]) {
    const html = renderCard(fixture({ status }));
    assert.doesNotMatch(html, /不代表通过筛选|录用概率|已录用|有望通过/);
    assert.doesNotMatch(html, /录用概率|已录用|有望通过/);
  }
});

test("企业回复与原报告/问题/引用链接保留", () => {
  const item = fixture({
    status: "replied", replyKind: "interview", replyText: "周四下午来聊聊",
    replyReferences: [{ requirementId: "q1", citationIds: ["c1", "c2"] }],
  });
  const html = renderCard(item);
  assert.ok(html.includes("面试邀请"), html);
  assert.ok(html.includes("周四下午来聊聊"), html);
  assert.ok(!html.includes("阅读企业回复并按其内容跟进"), "已有回复不重复展示阅读指令");
  assert.ok(html.includes("查看关联报告"), html);
  assert.ok(html.includes('href="/reports/r-9"'), html);
  assert.ok(html.includes('href="/reports/r-9#requirement-q1"'), html);
  assert.ok(html.includes("第1项："), html);
  assert.ok(html.includes("React 基础"), html);
  assert.ok(html.includes(`href="/reports/r-9?enterpriseReply=q1#requirement-q1"`), "补证入口必须保留");
  assert.ok(html.includes('href="/reports/r-9#citation-c1"'), html);
  assert.ok(html.includes('href="/reports/r-9#citation-c2"'), html);
});

test("已撤回状态展示重新投递入口并定位到报告页授权锚点，且不再出现撤回按钮", () => {
  const html = renderCard(fixture({ status: "withdrawn" }));
  assert.ok(html.includes("重新确认授权并投递"), html);
  assert.ok(html.includes('href="/reports/r-9#application-submit"'), html);
  assert.ok(!html.includes(">撤回授权</button>"), "已撤回后不得再提供撤回入口");
});

test("未撤回状态先请求确认：点击撤回只进入二次确认，不直接撤回", () => {
  const requests = [];
  const node = element(fixture(), { onRequestWithdraw: id => requests.push(id) });
  const buttons = findButtons(node);
  const request = buttons.find(b => buttonText(b).includes("撤回授权"));
  assert.ok(request, "必须提供撤回入口");
  request.props.onClick();
  assert.deepEqual(requests, ["app-1"], "第一次点击只能发起二次确认");
  const html = renderCard(fixture(), { confirming: true });
  assert.ok(html.includes("确认撤回授权"), html);
  assert.ok(html.includes("已下载副本无法追回"), html);
});

test("二次确认面板：确认/取消各走各的回调，忙碌时确认禁用", () => {
  const confirmed = [], cancelled = [];
  const node = element(fixture(), { confirming: true, onConfirmWithdraw: id => confirmed.push(id), onCancelWithdraw: () => cancelled.push(1) });
  const buttons = findButtons(node);
  const confirm = buttons.find(b => buttonText(b).includes("确认撤回授权"));
  const cancel = buttons.find(b => buttonText(b).includes("取消"));
  assert.ok(confirm && cancel, "二次确认必须同时提供确认与取消");
  confirm.props.onClick();
  cancel.props.onClick();
  assert.deepEqual(confirmed, ["app-1"]);
  assert.deepEqual(cancelled, [1]);
  const busyNode = element(fixture(), { confirming: true, busy: true });
  const busyConfirm = findButtons(busyNode).find(b => buttonText(b).includes("确认撤回授权"));
  assert.equal(busyConfirm.props.disabled, true, "撤回请求进行中必须禁用确认按钮");
});


test("reply presentation uses the actual replied event and preserves legacy missing metadata",()=>{
 const html=renderCard(fixture({status:"replied",replyKind:"continue",replyText:"原始回复",events:[{type:"submitted",at:"2020-01-01T00:00:00Z"},{type:"replied",at:"2026-10-31T01:02:03Z"}]}));
 assert.match(html,/继续沟通/);assert.match(html,/原始回复/);assert.match(html,/<time[^>]*dateTime="2026-10-31T01:02:03Z"/i);assert.doesNotMatch(html,/dateTime="2020/);
 const legacy=renderCard(fixture({status:"replied",replyText:"旧回复原文",replyKind:null,events:[]}));assert.match(legacy,/回复类型未记录/);assert.match(legacy,/回复时间未记录/);assert.match(legacy,/旧回复原文/);assert.doesNotMatch(legacy,/<time/);
});


test("enterprise sent reply uses the same metadata and does not substitute application creation time",async()=>{
 const {default:Reply}=await import("../src/components/ApplicationReply.tsx");
 const item=fixture({status:"replied",replyKind:"interview",replyText:"原始企业回复",events:[{type:"replied",at:"2026-10-31T08:00:00Z"},{type:"replied",at:"invalid"}]});
 const before=JSON.stringify(item);const html=renderToStaticMarkup(React.createElement(Reply,{application:item,sent:true}));
 assert.match(html,/已发送 · /);assert.match(html,/面试邀请/);assert.match(html,/dateTime="2026-10-31T08:00:00Z"/i);assert.match(html,/原始企业回复/);assert.doesNotMatch(html,/2026-10-12/);assert.equal(JSON.stringify(item),before);
});
