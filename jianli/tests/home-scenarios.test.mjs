// Actual component handlers/effects with a deterministic clock; not browser interaction evidence.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");
const source = readFileSync(new URL("../src/components/HomeScenarioPreview.tsx", import.meta.url), "utf8");
function walk(node) { return !node || typeof node !== "object" ? [] : [node, ...React.Children.toArray(node.props?.children).flatMap(walk)]; }

function preview(t) {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const previousDocument = globalThis.document;
  const listeners = new Map(), focused = [], states = [], effects = [];
  let cursor = 0, effectCursor = 0, pending = [], dirty = false, tree, mounted = true;
  const document = { visibilityState: "visible", addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name), getElementById: id => ({ focus() { focused.push(id); } }) };
  globalThis.document = document;
  const mod = { exports: {} };
  const mocks = {
    react: { ...React, useId: () => "scenario", useState(initial) {
      const index = cursor++;
      if (!(index in states)) states[index] = initial;
      return [states[index], value => { const next = typeof value === "function" ? value(states[index]) : value; if (!Object.is(next, states[index])) { states[index] = next; dirty = true; } }];
    }, useEffect(fn, deps) {
      const index = effectCursor++, previous = effects[index];
      if (!previous || deps.some((value, i) => !Object.is(value, previous.deps[i]))) pending.push(() => { previous?.cleanup?.(); effects[index] = { deps, cleanup: fn() }; });
    } },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) },
    "@/lib/heatmap-demo": { HEATMAP_DEMO: [{ dimensions: [
      { requirementId: "r1", title: "实际合成要求", verdict: "supported" },
      { requirementId: "r2", title: "自述", verdict: "claimed_only" },
      { requirementId: "r3", title: "自动化测试", verdict: "gap" },
    ] }], DEMO_LABELS: { supported: "有证据支持", claimed_only: "仅简历声明", gap: "材料待补充" }, demoCellClass: () => "state" },
  };
  new Function("require", "module", "exports", transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code)(id => { assert.ok(id in mocks, id); return mocks[id]; }, mod, mod.exports);
  const render = () => {
    do { dirty = false; cursor = 0; effectCursor = 0; pending = []; tree = mod.exports.default(); const queue = pending; queue.forEach(fn => fn()); } while (dirty);
    return tree;
  };
  const unmount = () => { if (mounted) { effects.forEach(effect => effect.cleanup?.()); mounted = false; } };
  const h = { render, unmount, focused, listeners, get active() { return states[0]; }, get root() { return render(); },
    tick(ms) { t.mock.timers.tick(ms); if (mounted) render(); return states[0]; },
    tab(index) { return walk(render()).filter(n => n.props?.role === "tab")[index]; },
    button(label) { return walk(render()).find(n => n.type === "button" && n.props["aria-label"] === label); },
    clickTab(index) { h.tab(index).props.onClick(); render(); },
    visibility(value) { document.visibilityState = value; listeners.get("visibilitychange")?.(); render(); },
  };
  render();
  t.after(() => { unmount(); if (previousDocument === undefined) delete globalThis.document; else globalThis.document = previousDocument; });
  return h;
}

test("starts on matching and only changes with a user selection", t => {
  const h = preview(t);
  assert.equal(h.active, 0);
  assert.equal(h.tick(20000), 0);
  h.clickTab(1);
  assert.equal(h.tick(20000), 1);
  h.clickTab(2);
  assert.equal(h.active, 2);
});

test("keyboard navigation moves focus; inactive slides are inaccessible and cannot take focus", t => {
  const h = preview(t);
  for (const [key, index] of [["ArrowRight", 1], ["End", 2], ["Home", 0], ["ArrowLeft", 2]]) {
    let prevented = false;
    h.tab(h.active).props.onKeyDown({ key, preventDefault() { prevented = true; } }); h.render();
    assert.equal(h.active, index); assert.equal(h.focused.at(-1), `scenario-tab-${index}`); assert.ok(prevented);
    const panels = walk(h.root).filter(n => n.props?.role === "tabpanel");
    assert.equal(panels.filter(n => !n.props["aria-hidden"]).length, 1);
    for (const [i, panel] of panels.entries()) { assert.equal(panel.props.inert, i !== index); assert.equal(panel.props.tabIndex, i === index ? 0 : -1); }
  }
});

test("three complete scenes keep synthetic boundaries and use different content structures without API calls", t => {
  const h = preview(t), panels = walk(h.root).filter(n => n.props?.role === "tabpanel");
  assert.ok(walk(panels[0]).some(n => n.type === "dl"));
  assert.ok(walk(panels[1]).some(n => n.type === "ol"));
  assert.ok(walk(panels[2]).some(n => n.type === "dl"));
  const html = renderToStaticMarkup(h.root);
  for (const text of ["数据说明", "当前为交互样例", "不调用模型", "当前缺口", "自动化测试", "V1", "V2", "旧报告和原投递保留原版本"]) assert.ok(html.includes(text), text);
  assert.ok(!source.includes("api.") && !html.includes("78%"));
});
