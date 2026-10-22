import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import * as workflow from "../src/lib/growth-workflow.ts";
import * as materialUpload from "../src/lib/material-upload.ts";

const require = createRequire(import.meta.url);
const { transform } = require("sucrase");
const { jsx } = require("react/jsx-runtime");
const { renderToStaticMarkup } = require("react-dom/server");
const JOB = "11111111-1111-1111-1111-111111111111";

// Render the actual GrowthContent JSX with saved states. Effects are deliberately
// not mounted: these cases verify available navigation, never call an API.
function renderTask(status, extra = {}) {
  const task = {
    id: "owned-task", jobId: JOB, jobTitle: "合成岗位", requirementId: "requirement",
    requirementTitle: "Redis", status,
    analysisTaskId: ["planned", "materials_selected"].includes(status) ? null : "analysis",
    targetReportId: status === "compared" ? "new-report" : null,
    baseReportId: "old-report", materials: [], baseMaterials: [],
    plan: { deliverable: "静态源码", steps: [], acceptanceChecks: [] },
    boundary: "新报告不更新原投递", ...extra,
  };
  let stateIndex = 0;
  const picker = label => ({ __esModule: true, default: () => jsx("div", { children: label }) });
  const modules = {
    react: { Suspense: props => props.children, useEffect() {}, useRef: current => ({ current }), useState: value => [stateIndex++ === 0 ? task : typeof value === "function" ? value() : value, () => {}] },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: props => jsx("a", props) },
    "@/lib/api/client": { api: new Proxy({}, { get() { return () => { throw Error("unexpected API call"); }; } }), errorMessage: String },
    "@/lib/growth-workflow": workflow,
    "@/lib/material-upload": materialUpload,
    "./GrowthUploadReturn": { GrowthMaterialReview: () => jsx("div", { children: "resume-picker project-picker" }) },
    "./AuthProvider": { useAuth: () => ({ user: { id: "owner", role: "student" } }) },
    "./ResumeVersionPicker": picker("resume-picker"),
    "./ProjectVersionPicker": picker("project-picker"),
    "./GrowthComparison": picker("comparison"),
    "./EnterpriseReplyContext": picker("reply-context"),
    "./PrivateAnswerDraft": picker("private-draft"),
    "./ListPagination": picker("pagination"),
  };
  const source = readFileSync(new URL("../src/components/GrowthWorkspace.tsx", import.meta.url), "utf8");
  const code = transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  const parent = mod.exports.default({ id: task.id });
  return renderToStaticMarkup(parent.type(parent.props));
}

test("finished task does not send students to an upload they cannot save", () => {
  const html = renderTask("compared");
  assert.doesNotMatch(html, /前往上传新版材料|resume-picker|project-picker|保存本次材料选择/);
  assert.match(html, /本轮材料已固定/);
  assert.match(html, /href="\/reports\/new-report"[^>]*>从新报告选择下一条缺口/);
  assert.doesNotMatch(html, /reports\/new-report#/);
});

test("in-flight task keeps the processing route without an upload dead end", () => {
  const html = renderTask("analyzing");
  assert.doesNotMatch(html, /前往上传新版材料|保存本次材料选择|选择下一条缺口/);
  assert.match(html, /本轮材料已固定/);
  assert.match(html, /href="\/tasks\/analysis"/);
});

test("planned, selected and failed tasks retain explicit upload and save", () => {
  for (const status of ["planned", "materials_selected", "analysis_failed"]) {
    const html = renderTask(status);
    assert.match(html, /href="\/portfolio\?growthTask=owned-task"/);
    assert.match(html, /resume-picker/); assert.match(html, /project-picker/);
    assert.match(html, /保存本次材料选择/);
    assert.doesNotMatch(html, /从新报告选择下一条缺口/);
  }
});
