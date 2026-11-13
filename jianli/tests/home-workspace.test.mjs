import { jobWorkspaceNextStep } from "../src/lib/job-workspace-next-step.ts";
import * as demoPresentation from "../src/lib/demo-display-identity.js";
// Real component SSR with controlled saved state. Effects/network are deliberately
// not executed; this does not verify late responses, identity races or browser behavior.
import test from "node:test";
import { displayIdentity } from "../src/lib/demo-display-identity.js";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");
const component = process.env.CAREERPROOF_HOME_REVIEW_SOURCE || new URL("../src/components/HomeWorkspace.tsx", import.meta.url);
const source = readFileSync(component, "utf8");
const EMPTY = { notifications: [], jobs: [] };

function render(role, { work = EMPTY, errors = [], loading = false, status = "authenticated" } = {}) {
  let cursor = 0;
  const values = [work, errors, loading, 0];
  const modules = {
    react: { ...React, useState: () => [values[cursor++], () => {}], useEffect: () => {} },
 "@/lib/demo-display-identity.js":demoPresentation,
    "next/navigation": { useRouter: () => ({ replace() {} }) },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) },
    "@/lib/api/client": { api: new Proxy({}, { get() { throw new Error("SSR must not request data"); } }), errorMessage: String },
    "./IdentityName": { __esModule: true, default: ({name,identityId}) => {const value=displayIdentity(name,identityId);return value.isExample ? `${value.name} · 示例` : name;} },
    "./AuthProvider": { useAuth: () => ({ user: role ? { id: "synthetic", displayName: "当前用户", role } : null, status, reload() {} }) },
  };
  const code = transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  return renderToStaticMarkup(React.createElement(mod.exports.default, null, "公共介绍"));
}

test("a failed read does not present an unknown workspace as empty", () => {
  const unknown = jobWorkspaceNextStep({ versions: [], incomplete: true });
  assert.equal(unknown.action, "重试读取");
  assert.equal(unknown.href, undefined);
  assert.deepEqual(jobWorkspaceNextStep({ versions: [], incomplete: false }), {description:"暂无待处理事项。", href:"/portfolio", action:"准备材料"});
  assert.deepEqual(jobWorkspaceNextStep({ versions: [{status:"completed", createdAt:"2026-11-12"}], incomplete:false }), {description:"暂无待处理事项。", href:"/jobs", action:"发现岗位"});
});

test("a saved material task is surfaced even without an application", () => {
  const failed = {status:"failed", taskId:"task-a", originalFilename:"项目.zip", createdAt:"2026-11-12"};
  const next = jobWorkspaceNextStep({ versions: [failed], incomplete: true });
  assert.deepEqual(next, { description:"处理失败 · 项目.zip", href:"/tasks/task-a", action:"处理上传问题" });
  const html = render("student");
  assert.match(html,/正在打开求职工作台/);
  assert.doesNotMatch(html,/最近报告|未读消息|快捷入口|企业工作台|公共介绍/);
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

test("legacy growth cannot supply the current task and the report lookup only requests product history",()=>{
  const next = readFileSync(new URL("../src/components/JobWorkspaceNextStep.tsx", import.meta.url),"utf8");
  assert.doesNotMatch(next,/listGrowthTasks|\/growth|api.notifications/);
  assert.match(next,/myApplications\(1, 3, undefined, \{ view: "action" \}\)/);
  assert.match(next,/listReports\(1, 3, \{ scope: "product", view: "jobs" \}\)/);
});
