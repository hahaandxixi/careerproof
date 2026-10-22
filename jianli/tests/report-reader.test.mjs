import test from "node:test";
import assert from "node:assert/strict";
import { registerHooks, createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const require = createRequire(import.meta.url);
const { transform } = require("sucrase");
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith("@/")) {
      const base = path.join(SRC, specifier.slice(2));
      for (const name of [base, `${base}.ts`, `${base}.tsx`]) {
        try { return next(pathToFileURL(name).href, context); } catch {}
      }
    }
    if (specifier.startsWith(".") && !path.extname(specifier)) {
      for (const suffix of ["", ".ts", ".tsx", ".js"]) {
        try { return next(new URL(specifier + suffix, context.parentURL).href, context); } catch {}
      }
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (/\.tsx?$/.test(url)) return {
      format: "module", shortCircuit: true,
      source: transform(readFileSync(fileURLToPath(url), "utf8"), {
        transforms: ["typescript", "jsx"], jsxRuntime: "automatic", filePath: url,
      }).code,
    };
    return next(url, context);
  },
});
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const load = name => import(pathToFileURL(path.join(SRC, name)).href);
const helpers = await load("lib/report-reader.ts");
const { revealEvidenceAnchor } = await load("lib/evidence-anchor.ts");
const verdicts = await load("lib/verdict-display.js");
const { default: Reader } = await load("components/ReportRequirementReader.tsx");
const { default: Overview } = await load("components/ReportOverview.tsx");

const items = [
  { requirementId: "implementation", requirementTitle: "持久化", verdict: "supported", weight: 5, evidenceLevel: 3,
    evidenceList: [{ citationId: "saved-alpha", filePath: "project-v1/service.py", projectVersionId: "project-v1" }] },
  { requirementId: "tests", requirementTitle: "行为测试", verdict: "partial", weight: 4, evidenceLevel: 2,
    evidenceList: [{ citationId: "saved-beta", filePath: "project-v2/service.py", projectVersionId: "project-v2" }, { citationId: null }] },
  { requirementId: "run", requirementTitle: "运行核验", verdict: "gap", weight: 3, evidenceLevel: null, evidenceList: [] },
];
const articles = items.map(item => React.createElement("article", { key: item.requirementId, id: `requirement-${item.requirementId}` },
  React.createElement("p", null, `原文 ${item.requirementTitle}`),
  React.createElement("textarea", { defaultValue: `未保存草稿 ${item.requirementId}` })));

test("initial selection preserves the existing evidence priority without sorting the saved report", () => {
  const before = JSON.stringify(items);
  assert.equal(helpers.initialReportRequirement(items), "tests");
  assert.equal(helpers.initialReportRequirement([items[0]]), "implementation");
  assert.equal(helpers.initialReportRequirement([]), null);
  assert.equal(JSON.stringify(items), before);
});

test("saved citation and rule-source identities resolve exactly across same-name files and versions", () => {
  for (const [anchor, expected] of [
    ["requirement-implementation", "implementation"], ["growth-tests", "tests"],
    ["citation-saved-alpha", "implementation"], ["citation-saved-beta", "tests"],
    ["rule-source-tests-2", "tests"], ["citation-R2-E999", null],
    ["growth-tests?other=1", null], ["rule-source-tests-1", null],
  ]) assert.equal(helpers.requirementForReportAnchor(items, anchor), expected, anchor);
  assert.equal(helpers.reportEntryRequirement(items, "#citation-saved%2Dbeta"), "tests");
  assert.equal(helpers.reportEntryRequirement(items, "#%broken"), null);
});

test("enterprise reply entry selects its saved requirement and never overrides a known citation", () => {
  assert.equal(helpers.reportEntryRequirement(items, "", "?enterpriseReply=run"), "run");
  assert.equal(helpers.reportEntryRequirement(items, "#citation-saved-alpha", "?enterpriseReply=run"), "implementation");
  assert.equal(helpers.reportEntryRequirement(items, "", "?enterpriseReply=unknown"), null);
});

test("real reader SSR keeps every article and draft mounted, with one visible selected panel", () => {
  const html = renderToStaticMarkup(React.createElement(Reader, { items }, articles));
  for (const item of items) {
    assert.ok(html.includes(`href="#requirement-${item.requirementId}"`));
    assert.ok(html.includes(`id="requirement-${item.requirementId}"`));
    assert.ok(html.includes(`未保存草稿 ${item.requirementId}`));
  }
  assert.equal((html.match(/aria-current="true"/g) ?? []).length, 1);
  assert.equal((html.match(/<div hidden="">/g) ?? []).length, 2);
  assert.ok(html.includes("正在查看"));
});

test("overview renders fixed identity, truthful fallback and a single existing-priority action", () => {
  const report = {
    candidateName: "林舟", jobTitle: "后端开发", createdAt: "2026-10-22T10:00:00Z",
    analysisMode: "ai_evidence", aiProvider: "deepseek", aiFallbackUsed: true,
    summary: "保存的报告摘要", items, materials: [
      { title: "库存服务", versionNumber: 1, id: "project-v1", kind: "project" },
      { title: "库存服务", versionNumber: 2, id: "project-v2", kind: "project" },
    ],
  };
  const before = JSON.stringify(report);
  const html = renderToStaticMarkup(React.createElement(Overview, { report, role: "enterprise" }));
  for (const text of ["企业查看", "林舟", "后端开发", "库存服务 · 第 1 版", "库存服务 · 第 2 版", "模型已降级", "本地规则结果", "保存的报告摘要"]) assert.ok(html.includes(text), text);
  assert.equal((html.match(/class="btn /g) ?? []).length, 1);
  assert.ok(html.includes('href="#requirement-tests"'));
  assert.ok(!html.includes("模型耗时"));
  assert.equal(JSON.stringify(report), before);
});

/** Drive the production reader's effects with a controlled commit/animation-frame queue.
 * This checks navigation ordering, not browser geometry, native pointer or keyboard behavior. */
function navigationFixture(hash = "", search = "") {
  const effects = [], values = [], windowListeners = new Map(), documentListeners = new Map(), frames = new Map(), events = [];
  let cursor = 0, nextFrame = 0, committedSelection;
  const modules = {
    react: { Children: React.Children, useEffect: fn => effects.push(fn), useState: initial => {
      const i = cursor++;
      if (!(i in values)) values[i] = typeof initial === "function" ? initial() : initial;
      return [values[i], value => { values[i] = typeof value === "function" ? value(values[i]) : value; }];
    } },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "@/lib/report-reader": helpers,
    "@/lib/evidence-anchor": { revealEvidenceAnchor },
    "@/lib/verdict-display.js": verdicts,
  };
  const mod = { exports: {} };
  const code = transform(readFileSync(path.join(SRC, "components/ReportRequirementReader.tsx"), "utf8"), {
    transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true,
  }).code;
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  const original = { window: globalThis.window, document: globalThis.document, Element: globalThis.Element, requestAnimationFrame: globalThis.requestAnimationFrame, cancelAnimationFrame: globalThis.cancelAnimationFrame };
  class Node {
    constructor(href) { this.href = href; }
    closest() { return { getAttribute: () => this.href }; }
  }
  const details = { tagName: "DETAILS", open: false, parentElement: null };
  const target = { parentElement: details, scrollIntoView() {
    events.push({ selected: committedSelection, open: details.open });
  } };
  globalThis.Element = Node;
  globalThis.window = { location: { hash, search }, addEventListener: (name, fn) => windowListeners.set(name, fn), removeEventListener: name => windowListeners.delete(name) };
  globalThis.document = {
    addEventListener: (name, fn) => documentListeners.set(name, fn), removeEventListener: name => documentListeners.delete(name),
    getElementById: id => id === "citation-saved-alpha" || id === "growth-implementation" || id === "requirement-implementation" ? target : null,
  };
  globalThis.requestAnimationFrame = fn => { const id = ++nextFrame; frames.set(id, fn); return id; };
  globalThis.cancelAnimationFrame = id => frames.delete(id);
  const render = () => { cursor = 0; effects.length = 0; mod.exports.default({ items, children: articles }); committedSelection = values[0].selected; };
  render();
  const cleanupListeners = effects[0]();
  return {
    values, events, details, windowListeners, documentListeners,
    commit() { render(); return effects[1](); },
    flush() { for (const [id, fn] of frames) { frames.delete(id); fn(); } },
    click(href, extra = {}) { documentListeners.get("click")({ target: new Node(href), button: 0, ...extra }); },
    hash(value) { window.location.hash = value; windowListeners.get("hashchange")(); },
    cleanup() { cleanupListeners(); Object.assign(globalThis, original); },
  };
}

test("direct citation bookmark selects the saved requirement before expanding and scrolling", () => {
  const f = navigationFixture("#citation-saved-alpha");
  try {
    assert.equal(f.values[0].selected, "implementation");
    assert.deepEqual(f.events, []);
    f.commit(); f.flush();
    assert.deepEqual(f.events, [{ selected: "implementation", open: true }]);
  } finally { f.cleanup(); }
});

test("same-fragment clicks reopen evidence without hashchange; back/forward and growth links select their item", () => {
  const f = navigationFixture();
  try {
    f.click("#citation-saved-alpha"); f.commit(); f.flush();
    f.details.open = false;
    f.click("#citation-saved-alpha"); f.commit(); f.flush();
    assert.equal(f.events.length, 2);
    assert.ok(f.events.every(event => event.selected === "implementation" && event.open));
    f.hash("#growth-run"); assert.equal(f.values[0].selected, "run");
    f.hash("#requirement-tests"); assert.equal(f.values[0].selected, "tests");
    f.click("#growth-implementation"); f.commit(); f.flush();
    assert.deepEqual(f.events.at(-1), { selected: "implementation", open: true });
  } finally { f.cleanup(); }
});

test("modified, external and unknown links keep selection, and unmount removes listeners and pending scroll", () => {
  const f = navigationFixture();
  try {
    for (const extra of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) f.click("#requirement-implementation", extra);
    f.click("/reports/other#requirement-implementation"); f.click("#citation-unknown");
    assert.equal(f.values[0].selected, "tests");
    f.click("#requirement-implementation"); const cancelScroll = f.commit(); cancelScroll(); f.flush();
    assert.deepEqual(f.events, []);
  } finally { f.cleanup(); }
  assert.equal(f.windowListeners.size, 0); assert.equal(f.documentListeners.size, 0);
});
