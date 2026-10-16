// 传智杯56：岗位匹配表单“已有投递提示”渲染回归。用 sucrase 加载真实 JobDetailView.tsx
// 导出的无状态通知组件，react-dom/server 渲染断言可观察输出：active 复用共享状态文案并
// 链到 /applications#application-<id>；withdrawn 不得呈现为进行中、不恢复授权；
// error 显式且不阻断匹配；unknown 不做任何“未投递”断言。
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
    // JobDetailView 的材料选择器传递导入 demo/samples.json；Node ESM 需要 import attribute，
    // 这里短路成等价 JS 模块，保持组件源码不动。
    if (url.endsWith(".json")) {
      return { format: "module", source: `export default ${readFileSync(fileURLToPath(url), "utf8")}`, shortCircuit: true };
    }
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
const view = await import(pathToFileURL(path.join(SRC, "components/JobDetailView.tsx")).href);
const { JobApplicationStatusNotice } = view;
assert.ok(typeof JobApplicationStatusNotice === "function", "JobDetailView 必须导出无状态通知组件 JobApplicationStatusNotice");

function render(state, handlers = {}) {
  return renderToStaticMarkup(React.createElement(JobApplicationStatusNotice, { state, onRetry: handlers.onRetry ?? (() => {}), ...handlers }));
}

test("loading：显式读取中，不给结论、无链接", () => {
  const html = render({ kind: "loading" });
  assert.match(html, /role="status"/);
  assert.ok(html.includes("正在核对"), html);
  assert.ok(!html.includes("href="), html);
});

test("active(submitted)：复用共享文案“已投递”，链接定位到 /applications#application-<id>，并说明不会替换", () => {
  const html = render({ kind: "active", application: { id: "0b6ab13a-58c9-4a0e-9b8f-8d0c1d2e3f4a", status: "submitted", createdAt: "2026-10-12T08:00:00Z" } });
  assert.ok(html.includes("已投递"), html);
  assert.ok(html.includes('href="/applications#application-0b6ab13a-58c9-4a0e-9b8f-8d0c1d2e3f4a"'), html);
  assert.match(html, /不会替换/);
  assert.ok(!html.includes("<button"), "提示区不得出现撤回/重投等操作按钮");
  assert.ok(!html.includes("type=\"checkbox\""), "不得出现任何授权勾选，防止恢复同意");
});

test("active(viewed)：共享状态文案按状态映射，含下一步指引", () => {
  const html = render({ kind: "active", application: { id: "app-1", status: "viewed", createdAt: "2026-10-12T08:00:00Z" } });
  assert.ok(html.includes("企业已查看报告，尚未回复"), html);
  assert.match(html, /下一步/);
});

test("withdrawn：呈现为撤回史而非进行中投递，可看记录，不给重投/授权入口", () => {
  const html = render({ kind: "withdrawn", application: { id: "app-w", status: "withdrawn", createdAt: "2026-10-14T08:00:00Z" } });
  assert.ok(html.includes("已撤回授权"), html);
  assert.ok(!html.includes("当前没有进行中的"));
  assert.match(html, /这里只说明该条撤回记录/);
  assert.ok(html.includes('href="/applications#application-app-w"'), html);
  assert.ok(!html.includes("进行中的投递："), "不得把撤回史框成进行中的投递");
  assert.ok(!html.includes("<button"), "不得出现自动重投或撤回按钮");
  assert.ok(!html.includes("type=\"checkbox\""), "不得恢复任何同意默认值");
});

test("error：显式失败与重试，绝不写成未投递，也不阻断生成报告", () => {
  const html = render({ kind: "error", message: "服务暂不可用" });
  assert.match(html, /role="alert"/);
  assert.ok(html.includes("服务暂不可用"), html);
  assert.match(html, /重试/);
  assert.ok(!html.includes("未投递"), html);
  assert.ok(!html.includes("没有投递"), html);
  assert.match(html, /不影响生成报告/);
  assert.ok(!/<form[\s>]/.test(html), "状态读取失败不得吞掉或替代匹配表单");
});

test("error：重试按钮只走只读 onRetry 回调", () => {
  const retried = [];
  const node = JobApplicationStatusNotice({ state: { kind: "error", message: "x" }, onRetry: () => retried.push(1) });
  const buttons = [];
  (function walk(current) {
    if (!current || typeof current !== "object") return;
    if (current.type === "button") buttons.push(current);
    const children = current.props?.children;
    if (Array.isArray(children)) children.forEach(walk);
    else if (children) walk(children);
  })(node);
  const retry = buttons.find(button => String(button.props.children).includes("重试"));
  assert.ok(retry, "error 提示必须提供重试");
  retry.props.onClick();
  assert.deepEqual(retried, [1]);
});

test("unknown：无记录证明时不渲染任何结论（空输出，且绝不出现“未投递”）", () => {
  const html = render({ kind: "unknown" });
  assert.equal(html, "");
});
