// 传智杯48 渲染回归：证据等级优先名称、去除“实践证据 x/5”与“/ 100”误导、
// 65 规则上限说明、岗位权重仍保留 /5、未评级与未知历史等级仍可显示。
// 真实 .tsx 组件经 sucrase 同步转译后由 react-dom/server 渲染，断言可观察输出，不以源码正则代替。
// 分数取值对齐 evidence-v3 单项材料支持度可达值 0/10/15/30/40/65；历史/异常兼容用例单独注明。
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
const { default: SkillRadar } = await import(pathToFileURL(path.join(SRC, "components/SkillRadar.tsx")).href);
const { default: ActionPlan } = await import(pathToFileURL(path.join(SRC, "components/ActionPlan.tsx")).href);
const { default: GrowthComparison } = await import(pathToFileURL(path.join(SRC, "components/GrowthComparison.tsx")).href);

const dim = (id, verdict, score, extra = {}) => ({ requirementId: id, title: id, skill: id, verdict, score, weight: 3, evidenceLevel: null, ...extra });

test("SkillRadar 证据等级显示名称并说明规则上限，不再呈现 /5 与 / 100", () => {
  const dimensions = [dim("Python", "supported", 65, { evidenceLevel: 3 }), dim("SQL", "partial", 40, { evidenceLevel: 2 }), dim("pytest", "gap", 0)];
  const html = renderToStaticMarkup(React.createElement(SkillRadar, { dimensions, items: [], initialRequirementId: "Python" }));
  assert.ok(html.includes("实践证据 任务实现"));
  assert.ok(html.includes("当前规则上限 65"));
  assert.ok(html.includes("材料支持度"));
  assert.ok(!html.includes("/ 100"));
  assert.ok(!html.includes("/5"));
  // 雷达 SVG 环刻度是坐标尺度，本次文案整改不得改动
  assert.ok(html.includes(">100<"));
});

test("SkillRadar 历史未知等级 4 仍显示原数字，不消失也不造比例", () => {
  // 兼容用例：等级 4 非当前自动判定范围，仅验证历史数据仍可显示
  const dimensions = [dim("Python", "supported", 65, { evidenceLevel: 4 }), dim("SQL", "partial", 40), dim("pytest", "gap", 0)];
  const html = renderToStaticMarkup(React.createElement(SkillRadar, { dimensions, items: [], initialRequirementId: "Python" }));
  assert.ok(html.includes("等级 4"));
  assert.ok(!html.includes("/5"));
});

test("ActionPlan 岗位权重仍为 /5，当前证据显示等级名称或未评级", () => {
  const actions = [
    { requirementId: "r1", requirementTitle: "数据库设计", skill: "SQL", weight: 4, currentLevel: 1, source: "rules", evidenceGap: "缺少建表语句", action: "补充 ER 图与建表脚本", citationIds: [] },
    { requirementId: "r2", requirementTitle: "缓存实践", skill: "Redis", weight: 2, currentLevel: null, source: "ai_suggestion", evidenceGap: "无材料", action: "提交缓存实践作品", citationIds: [] },
  ];
  const html = renderToStaticMarkup(React.createElement(ActionPlan, { actions }));
  assert.ok(html.includes("岗位权重 4/5"));
  assert.ok(html.includes("岗位权重 2/5"));
  assert.ok(html.includes("当前证据基础线索"));
  assert.ok(html.includes("当前证据未评级"));
  assert.ok(!html.includes("当前证据1/5"));
  assert.ok(!html.includes("当前证据2/5"));
});

test("GrowthComparison 基准未评级与目标等级名称、历史等级 80 仍可显示", () => {
  const task = {
    id: "t1", baseReportId: "b1", jobId: "j1", jobTitle: "后端岗位",
    requirementId: "r1", requirementTitle: "SQL 设计", gap: "缺少 SQL 实践", originalAction: "补充 SQL 作品",
    plan: { requirementId: "r1", gapKind: "implementation", deliverable: "d", steps: [], acceptanceChecks: [] },
    baseMaterials: [], materials: [], status: "compared",
    analysisTaskId: null, analysisStatus: null, analysisError: null,
    targetReportId: "t2",
    comparison: {
      baseId: "b1", targetId: "t2", contextChanges: [], baseMaterials: [], targetMaterials: [], limitations: [],
      items: [
        { requirementId: "r1", title: "SQL 设计", status: "existing", baseRequirement: null, targetRequirement: null,
          baseLevel: null, targetLevel: 3, baseAiStatus: null, targetAiStatus: null, baseReview: null, targetReview: null,
          addedEvidence: [], removedEvidence: [], changes: [] },
        // 兼容用例：80 为历史/异常等级，仅验证原数字保留显示，不当正常值
        { requirementId: "r2", title: "缓存", status: "existing", baseRequirement: null, targetRequirement: null,
          baseLevel: 80, targetLevel: null, baseAiStatus: null, targetAiStatus: null, baseReview: null, targetReview: null,
          addedEvidence: [], removedEvidence: [], changes: [] },
      ],
    },
    createdAt: "2026-10-13T00:00:00.000Z", boundary: "",
  };
  const html = renderToStaticMarkup(React.createElement(GrowthComparison, { task }));
  assert.ok(html.includes("未评级"));
  assert.ok(html.includes("任务实现"));
  assert.ok(html.includes("等级 80"));
  assert.ok(!html.includes("/5"));
});
