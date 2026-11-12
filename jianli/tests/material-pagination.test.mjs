// 材料列表轻量分页与筛选回归：先筛选再分页、筛选回第一页、历史版本不计入
// 分页总数、数量减少后页码回落有效页。沿用 sucrase 转译加载真实 page.tsx，
// 用可重放的 useState 单元驱动真实 ListPagination 的翻页按钮。
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import * as demoPresentation from "../src/lib/demo-display-identity.js";
import * as listPagination from "../src/lib/list-pagination.js";
import * as upload from "../src/lib/portfolio-upload.ts";
import * as contract from "../src/lib/material-upload.ts";

const require = createRequire(import.meta.url);
const React = require("react");
const { transform } = require("sucrase");
const runtime = require("react/jsx-runtime");

// Compile the real ListPagination (tsx) so pagination assertions hit production code.
const paginationModule = { exports: {} };
new Function("require", "module", "exports",
  transform(readFileSync(new URL("../src/components/ListPagination.tsx", import.meta.url), "utf8"),
    { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code
)(id => (id === "@/lib/list-pagination.js" ? listPagination : id === "react/jsx-runtime" ? runtime : assert.fail(id)), paginationModule, paginationModule.exports);

const version = (id, number, createdAt) => ({
  id, versionNumber: number, originalFilename: `${id}.zip`, sizeBytes: 1024, createdAt,
  status: "completed", taskId: null, progress: 100, currentStep: null, errorMessage: null,
});

function workspace() {
  const data = { resumes: [], projects: [] };
  const cells = [];
  const effects = [];
  let cursor = 0;
  const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const hooks = {
    Suspense: props => props.children,
    useState(value) { const i = cursor++; if (!(i in cells)) cells[i] = { value }; return [cells[i].value, next => { cells[i].value = typeof next === "function" ? next(cells[i].value) : next; }]; },
    useRef(value) { const i = cursor++; return cells[i] ??= { current: value }; },
    useMemo(fn, deps) { const i = cursor++; if (!cells[i] || !same(cells[i].deps, deps)) cells[i] = { deps, value: fn() }; return cells[i].value; },
    useCallback(fn, deps) { const i = cursor++; if (!cells[i] || !same(cells[i].deps, deps)) cells[i] = { deps, value: fn }; return cells[i].value; },
    useEffect(fn, deps) { const i = cursor++; if (!cells[i] || !same(cells[i].deps, deps)) { const cleanup = cells[i]?.cleanup; cells[i] = { deps }; effects.push(() => { cleanup?.(); cells[i].cleanup = fn(); }); } },
  };
  const modules = {
    "@/lib/demo-display-identity.js": demoPresentation,
    react: hooks,
    "react/jsx-runtime": runtime,
    "next/link": { __esModule: true, default: props => runtime.jsx("a", props) },
    "@/components/GrowthUploadReturn": { __esModule: true, default: () => null },
    "@/components/ReportUploadReturn": { __esModule: true, default: () => null },
    "@/components/MaterialUploadIntent": { __esModule: true, default: () => null },
    "@/components/ListPagination": { __esModule: true, default: paginationModule.exports.default },
    "@/components/MaterialFileDropzone": { __esModule: true, default: () => null },
    "@/components/LoginLink": { __esModule: true, default: () => null },
    "@/components/AuthProvider": { useAuth: () => ({}) },
    "@/components/AccessGate": { ErrorNotice: () => null },
    "@/lib/portfolio-upload": upload,
    "@/lib/material-upload": contract,
    "@/lib/api/client": {
      errorMessage: String,
      api: {
        listResumes: async () => data.resumes,
        listProjects: async () => data.projects,
      },
    },
  };
  const source = readFileSync(new URL("../src/app/portfolio/page.tsx", import.meta.url), "utf8");
  const mod = { exports: {} };
  new Function("require", "module", "exports",
    transform(`${source}\nexport { PortfolioWorkspace };`, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code
  )(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  const render = () => { cursor = 0; return mod.exports.PortfolioWorkspace({ userId: "owner" }); };
  const settle = async () => {
    let tree;
    for (let i = 0; i < 15; i++) { tree = render(); while (effects.length) effects.shift()(); await Promise.resolve(); }
    return tree;
  };
  return { data, render, settle };
}

const flat = node => !node || typeof node !== "object" ? [] : [node, ...React.Children.toArray(node.props?.children).flatMap(flat)];
const text = node => typeof node === "string" || typeof node === "number" ? String(node) : React.Children.toArray(node?.props?.children).map(text).join("");
const rows = tree => flat(tree).filter(node => node.props?.className === "min-w-0");
const button = (tree, label) => flat(tree).find(node => node.type === "button" && text(node).startsWith(label));
// The pager is a function element in the tree; invoke it once to reach its buttons.
const pager = tree => {
  const element = flat(tree).find(node => node.type === paginationModule.exports.default);
  return element ? { element, nav: element.type(element.props) } : null;
};

test("seven materials split into 6 + 1 and history versions never add to the page total", async () => {
  const originalWindow = globalThis.window, originalDocument = globalThis.document;
  globalThis.window = { sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
  globalThis.document = { getElementById: () => null };
  try {
    const h = workspace();
    // 7 resources; one project carries an older version, so raw uploads = 8.
    h.data.resumes = [1, 2, 3].map(n => ({ id: `resume-${n}`, title: `简历${n}`, createdAt: `2026-11-0${n}T00:00:00Z`, versions: [version(`rv-${n}`, 1, `2026-11-0${n}T00:00:00Z`)] }));
    h.data.projects = [
      { id: "project-1", name: "项目一", description: "", version: 2, createdAt: "2026-11-04T00:00:00Z", versions: [version("pv-1-old", 1, "2026-11-01T00:00:00Z"), version("pv-1", 2, "2026-11-04T00:00:00Z")] },
      ...[2, 3, 4].map(n => ({ id: `project-${n}`, name: `项目${["二", "三", "四"][n - 2]}`, description: "", version: 1, createdAt: `2026-11-0${n + 3}T00:00:00Z`, versions: [version(`pv-${n}`, 1, `2026-11-0${n + 3}T00:00:00Z`)] })),
    ];
    let tree = await h.settle();
    assert.match(text(button(tree, "全部")), /全部 7/);
    assert.match(text(button(tree, "简历")), /简历 3/);
    assert.match(text(button(tree, "项目")), /项目 4/);
    assert.equal(rows(tree).length, 6, "page one shows six material items");
    let page = pager(tree);
    assert.match(text(page.nav), /共 7 条 · 第 1 \/ 2 页 · 本页记录 1–6/);
    // The multi-version project's newest row keeps its collapsed history entry.
    assert.match(text(tree), /历史版本（1）/);

    await flat(page.nav).find(node => node.type === "button" && text(node) === "下一页").props.onClick();
    tree = await h.settle();
    assert.equal(rows(tree).length, 1, "page two shows the remaining single item");
    page = pager(tree);
    assert.match(text(page.nav), /第 2 \/ 2 页 · 本页记录 7–7/);
    assert.deepEqual(page.element.props.value, { total: 7, page: 2, pageSize: 6 });

    // Filter change returns to page 1 and shows only that kind with its count.
    await button(tree, "简历").props.onClick(); tree = await h.settle();
    assert.equal(rows(tree).length, 3);
    assert.equal(button(tree, "简历").props["aria-pressed"], true);
    assert.match(text(button(tree, "简历")), /简历 3/);
    assert.equal(pager(tree), null, "filtered list within one page hides the pager");
    for (const kind of flat(tree).filter(node => node.props?.item?.kind)) assert.equal(kind.props.item.kind, "resume");
    await button(tree, "全部").props.onClick(); tree = await h.settle();
    assert.equal(rows(tree).length, 6, "back to all kinds stays on page one");
  } finally { globalThis.window = originalWindow; globalThis.document = originalDocument; }
});

test("shrinking the list after page 2 falls back to a valid page instead of a blank one", async () => {
  const originalWindow = globalThis.window, originalDocument = globalThis.document;
  globalThis.window = { sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
  globalThis.document = { getElementById: () => null };
  try {
    const h = workspace();
    h.data.resumes = [1, 2].map(n => ({ id: `resume-${n}`, title: `简历${n}`, createdAt: `2026-11-0${n}T00:00:00Z`, versions: [version(`rv-${n}`, 1, `2026-11-0${n}T00:00:00Z`)] }));
    h.data.projects = [1, 2, 3, 4, 5].map(n => ({ id: `project-${n}`, name: `项目${n}`, description: "", version: 1, createdAt: `2026-11-0${n}T00:00:00Z`, versions: [version(`pv-${n}`, 1, `2026-11-0${n}T00:00:00Z`)] }));
    let tree = await h.settle();
    const firstPage = pager(tree);
    await flat(firstPage.nav).find(node => node.type === "button" && text(node) === "下一页").props.onClick();
    tree = await h.settle();
    assert.equal(rows(tree).length, 1);
    // Archive two projects elsewhere, then hit the page's own refresh action.
    h.data.projects = h.data.projects.slice(0, 3);
    await button(tree, "刷新列表").props.onClick(); tree = await h.settle();
    assert.equal(rows(tree).length, 5, "clamped page one shows every remaining item");
    assert.equal(pager(tree), null, "no pager once the list fits one page");
    assert.match(text(button(tree, "全部")), /全部 5/);
  } finally { globalThis.window = originalWindow; globalThis.document = originalDocument; }
});
