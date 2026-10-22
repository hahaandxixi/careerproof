import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");

function load(path, modules) {
  const loaded = { exports: {} };
  const code = transform(readFileSync(new URL(path, import.meta.url), "utf8"), {
    transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true,
  }).code;
  new Function("require", "module", "exports", code)(id => {
    assert.ok(id in modules, `unexpected import ${id}`);
    return modules[id];
  }, loaded, loaded.exports);
  return loaded.exports;
}

function render(payload, eventType = "tool.completed") {
  const task = { status: "completed", progress: 100, createdAt: "2026-10-18T00:00:00Z",
    startedAt: null, completedAt: null, steps: [{step: 1, name: "模型证据分析", eventType,
      detail: "synthetic", payload}], reportId: null, currentStep: "处理结束" };
  let state = 0;
  const trace = load("../src/lib/process-trace.ts", {});
  const link = { __esModule: true, default: ({children, href}) => React.createElement("a", {href}, children) };
  const contentNotice = load("../src/components/MaterialContentNotice.tsx", {
    "react/jsx-runtime": require("react/jsx-runtime"), "next/link": link,
  });
  const component = load("../src/components/TaskView.tsx", {
    "react": { useEffect() {}, useState: initial => [state++ === 0 ? task : initial, () => {}] },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: ({children, href}) => React.createElement("a", {href}, children) },
    "next/navigation": { useRouter: () => ({push() { throw Error("unexpected navigation"); }}) },
    "@/lib/api/client": { api: {}, errorMessage: String },
    "@/lib/analysis-status": { taskUsedExternalAI: (provider, fallback) => !!provider && provider !== "rules" && !fallback },
    "@/lib/process-trace": trace,
    "./AccessGate": { ErrorNotice: () => null },
    "./MaterialContentNotice": contentNotice,
  }).default;
  return renderToStaticMarkup(React.createElement(component, {id: "synthetic"}));
}

test("skipped and degraded model stages show the reason without a success tick", () => {
  for (const [payload, text] of [
    [{provider: "rules", skippedReason: "not-consented"}, "未调用模型"],
    [{provider: "deepseek", fallbackUsed: true}, "模型已降级"],
  ]) {
    const html = render(payload);
    assert.ok(html.includes(text));
    assert.ok(!html.includes("✓"));
    assert.ok(!html.includes("text-emerald") && !html.includes("text-amber"));
    assert.ok(!html.includes("实际处理时长"));
  }
});

test("completed AI records retain a tick; unavailable records never gain one", () => {
  assert.ok(render({provider: "deepseek", fallbackUsed: false}).includes("✓"));
  assert.ok(!render({}, "verification.unavailable").includes("✓"));
});
