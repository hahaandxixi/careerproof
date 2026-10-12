// 传智杯44：投递面板首屏必须直面分享风险，授权不预勾选，高级说明默认折叠但完整。
// 测试环境没有浏览器 DOM 且禁止安装依赖：沿用 failure-reply-draft 的做法，
// 用 sucrase 同步转译加载真实 .tsx 组件代码，再用 react-dom/server 渲染真实元素。
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
const submit = await import(pathToFileURL(path.join(SRC, "components/ApplicationSubmit.tsx")).href);

function render() {
  return renderToStaticMarkup(React.createElement(submit.default, { reportId: "r-1" }));
}

test("授权复选框不预勾选，未勾选时确认投递按钮必须禁用", () => {
  const html = render();
  const input = /<input[^>]*type="checkbox"[^>]*>/.exec(html)?.[0] ?? "";
  assert.ok(input, "必须渲染主动授权复选框");
  assert.ok(!/\bchecked\b/i.test(input), `授权不得预勾选：${input}`);
  const button = /<button[^>]*>/.exec(html)?.[0] ?? "";
  assert.ok(/disabled/i.test(button), `未勾选授权时确认投递必须禁用：${button}`);
});

test("首屏明示三项核心风险：固定报告/引用、简历下载可能含联系方式、撤回但已下载副本无法追回", () => {
  const html = render();
  assert.ok(html.includes("投递时固定的报告"), html);
  assert.ok(html.includes("代码引用片段"), html);
  assert.ok(html.includes("简历原文件"), html);
  assert.ok(html.includes("联系方式"), html);
  assert.ok(html.includes("撤回前已下载的副本无法追回"), html);
});

test("高级说明默认折叠且内容完整，不得隐藏其余分享风险", () => {
  const html = render();
  const details = /<details[^>]*>[\s\S]*?<\/details>/.exec(html)?.[0] ?? "";
  assert.ok(details, "高级说明必须用 details 承载");
  assert.ok(!/<details[^>]*\bopen[\s>]/i.test(details), "高级说明默认必须折叠");
  for (const text of ["其他报告", "不自动发送邮件", "新记录", "旧投递不会恢复或被覆盖"]) {
    assert.ok(details.includes(text), `折叠内容不得丢失：${text}`);
  }
});

test("保留确认投递入口、授权文案与查看我的投递链接及报告页锚点", () => {
  const html = render();
  assert.ok(html.includes("确认投递"), html);
  assert.ok(html.includes("同意向该岗位所属企业授权"), html);
  assert.ok(html.includes('href="/applications"'), html);
  assert.ok(html.includes("查看我的投递"), html);
  assert.ok(html.includes('id="application-submit"'), "报告页 application-submit 锚点必须保留，供我的投递重新授权跳转");
});
