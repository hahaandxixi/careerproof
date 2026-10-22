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
const { renderToStaticMarkup: render } = require("react-dom/server");
const { ReportHistoryCard } = await import("../src/components/ReportList.tsx");
const { SelectedRequirementEvidence, toggleComparisonCandidate, RequirementFocusSelect } = await import("../src/components/ApplicationBoard.tsx");

const summary = {
  id: "report-a", jobId: "job-a", jobTitle: "后端开发", candidateName: "甲",
  createdAt: "2026-10-22T10:00:00Z", summary: "已保存的规则分析",
};
test("history card displays server-wide history facts and fixed versions only when recorded", () => {
  const html = render(React.createElement(ReportHistoryCard, { report: {
    ...summary, isLatestForJob: false, jobReportCount: 27,
    materials: [
      { kind: "project", id: "version-a111111", title: "同名项目", versionNumber: 1 },
      { kind: "project", id: "version-b222222", title: "同名项目", versionNumber: 2 },
    ],
  }, onSameJob() {} }));
  assert.match(html, /该岗位有后续报告/);
  assert.match(html, /同岗位历史（27份）/);
  assert.match(html, /同名项目 · 第1版 · 材料编号 version-/);
  assert.match(html, /同名项目 · 第2版/);
  assert.match(html, /href="\/reports\/report-a"/);
  const unknown = render(React.createElement(ReportHistoryCard, { report: summary }));
  assert.doesNotMatch(unknown, /最新报告|后续报告|固定材料|历史（/);
});
test("comparison is bounded at four, removable and does not mutate the caller's selection", () => {
  const ids = ["a", "b", "c", "d"];
  assert.deepEqual(toggleComparisonCandidate(ids, "e"), ids);
  assert.deepEqual(toggleComparisonCandidate(ids, "b"), ["a", "c", "d"]);
  assert.deepEqual(ids, ["a", "b", "c", "d"]);
  assert.deepEqual(toggleComparisonCandidate(["a"], "b"), ["a", "b"]);
});
test("nearby cell evidence stays in the selected application's frozen requirement and materials", () => {
  const item = {
    requirementId: "r-a", requirementTitle: "容量限制", verdict: "supported",
    explanation: "容量不足时拒绝报名", aiExplanation: null, aiInformationGap: null,
    evidenceList: [{ citationId: "R1-E1", filePath: "version-a/service.py", projectVersionId: "version-a", lineStart: 12, lineEnd: 17, snippet: "raise CapacityError()", contentHash: "hash-a", evidenceType: "project_code" }],
  };
  const application = { id: "application-a", candidateName: "合成甲", report: {
    ...summary, materials: [{ id: "version-a", kind: "project", title: "报名项目", versionNumber: 3 }],
    items: [item, { ...item, requirementId: "r-b", requirementTitle: "不能串入的其他要求", evidenceList: [{...item.evidenceList[0], snippet:"DO_NOT_LEAK"}] }],
  } };
  const html = render(React.createElement(SelectedRequirementEvidence, { application, requirementId: "r-a" }));
  assert.match(html, /合成甲 · 容量限制/);
  assert.match(html, /报名项目/);
  assert.match(html, /第12–17行/);
  assert.match(html, /raise CapacityError/);
  assert.doesNotMatch(html, /DO_NOT_LEAK|不能串入的其他要求/);
  assert.match(html, /href="#selected-application-report"/);
  const missing = render(React.createElement(SelectedRequirementEvidence, { application, requirementId: "other-version-r" }));
  assert.match(missing, /不同报告的要求版本可能不同/);
  assert.doesNotMatch(missing, /raise CapacityError/);
});


test("zero matches retain the selected requirement label and exact filter value", () => {
  const html = render(React.createElement(RequirementFocusSelect, {
    dimensions: [], value: "req-capacity", selectedLabel: "容量不足处理", onChange() {},
  }));
  assert.match(html, /<option value="req-capacity" selected="">容量不足处理<\/option>/);
  assert.doesNotMatch(html, /<option value="" selected=/);
  const other = render(React.createElement(RequirementFocusSelect, {
    dimensions: [{requirementId: "req-other", title: "另一要求", skill: "SQL"}],
    value: "req-capacity", selectedLabel: "容量不足处理", onChange() {},
  }));
  assert.match(other, /value="req-capacity" selected=""/);
  assert.match(other, /value="req-other"/);
  const unknown = render(React.createElement(RequirementFocusSelect, {
    dimensions: [], value: "legacy-requirement", selectedLabel: "", onChange() {},
  }));
  assert.match(unknown, /已选要求（当前结果未包含）/);
  const reset = render(React.createElement(RequirementFocusSelect, {
    dimensions: [], value: "", selectedLabel: "旧标签", onChange() {},
  }));
  assert.match(reset, /<option value="" selected="">全部要求<\/option>/);
  assert.doesNotMatch(reset, /旧标签/);
});
