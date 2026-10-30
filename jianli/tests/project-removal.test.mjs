import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import * as upload from "../src/lib/portfolio-upload.ts";
import * as material from "../src/lib/material-upload.ts";

const require = createRequire(import.meta.url);
const runtime = require("react/jsx-runtime");
const { transform } = require("sucrase");
const source = readFileSync(new URL("../src/app/portfolio/page.tsx", import.meta.url), "utf8");

function nodes(node, predicate) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap(value => nodes(value, predicate));
  return [...(predicate(node) ? [node] : []), ...nodes(node.props?.children, predicate)];
}

const versions = [1, 2].map(n => ({ id: `v${n}`, versionNumber: n, status: "completed", createdAt: `2026-10-${20+n}` }));
function workspace(client = {}) {
  let cursor = 0, refCursor = 0;
  const state = { 11: [{ id: "owned", name: "报名服务", versions }, { id: "empty", name: "空项目", versions: [] }], 12: true };
  const refs = [];
  const calls = [];
  const api = { archiveMaterial: async (...args) => { calls.push(args); return { archived: true }; }, listResumes: async () => [], listProjects: async () => [], ...client };
  const modules = {
    react: { Suspense: () => null, useCallback: fn => fn, useEffect() {}, useMemo: fn => fn(),
      useState(initial) { const i=cursor++; if (!(i in state)) state[i]=initial; return [state[i], value => { state[i]=typeof value === "function" ? value(state[i]) : value; }]; },
      useRef(initial) { const i=refCursor++; return refs[i] ??= { current: initial }; } },
    "react/jsx-runtime": runtime, "next/link": { default: () => null, __esModule: true },
    "@/components/AuthProvider": { useAuth: () => ({}) }, "@/components/AccessGate": { ErrorNotice: () => null },
    "@/lib/portfolio-upload": upload, "@/lib/material-upload": material,
    "@/lib/api/client": { api, errorMessage: error => error.message },
  };
  for (const name of ["ArchivedMaterials", "LoginLink", "MaterialFileDropzone", "GrowthUploadReturn", "ReportUploadReturn", "MaterialUploadIntent"]) modules[`@/components/${name}`] = { default: () => null, __esModule: true };
  const code = transform(`${source}\nexport { PortfolioWorkspace };`, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  const render = () => { cursor=0; refCursor=0; return mod.exports.PortfolioWorkspace({ userId: "owner" }); };
  function remove(tree, id="owned") {
    const card = nodes(tree, n => n.props?.item?.resourceId === id && n.props?.latest)[0];
    if (card) return nodes(card.type(card.props), n => n.type === "button" && n.props.children === "移出材料库")[0];
    return nodes(tree, n => n.type === "button" && n.props.children === "移出材料库")[0];
  }
  return { render, remove, state, refs, calls };
}

function browser(t, confirm) {
  const previous = globalThis.window;
  globalThis.window = { confirm, sessionStorage: { removeItem() {} } };
  t.after(() => { globalThis.window = previous; });
}

test("cancel project removal does not call API or change any version", async t => {
  browser(t, message => { assert.match(message, /所有版本.*历史报告.*恢复/); return false; });
  const ui=workspace(); const before=structuredClone(ui.state[11]);
  await ui.remove(ui.render()).props.onClick();
  assert.deepEqual(ui.calls, []); assert.deepEqual(ui.state[11], before);
});

test("confirmed removal calls existing archive and immediately removes every version", async t => {
  browser(t, () => true);
  const ui=workspace(); await ui.remove(ui.render()).props.onClick();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(ui.calls, [["project", "owned", true]]);
  assert.deepEqual(ui.state[11].map(p => p.id), ["empty"]);
  const tree=ui.render(); assert.equal(nodes(tree, n => n.props?.item?.resourceId === "owned").length, 0);
  assert.match(ui.state[14], /已从当前材料库移除/);
});

test("failed archive keeps project and shows the actual error without success notice", async t => {
  browser(t, () => true);
  const ui=workspace({ archiveMaterial: async () => { throw new Error("材料不存在或无权访问"); } });
  await ui.remove(ui.render()).props.onClick(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.state[11][0].id, "owned"); assert.equal(ui.state[14], "");
  assert.ok(nodes(ui.render(), n => n.props?.role === "alert").some(n => n.props.children.includes("材料不存在或无权访问")));
});

test("empty project can be removed and in-flight removal blocks duplicate requests", async t => {
  browser(t, () => true); let finish; let count=0;
  const ui=workspace({ archiveMaterial: () => { count++; return new Promise(resolve => { finish=resolve; }); } });
  const button=ui.remove(ui.render(), "empty"); button.props.onClick(); button.props.onClick();
  assert.equal(count, 1); assert.equal(ui.remove(ui.render(), "empty").props.disabled, true);
  finish({archived:true}); await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(ui.state[11].map(p => p.id), ["owned"]);
});

test("old list response cannot put removed project back into active history", async t => {
  browser(t, () => true); let finishList;
  const ui=workspace({ listProjects: () => new Promise(resolve => { finishList=resolve; }) });
  let tree=ui.render();
  const oldProjects=structuredClone(ui.state[11]);
  nodes(tree, n => n.type === "button" && n.props.children === "刷新列表")[0].props.onClick();
  ui.remove(tree).props.onClick(); await new Promise(resolve => setImmediate(resolve));
  finishList(oldProjects); await new Promise(resolve => setImmediate(resolve));
  tree=ui.render(); assert.equal(nodes(tree, n => n.props?.item?.resourceId === "owned").length, 0);
});
