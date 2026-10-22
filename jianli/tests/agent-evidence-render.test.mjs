// Real component SSR; this explicit mock fixture never proves a live model run.
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
const { default: Panel } = await import(pathToFileURL(path.join(SRC, "components/ReportAgentEvidence.tsx")).href);
const fixture = JSON.parse(readFileSync(path.join(here, "fixtures/agent-evidence-report.json"), "utf8"));
const render = (report = fixture, canGrow = true) => renderToStaticMarkup(React.createElement(Panel, { report, canGrow }));

test("component shows actual source and final use before technical logs", () => {
  const html = render();
  for (const text of ["这次分析做了什么", "Mock 界面验证", "project/order.py", "store.rollback()", "最终解释引用了", "没有保存初始AI判断", "对照其他已保存引用", "不能据此还原首轮实际发送"]) assert.ok(html.includes(text), text);
  assert.ok(!html.includes("补检索前的已有引用"));
  assert.ok(html.includes(`href="#growth-${fixture.items[0].requirementId}"`));
  assert.ok(html.indexOf("补充找到的证据") < html.indexOf("技术记录与范围"));
});
test("no-consent and program-budget notices remain visible with no tool rows", () => {
  const value = structuredClone(fixture); value.aiToolCalls = [];
  value.aiProcess = { skippedReason: "consent_not_granted" };
  assert.ok(render(value).includes("本次未调用模型"));
  assert.ok(render(value).includes('href="#evidence-workspace-title"'));
  value.aiProcess = { planningSkippedReason: "report_budget_reserved" };
  assert.ok(render(value).includes("不是模型主动选择停止"));
});
test("fallback shows rule explanation instead of a failed AI answer", () => {
  const value = structuredClone(fixture); value.aiFallbackUsed = true;
  value.items[0].aiExplanation = "FAILED-AI-ANSWER-MUST-NOT-SHOW";
  assert.ok(!render(value).includes("FAILED-AI-ANSWER-MUST-NOT-SHOW"));
  assert.ok(render(value).includes(value.items[0].explanation));
});
test("role without growth permission gets no growth action", () => {
  assert.ok(!render(fixture, false).includes('href="#growth-'));
});
test("stop/no-result/fallback records do not invent sources", () => {
  const value = structuredClone(fixture);
  value.aiToolCalls = [{ tool: "retrieve_more_evidence", status: "not_requested" }];
  assert.ok(render(value).includes("模型选择不再调用工具"));
  assert.ok(!render(value).includes("store.rollback()"));
  value.aiToolCalls = [{ tool: "retrieve_more_evidence", status: "no_result" }];
  assert.ok(render(value).includes("没有返回新证据"));
  value.aiFallbackUsed = true;
  assert.ok(render(value).includes("已保留规则结果"));
});
