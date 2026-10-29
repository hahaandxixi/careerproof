import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import * as upload from "../src/lib/portfolio-upload.ts";
import * as contract from "../src/lib/material-upload.ts";

const require = createRequire(import.meta.url);
const { transform } = require("sucrase");
const runtime = require("react/jsx-runtime");

// Exercise the real form submit handler with controlled hook state and an
// offline API. This is not a browser file-picker or drag-and-drop test.
function workspace(file, kind, state = {}) {
  let index = 0;
  const calls = [];
  const errors = [];
  const initial = { 1: kind === "resume" ? file : null, 2: "报名服务", 5: kind === "project" ? file : null, ...state };
  const modules = {
    react: {
      Suspense: props => props.children,
      useCallback: fn => fn, useEffect() {}, useMemo: fn => fn(),
      useRef: value => ({ current: value }),
      useState: value => {
        const key = index++;
        return [key in initial ? initial[key] : value, next => { if (key === 8 || key === 9) errors.push(next); }];
      },
    },
    "react/jsx-runtime": runtime,
    "next/link": { __esModule: true, default: props => runtime.jsx("a", props) },
    "@/components/ArchivedMaterials": { __esModule: true, default: () => null },
    "@/components/GrowthUploadReturn": { __esModule: true, default: () => null },
    "@/components/ReportUploadReturn": { __esModule: true, default: () => null },
    "@/components/MaterialFileDropzone": { __esModule: true, default: () => null },
    "@/components/LoginLink": { __esModule: true, default: () => null },
    "@/components/AuthProvider": { useAuth: () => ({}) },
    "@/components/AccessGate": { ErrorNotice: () => null },
    "@/lib/portfolio-upload": upload,
    "@/lib/material-upload": contract,
    "@/lib/api/client": { errorMessage: String, api: {
      uploadResume: async (_title, selected) => { calls.push(selected); return { versionId: "v", taskId: "t" }; },
      createProject: async () => ({ id: "p", name: "报名服务", description: "", version: 1 }),
      uploadProjectVersion: async (_id, selected) => { calls.push(selected); return { versionId: "v", taskId: "t" }; },
      listResumes: async () => [], listProjects: async () => [],
    } },
  };
  const source = readFileSync(new URL("../src/app/portfolio/page.tsx", import.meta.url), "utf8");
  const code = transform(`${source}\nexport { PortfolioWorkspace };`, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  const tree = mod.exports.PortfolioWorkspace({ userId: "owner" });
  function collect(node, type) {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(item => collect(item, type));
    return [...(node.type === type ? [node] : []), ...collect(node.props?.children, type)];
  }
  return { tree, form: collect(tree, "form")[kind === "resume" ? 0 : 1], calls, errors, collect };
}

test("actual upload forms accept supported uppercase image files", async () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  globalThis.window = { sessionStorage: { setItem() {}, removeItem() {} } };
  globalThis.document = { getElementById: () => null };
  try {
    for (const kind of ["resume", "project"]) {
      const file = new File(["synthetic image"], "证明.PNG", { type: "image/png" });
      const value = workspace(file, kind);
      await value.form.props.onSubmit({ preventDefault() {} });
      assert.equal(value.calls.length, 1, `${kind}: ${value.errors.join(";")}`);
      assert.equal(value.calls[0], file);
    }
  } finally { globalThis.window = originalWindow; globalThis.document = originalDocument; }
});

test("unsupported and oversize files stop actual form handlers before API", async () => {
  for (const kind of ["resume", "project"]) {
    for (const file of [new File(["x"], "script.exe"), { name: "screen.JPG", size: 10 * 1024 * 1024 + 1 }]) {
      const value = workspace(file, kind);
      await value.form.props.onSubmit({ preventDefault() {} });
      assert.equal(value.calls.length, 0);
      assert.ok(value.errors.some(message => message.includes("格式不支持") || message.includes("10MB")));
    }
  }
});

test("returning workspace shows one latest version first and keeps history collapsed", () => {
  const versions = [1, 2].map(n => ({ id: `v${n}`, versionNumber: n, originalFilename: `service-v${n}.zip`, createdAt: `2026-10-${20 + n}`, status: "completed", progress: 100 }));
  const value = workspace(null, "project", { 11: [{ id: "p", name: "报名服务", description: "", versions }], 12: true });
  const details = value.collect(value.tree, "details");
  assert.equal(details[0].props.open, undefined); // historical versions default closed
  assert.equal(details[1].props.id, "add-materials");
  assert.equal(details[1].props.open, false);
  const records = value.collect(value.tree, "section")[0];
  const newest = value.collect(records, "div").flatMap(node => node.props.children ?? []).filter(node => node?.props?.latest);
  assert.equal(newest.length, 1);
  assert.equal(newest[0].props.item.versionId, "v2");
  assert.equal(newest[0].props.item.filename, "service-v2.zip");
});

test("empty loaded workspace opens preparation without making two uploads mandatory", () => {
  const value = workspace(null, "resume", { 12: true });
  const preparation = value.collect(value.tree, "details").find(node => node.props.id === "add-materials");
  assert.equal(preparation.props.open, true);
  assert.equal(value.collect(value.tree, "form").length, 2);
});

test("preparing an existing project version does not claim an upload has started", () => {
 const project={id:"existing",name:"报名服务",description:""};
 const attempt=upload.newProjectAttempt(project.name,project.description,project);
 const value=workspace(null,"project",{15:attempt});
 const headings=value.collect(value.tree,"h2").map(node=>node.props.children);
 assert.ok(headings.includes("上传新版本"));
 const copy=JSON.stringify(value.tree);
 assert.ok(copy.includes("目标项目：报名服务"));assert.ok(!copy.includes("正在上传到"));
 assert.equal(value.calls.length,0);
});
