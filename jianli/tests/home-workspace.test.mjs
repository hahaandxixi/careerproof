// Real component SSR with controlled saved state. Effects/network are deliberately
// not executed; this does not verify late responses, identity races or browser behavior.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");
const component = process.env.CAREERPROOF_HOME_REVIEW_SOURCE || new URL("../src/components/HomeWorkspace.tsx", import.meta.url);
const source = readFileSync(component, "utf8");
const EMPTY = { reports: [], growth: [], notifications: [], jobs: [], resumes: [], projects: [] };

function render(role, { work = EMPTY, errors = [], loading = false, status = "authenticated" } = {}) {
  let cursor = 0;
  const values = [work, errors, loading, 0];
  const modules = {
    react: { ...React, useState: () => [values[cursor++], () => {}], useEffect: () => {} },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) },
    "@/lib/api/client": { api: new Proxy({}, { get() { throw new Error("SSR must not request data"); } }), errorMessage: String },
    "./AuthProvider": { useAuth: () => ({ user: role ? { id: "synthetic", displayName: "当前用户", role } : null, status, reload() {} }) },
  };
  const code = transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  return renderToStaticMarkup(React.createElement(mod.exports.default, null, "公共介绍"));
}

test("a failed read is unknown, while verified empty work can offer the first-material route", () => {
  const unknown = render("student", { errors: ["最近报告读取失败"] });
  assert.ok(unknown.includes("打开我的材料"));
  assert.ok(unknown.includes('role="alert"'));
  assert.ok(!unknown.includes("准备第一份材料"));
  assert.ok(render("student").includes("准备第一份材料"));
});

test("student continues the saved report without enterprise actions", () => {
  const html = render("student", { work: { ...EMPTY, reports: [{ id: "report-owned", jobTitle: "后端开发", createdAt: "2026-10-22T10:00:00Z", analysisMode: "rules" }] } });
  assert.ok(html.includes('href="/reports/report-owned"'));
  assert.ok(html.includes("继续核对：后端开发"));
  assert.ok(html.includes('href="/portfolio"'));
  assert.ok(!html.includes('href="/jobs/new"'));
  assert.ok(!html.includes("企业工作台"));
});

test("enterprise gets its own job and authorized-application routes, not private student work", () => {
  const html = render("enterprise", { work: { ...EMPTY, jobs: [{ id: "owned-job", title: "后端开发", companyName: "合成企业", status: "published" }] } });
  for (const href of ["/jobs/mine", "/jobs/new", "/jobs/owned-job/applications"]) assert.ok(html.includes(`href="${href}"`));
  assert.ok(html.includes("企业工作台"));
  assert.ok(!html.includes('href="/portfolio"'));
  assert.ok(!html.includes('href="/reports"'));
});

test("admin uses its own allowed entries and cannot be rendered as an enterprise workspace", () => {
  const html = render("admin");
  assert.ok(html.includes("管理员工作区"));
  assert.ok(html.includes('href="/jobs"'));
  assert.ok(html.includes('href="/reports"'));
  assert.ok(!html.includes("企业工作台"));
  assert.ok(!html.includes('href="/jobs/mine"'));
  assert.ok(!html.includes('href="/jobs/new"'));
});

test("authentication loading and error never render the saved identity as confirmed", () => {
  const loading = render("student", { status: "loading" });
  assert.ok(loading.includes("正在读取你的工作区"));
  assert.ok(!loading.includes("当前用户"));
  const error = render("student", { status: "error" });
  assert.ok(error.includes("暂时无法确认登录状态"));
  assert.ok(error.includes("公共介绍"));
  assert.ok(!error.includes("当前用户"));
});

test("old growth tasks cannot replace report continuation or form a second student work area",()=>{
 const html=render("student",{work:{...EMPTY,reports:[{id:"report-owned",jobTitle:"当前岗位",createdAt:"2026-10-22T10:00:00Z",analysisMode:"rules"}],growth:[{id:"old-task",requirementTitle:"旧记录",status:"planned"}]}});
 assert.ok(html.includes("继续核对：当前岗位"));
 assert.ok(!html.includes("最近补证任务")&&!html.includes('href="/growth'));
 assert.ok(!source.includes("api.listGrowthTasks"),"home must not depend on the legacy task list API");
});
