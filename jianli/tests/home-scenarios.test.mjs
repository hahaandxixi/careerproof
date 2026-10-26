import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");
const source = readFileSync(new URL("../src/components/HomeScenarioPreview.tsx", import.meta.url), "utf8");
function preview() {
  let active = 0;
  const mod = { exports: {} };
  const mocks = {
    react: { ...React, useId: () => "scenario", useState: () => [active, value => { active = value; }] },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) },
    "@/lib/heatmap-demo": { HEATMAP_DEMO: [{ dimensions: [
      { requirementId: "r1", title: "实际合成要求", verdict: "supported" }, { requirementId: "r2", title: "自述", verdict: "claimed_only" },
    ] }], DEMO_LABELS: { supported: "有证据支持", claimed_only: "仅简历声明" }, demoCellClass: () => "state" },
  };
  new Function("require", "module", "exports", transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code)(id => { assert.ok(id in mocks, id); return mocks[id]; }, mod, mod.exports);
  return () => mod.exports.default();
}
function walk(node) { return !node || typeof node !== "object" ? [] : [node, ...React.Children.toArray(node.props?.children).flatMap(walk)]; }
test("three real handlers switch selected tab and visible panel, without a timer or API", () => {
  const render = preview();
  for (let i = 0; i < 3; i++) {
    const tabs = walk(render()).filter(n => n.props?.role === "tab"); tabs[i].props.onClick();
    const nodes = walk(render());
    assert.equal(nodes.filter(n => n.props?.role === "tabpanel" && !n.props.hidden).length, 1);
    assert.equal(nodes.find(n => n.props?.role === "tab" && n.props["aria-selected"]).props.id, `scenario-tab-${i}`);
  }
  assert.ok(!source.includes("setInterval") && !source.includes("api."));
  const html = renderToStaticMarkup(render());
  for (const text of ["合成预览", "不调用真实 AI", "不用先创建补证任务", "不保证等级上升"]) assert.ok(html.includes(text));
  assert.ok(!html.includes("78%"));
});
test("arrow/Home/End navigation moves focus to the activated tab", () => {
  const render = preview(); const focused = [];
  const previous = globalThis.document;
  globalThis.document = { getElementById: id => ({ focus() { focused.push(id); } }) };
  try {
    for (const [key, id] of [["ArrowRight", "scenario-tab-1"], ["End", "scenario-tab-2"], ["Home", "scenario-tab-0"], ["ArrowLeft", "scenario-tab-2"]]) {
      const tab = walk(render()).find(n => n.props?.role === "tab" && n.props["aria-selected"]);
      let prevented = false; tab.props.onKeyDown({ key, preventDefault() { prevented = true; } });
      assert.equal(focused.at(-1), id); assert.ok(prevented);
    }
  } finally { if (previous === undefined) delete globalThis.document; else globalThis.document = previous; }
});
