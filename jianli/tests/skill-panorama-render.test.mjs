import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import * as panorama from "../src/lib/skill-panorama.ts";
import * as presentation from "../src/lib/demo-display-identity.js";
import { safeReturnPath, roleReturnPath } from "../src/lib/auth-return.ts";
const require = createRequire(import.meta.url), React = require("react"), { renderToStaticMarkup } = require("react-dom/server"), { transform } = require("sucrase");
let auth = { user: { id: "owner", role: "student" }, status: "authenticated" };
const source = readFileSync(new URL("../src/components/SkillPanorama.tsx", import.meta.url), "utf8");
const modules = {
  react: React, "react/jsx-runtime": require("react/jsx-runtime"),
  "next/link": { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) },
  "@/lib/api/client": { api: {}, errorMessage: e => e.message },
  "@/lib/demo-display-identity.js": presentation, "@/lib/skill-panorama": panorama,
  "./EvidenceSnippet": { __esModule: true, default: () => null }, "./SourceIdentity": { __esModule: true, default: () => null, SourceIdentityDetails: () => null },
  "./AuthProvider": { useAuth: () => auth }, "./AccessGate": { __esModule: true, default: ({ children }) => children },
  "./SkillPanorama.module.css": { __esModule: true, default: new Proxy({}, { get: (_, key) => key }) },
};
const mod = { exports: {} };
new Function("require", "module", "exports", transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
const item = (id, skill, verdict) => ({ requirementId: id, skill, verdict, requirementTitle: `Original requirement ${id}` });
const report = (id, items, versionNumber, extra = {}) => ({ id, jobId: `job-${id}`, jobTitle: `Job ${id}`, createdAt: "2026-11-01T10:00:00Z", materials: [{ kind: "project", id: `version-${versionNumber}`, title: "Fixed material", versionNumber }], items, ...extra });
const reports = [report("old", [item("a", "Python", "partial")], 1, { isLatestForJob: false }), report("new", [item("a", "python", "unsupported"), item("b", "", "custom_state")], 2)];
const state = { ...panorama.initialPanoramaState(), summaries: reports, reports, total: 14, hasMore: true };
const props = { state, selected: null, onSelect() {}, loadMore() {}, retryFailed() {} };
const render = overrides => renderToStaticMarkup(React.createElement(mod.exports.SkillPanoramaView, { ...props, ...overrides }));
const nodes = n => !n || typeof n !== "object" ? [] : [n, ...React.Children.toArray(n.props?.children).flatMap(nodes)];
const text = n => typeof n === "string" || typeof n === "number" ? String(n) : React.Children.toArray(n?.props?.children).map(text).join("");

test("overview renders actual grouped bands and explicit loaded scope, not radar, scores or empty categories", () => {
  const html = render();
  assert.match(html, /已保存报告中的技能/); assert.match(html, /编程语言/); assert.doesNotMatch(html, /数据与存储|<progress|熟练度：|综合评分|岗位技能雷达/);
  assert.match(html, /规则暂未支持 1 条/); assert.doesNotMatch(html, /摘要未加载|演示数据说明/); assert.match(html, /再加载最多 12 份报告/);
});
test("topic selection exposes every context, original report anchors and fixed versions without latest inference", () => {
  let selected;
  const tree = mod.exports.SkillPanoramaView({ ...props, onSelect: key => { selected = key; } });
  nodes(tree).find(n => n.type === "button" && text(n).startsWith("Python")).props.onClick();
  assert.equal(selected, "python"); const html = render({ selected });
  assert.match(html, /aria-pressed="true"/); assert.match(html, /Original requirement a/);
  assert.match(html, /\/reports\/old#requirement-a/); assert.match(html, /\/reports\/new#requirement-a/);
  assert.match(html, /v1/); assert.match(html, /v2/); assert.match(html, /2 个岗位/); assert.doesNotMatch(html, /该岗位最新报告/);
});
test("one jobId collapses older reports into history while a shared title with another jobId stays separate", () => {
  const older = report("older", [item("a", "Python", "partial")], 1, { jobId: "same-job", jobTitle: "Same job", isLatestForJob: false });
  const newer = report("newer", [item("a", "Python", "supported")], 2, { jobId: "same-job", jobTitle: "Same job" });
  const other = report("other", [item("a", "Python", "gap")], 3, { jobId: "other-job", jobTitle: "Same job" });
  const html = render({ selected: "python", state: { ...state, reports: [older, newer, other], summaries: [older, newer, other], total: 3, hasMore: false } });
  assert.match(html, /该岗位其他 1 份历史报告/);
  assert.match(html, /2 个岗位/);
  assert.match(html, /\/reports\/older#requirement-a/);
  assert.match(html, /\/reports\/other#requirement-a/);
  assert.doesNotMatch(html, /该岗位最新报告/);
});
test("status filter keeps skills with a matching record and shows hit count against the full history", () => {
  const supported = report("s", [item("a", "Python", "supported")], 1, { jobId: "job-s" });
  const claimed = report("c", [item("b", "Python", "claimed_only")], 2, { jobId: "job-c" });
  const filtered = render({ selected: "python", filter: "claimed_only", state: { ...state, reports: [supported, claimed], summaries: [supported, claimed], total: 2, hasMore: false } });
  assert.match(filtered, /命中 <strong>1<\/strong> 条 \/ 共 2 条/);
  assert.match(filtered, /命中 1 条/);
  assert.doesNotMatch(filtered, /Original requirement a/);
  assert.match(filtered, /Original requirement b/);
  const none = render({ selected: "python", filter: "gap", state: { ...state, reports: [supported, claimed], summaries: [supported, claimed], total: 2, hasMore: false } });
  assert.match(none, /当前筛选下，这项技能没有匹配的要求记录/);
});
test("unclassified requirements retain original unknown state, never invent a skill label", () => {
  const html = render({ selected: "" });
  assert.match(html, /未标注技能的要求/); assert.match(html, /Original requirement b/); assert.match(html, /原始状态：custom_state/); assert.match(html, /状态未知 \/ 未评估/);
});
test("partial failure and list failure preserve healthy selectable skills and independent retry actions", () => {
  const html = render({ state: { ...state, summaries: [...reports, report("failed", [], 1)], failures: { failed: "offline" }, listError: "page offline" } });
  assert.match(html, /仅重试失败详情/); assert.match(html, /重试列表读取/); assert.match(html, /Python/); assert.match(html, /1 份详情失败/);
  assert.match(html, /offline/);
});
test("empty account has one useful next action without an ornamental canvas", () => {
  const html = render({ state: { ...panorama.initialPanoramaState(), total: 0, hasMore: false } });
  assert.match(html, /还没有已保存报告/); assert.match(html, /href="\/jobs"/); assert.doesNotMatch(html, /技能版图|所选技能的岗位语境/);
});
test("workspace remount key isolates accounts; admin, logout and unresolved auth never mount product data", () => {
  auth = { user: { id: "a", role: "student" }, status: "authenticated" }; const a = mod.exports.default().props.children;
  auth = { user: { id: "b", role: "student" }, status: "authenticated" }; const b = mod.exports.default().props.children;
  assert.notEqual(a.key, b.key);
  for (const value of [{ user: { id: "b", role: "admin" }, status: "authenticated" }, { user: null, status: "unauthenticated" }, { user: { id: "a", role: "student" }, status: "error" }]) {
    auth = value; assert.ok(!mod.exports.default().props.children);
  }
});
test("normal authentication return path supports skills only for student", () => {
  assert.equal(safeReturnPath("/skills"), "/skills"); assert.equal(roleReturnPath("/skills", "student"), "/skills");
  assert.equal(roleReturnPath("/skills", "admin"), "/jobs"); assert.equal(roleReturnPath("/skills", "enterprise"), "/jobs/mine");
});
test("known fixture skills use the same job and fixed-material aliases with a visible disclosure",()=>{
 const saved=report("saved",[item("sql","SQL","claimed_only")],1,{
  jobId:"6c8ad563-ebf8-427c-b4a3-82905f37dbd0",jobTitle:"数据工程实习生 · 合成流程验收",
  materials:[{kind:"resume",id:"4df0cd38-f8d1-45d5-91b5-6f97958eb1dc",title:"本地验收简历",versionNumber:1}],
 });
 const before=structuredClone(saved);
 const html=render({selected:"sql",state:{...state,reports:[saved],summaries:[saved],total:1,hasMore:false}});
 assert.match(html,/数据工程实习生/);assert.match(html,/数据工程方向简历/);assert.doesNotMatch(html,/演示数据说明|合成流程验收|本地验收简历/);
 assert.doesNotMatch(html,/合成流程验收|本地验收简历/);assert.deepEqual(saved,before);
});


test("a status filter keeps a matching skill selected and otherwise moves to a visible one", () => {
  const landscape = panorama.buildSkillPanorama([
    report("one", [item("a", "Python", "supported")], 1, { jobId: "job-one" }),
    report("two", [item("b", "SQL", "gap")], 2, { jobId: "job-two" }),
  ]);
  assert.equal(panorama.selectionForFilter(landscape, "python", "supported"), "python");
  assert.equal(panorama.selectionForFilter(landscape, "python", "gap"), "sql");
  assert.equal(panorama.selectionForFilter(landscape, "sql", "supported"), "python");
  assert.equal(panorama.selectionForFilter(landscape, "python", "claimed_only"), null);
  assert.equal(panorama.selectionForFilter(landscape, null, "gap"), null);
});


test("two requirements from one report stay together and show separate review counts", () => {
  const records = [report("sql", [
    { ...item("query", "SQL", "supported"), confirmationStatus: "rejected" },
    { ...item("index", "SQL", "supported"), confirmationStatus: "corrected" },
  ], 1)];
  const html = render({ selected: "sql", state: { ...state, reports: records, summaries: records } });
  assert.match(html, /1 份报告 · 2 条要求/);
  assert.match(html, /需复核 2 条/);
  assert.match(html, /原报告 · 有证据支持/);
  assert.match(html, /\/reports\/sql#requirement-query/);
  assert.match(html, /\/reports\/sql#requirement-index/);
  assert.doesNotMatch(html, /该岗位其他/);
});
