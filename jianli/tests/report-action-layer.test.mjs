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

const { default: Workspace, ReportActionLayer } = await import(pathToFileURL(path.join(SRC, "components/ReportEvidenceWorkspace.tsx")).href);
const item = (id, verdict = "gap", extra = {}) => ({ requirementId: id, requirementTitle: `要求${id}`, skill: id, weight: 3, verdict, confirmationStatus: "pending", evidenceLevelGap: `缺口${id}`, explanation: `解释${id}`, evidenceList: [], ...extra });
const advice = (value, extra = {}) => ({ requirementId: value.requirementId, requirementTitle: value.requirementTitle, skill: value.skill, weight: value.weight, currentLevel: null, source: "rules", action: value.evidenceLevelGap, evidenceGap: value.evidenceLevelGap, citationIds: [], ...extra });
const report = (items, actionPlan = []) => ({ id: "report-test", items, actionPlan });
const render = value => renderToStaticMarkup(React.createElement(Workspace, { report: value }));
const count = (html, text) => html.split(text).length - 1;

test("six material gaps render six items even when the saved action plan contains only three", () => {
 const items = Array.from({ length: 6 }, (_, i) => item(String(i)));
 const html = render(report(items, items.slice(0, 3).map(value => advice(value))));
 for (const value of items) assert.ok(html.includes(`href="#requirement-${value.requirementId}"`));
 assert.equal(count(html, 'href="#growth-'), 6);
 assert.equal(count(html, "下一步补证计划"), 1);
 assert.ok(html.includes('id="evidence-group-gaps" aria-expanded="true"'));
 assert.ok(html.includes('id="evidence-group-supported" aria-expanded="false"'));
 assert.ok(!html.includes("优先补齐的证据"));
});

test("an absent action plan never empties the group or invents advice and attribution", () => {
 const html = render(report([item("without-advice")]));
 assert.ok(html.includes("缺口without-advice"));
 assert.ok(html.includes('href="#requirement-without-advice"'));
 assert.ok(!html.includes("建议行动："));
 assert.ok(!html.includes("本地规则提示"));
});

test("identical rules advice appears once while its saved source remains visible", () => {
 const value = item("repeat", "gap", { evidenceLevelGap: "补充参数校验源码及失败用例" });
 const html = render(report([value], [advice(value)]));
 assert.equal(count(html, value.evidenceLevelGap), 1);
 assert.ok(html.includes("本地规则提示"));
 assert.ok(!html.includes("对应缺口："));
});

test("distinct AI advice and gap survive, with only same-requirement saved citations", () => {
 const value = item("ai", "claimed_only", { evidenceList: [{ citationId: "R1-E1" }] });
 const html = render(report([value], [advice(value, { source: "ai_suggestion", action: "保存可复现的参数校验记录", evidenceGap: "缺少运行结果", citationIds: ["R1-E1", "R1-E1", "R2-E9"] })]));
 assert.ok(html.includes("AI 证据建议"));
 assert.ok(html.includes("保存可复现的参数校验记录"));
 assert.ok(html.includes("缺少运行结果"));
 assert.equal(count(html, 'href="#citation-R1-E1"'), 1);
 assert.ok(!html.includes("R2-E9"));
});

test("admin retains its action plan without receiving student controls or duplicate rules text", () => {
 const value = item("admin", "gap", { evidenceLevelGap: "补充数据库索引说明" });
 const html = renderToStaticMarkup(React.createElement(ReportActionLayer, { report: report([value], [advice(value)]), role: "admin" }));
 assert.ok(html.includes("下一步补证计划"));
 assert.ok(html.includes("本地规则提示"));
 assert.equal(count(html, value.evidenceLevelGap), 1);
 assert.ok(!html.includes('id="evidence-group-gaps"'));
 assert.ok(!html.includes('href="#growth-'));
});

test("student receives one merged plan and no standalone duplicate", () => {
 const value = item("student");
 const html = renderToStaticMarkup(React.createElement(ReportActionLayer, { report: report([value], [advice(value)]), role: "student" }));
 assert.equal(count(html, "下一步补证计划"), 1);
 assert.ok(html.includes('id="evidence-group-gaps"'));
});

test("review items open when gaps and partial support are absent", () => {
 const html = render(report([item("ok", "supported"), item("review", "supported", { confirmationStatus: "rejected" })]));
 assert.ok(html.includes('id="evidence-group-other" aria-expanded="true"'));
 assert.ok(html.includes('href="#requirement-review"'));
 assert.equal(count(html, 'aria-controls="evidence-panel-'), 4);
 assert.ok(html.includes('id="evidence-group-supported" aria-expanded="false"'));
 assert.ok(!html.includes('href="#growth-'));
 assert.ok(!html.includes('<details open'));
});

test("partial support opens its complete saved list instead of an empty gap panel", () => {
 const items = [item("sql", "partial"), item("redis", "partial"), item("ok", "supported")];
 const html = render(report(items, [advice(items[0])]));
 assert.ok(html.includes('id="evidence-group-partial" aria-expanded="true"'));
 assert.equal(count(html, 'href="#growth-'), 2);
 assert.ok(html.includes('href="#requirement-sql"'));
 assert.ok(html.includes('href="#requirement-redis"'));
 assert.ok(!html.includes("当前没有标记为“待补材料”的要求"));
 assert.equal(count(html, "本地规则提示"), 1);
});

test("fully supported and empty reports do not invent gaps or advice", () => {
 const html = render(report([item("complete", "supported")]));
 assert.ok(html.includes('id="evidence-group-supported" aria-expanded="true"'));
 assert.ok(html.includes('href="#requirement-complete"'));
 assert.ok(!html.includes('href="#growth-'));
 const empty = render(report([]));
 assert.ok(empty.includes("当前没有标记为“待补材料”的要求"));
 assert.ok(!empty.includes('href="#requirement-'));
});

test("unmatched actions never create requirements, suggestions or citations", () => {
 const unrelated = item("other-report");
 const html = render(report([item("current")], [advice(unrelated, { action: "不可出现在当前清单中的建议" })]));
 assert.ok(!html.includes("不可出现在当前清单中的建议"));
 assert.ok(!html.includes('href="#requirement-other-report"'));
 assert.ok(html.includes('href="#requirement-current"'));
});

test("fixed material versions and next action are visible without a second source of truth", () => {
 const html = render({
  ...report([item("ok", "supported")]),
  materials: [
   { kind: "resume", id: "r", title: "简历", versionNumber: 1, contentHash: "r" },
   { kind: "project", id: "p", title: "库存服务", versionNumber: 2, contentHash: "p" },
   { kind: "project", id: "q", title: "分析服务", versionNumber: 1, contentHash: "q" },
  ],
 });
 assert.ok(html.includes("简历（简历 v1） · 库存服务（项目 v2） · 分析服务（项目 v1）"));
 assert.ok(html.includes("补证或上传新版不会替换本报告。"));
 assert.ok(html.includes("下一步：核对关键引用后，可直接投递本报告"));
 assert.ok(!html.includes("先处理 0 项"));
});

test("review-only items offer review without imposing a new delivery prerequisite", () => {
 const html = render(report([item("review", "supported", { confirmationStatus: "rejected" })]));
 assert.ok(html.includes("下一步：可核对 1 项待补、部分支持或需复核的要求"));
 assert.ok(html.includes("也可直接投递当前报告"));
 assert.ok(!html.includes("完成后生成新报告再决定是否投递"));
 assert.ok(!html.includes("下一步：核对关键引用后，可直接投递本报告"));
});

test("empty items do not masquerade as full support", () => {
 const html = render(report([]));
 assert.ok(html.includes("暂无逐项结果，请先核对报告状态"));
 assert.ok(!html.includes("下一步：核对关键引用后，可直接投递本报告"));
});
