import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");
const code = transform(readFileSync(new URL("../src/components/GrowthTaskStart.tsx", import.meta.url), "utf8"), {
  transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true,
}).code;
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const task = extra => ({ id: "owned-task", baseReportId: "report", requirementId: "cache", targetReportId: null,
  plan: { deliverable: "本人保存的工程材料", steps: ["核对实现与异常路径", "整理版本对应记录"], acceptanceChecks: ["引用可定位"] }, ...extra });
const nodes = tree => !tree || typeof tree !== "object" ? [] : [tree, ...React.Children.toArray(tree.props?.children).flatMap(nodes)];

/** Controlled hooks drive the production effect and event handlers, not a browser/DOM test. */
function fixture(options = {}) {
  const slots = [], effects = [], cleanups = [], pending = [], calls = [], navigation = [];
  let cursor = 0, props = { reportId: "report", requirementId: "cache", primary: true, triggerLabel: "开始补证", ...options }, tree;
  const lookup = [], writes = [];
  const modules = {
    react: {
      useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === "function" ? initial() : initial;
        return [slots[i], value => { slots[i] = typeof value === "function" ? value(slots[i]) : value; }]; },
      useRef(initial) { const i = cursor++; return slots[i] ??= { current: initial }; },
      useEffect(fn, deps) { const i = cursor++; if (!effects[i] || deps.some((dep, j) => !Object.is(dep, effects[i].deps[j]))) pending.push(() => { cleanups[i]?.(); cleanups[i] = fn(); }); effects[i] = { deps }; },
    },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: ({ children, ...rest }) => React.createElement("a", rest, children) },
    "next/navigation": { useRouter: () => ({ push: value => navigation.push(value) }) },
    "@/lib/api/client": { errorMessage: error => error.message, api: {
      existingGrowthTask(report, requirement) { calls.push(["lookup", report, requirement]); const request = deferred(); lookup.push(request); return request.promise; },
      enterpriseReplyContext: async () => null,
      createGrowthTask(report, plan) { calls.push(["write", report, plan]); const request = deferred(); writes.push(request); return request.promise; },
    } },
    "@/lib/analysis-status": { adoptGrowthAdvice() { throw Error("unexpected adoption"); } },
    "./EvidenceLink": { __esModule: true, default: () => null },
    "./EnterpriseReplyContext": { __esModule: true, default: () => null },
  };
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  const original = { window: globalThis.window, document: globalThis.document };
  globalThis.window = { location: { hash: "", search: "" }, addEventListener() {}, removeEventListener() {} };
  globalThis.document = { addEventListener() {}, removeEventListener() {} };
  function render() { cursor = 0; tree = mod.exports.default(props); }
  function commit() { render(); while (pending.length) pending.shift()(); render(); }
  commit();
  return {
    lookup, writes, calls, navigation,
    commit,
    html() { render(); return renderToStaticMarkup(tree); },
    open() { nodes(tree).find(node => node.type === "button").props.onClick(); commit(); },
    retry() { nodes(tree).find(node => node.type === "button" && node.props.children === "重新读取任务").props.onClick(); commit(); },
    select(reportId, requirementId) { props = { ...props, reportId, requirementId }; commit(); },
    submit() { return nodes(tree).find(node => node.type === "form").props.onSubmit({ preventDefault() {} }); },
    async settle(request, value, error = false) { request[error ? "reject" : "resolve"](value); await Promise.resolve(); await Promise.resolve(); commit(); },
    cleanup() { cleanups.forEach(fn => fn?.()); Object.assign(globalThis, original); },
  };
}

test("opening a missing-task entry reads first; only an explicit submit creates, and repeated submits share the lock", async () => {
  const f = fixture();
  try {
    assert.equal(f.calls.length, 0);
    f.open(); assert.deepEqual(f.calls, [["lookup", "report", "cache"]]);
    assert.ok(!f.html().includes("保存并进入补证"));
    await f.settle(f.lookup[0], null);
    assert.ok(f.html().includes("保存并进入补证"));
    const submitting = f.submit(); await f.submit();
    assert.equal(f.calls.filter(call => call[0] === "write").length, 1);
    await f.settle(f.writes[0], task()); await submitting;
    assert.deepEqual(f.navigation, ["/growth/owned-task"]);
  } finally { f.cleanup(); }
});

test("existing planned and completed tasks reuse their saved plan and links, never create on open or re-open", async () => {
  for (const targetReportId of [null, "new-report"]) {
    const f = fixture(); const saved = task({ targetReportId }); const before = JSON.stringify(saved);
    try {
      f.open(); await f.settle(f.lookup[0], saved);
      const html = f.html();
      for (const text of ["本人保存的工程材料", "核对实现与异常路径", "引用可定位", 'href="/growth/owned-task"']) assert.ok(html.includes(text), text);
      assert.ok(html.includes(targetReportId ? "查看补证结果" : "继续补证任务"));
      assert.equal(html.includes('href="/reports/new-report"'), !!targetReportId);
      assert.ok(!html.includes("保存并进入补证"));
      f.open(); assert.ok(f.html().includes(targetReportId ? "查看补证结果" : "继续补证任务"));
      f.open(); assert.equal(f.lookup.length, 2);
      await f.settle(f.lookup[1], saved);
      assert.equal(f.calls.filter(call => call[0] === "write").length, 0);
      assert.equal(JSON.stringify(saved), before);
    } finally { f.cleanup(); }
  }
});

test("denied and temporarily unavailable lookups expose retry without opening a create form", async () => {
  for (const message of ["任务不存在或无权访问", "暂时无法读取任务"]) {
    const f = fixture();
    try {
      f.open(); await f.settle(f.lookup[0], Error(message), true);
      assert.ok(f.html().includes(message) && f.html().includes("重新读取任务"));
      assert.ok(!f.html().includes("保存并进入补证"));
      f.retry(); await f.settle(f.lookup[1], task());
      assert.ok(f.html().includes("继续补证任务"));
      assert.equal(f.calls.filter(call => call[0] === "write").length, 0);
    } finally { f.cleanup(); }
  }
});

test("a late lookup from another report cannot replace the selected task, and review warnings stay visible", async () => {
  const adopted = [];
  const f = fixture({ onExistingTask: value => adopted.push(value) });
  try {
    f.open(); f.select("report2", "other");
    await f.settle(f.lookup[1], task({ id: "new-task", actionNeedsRecheck: true, taskPlanWarning: "旧建议待核对" }));
    await f.settle(f.lookup[0], task({ id: "late-task" }));
    const html = f.html();
    assert.ok(html.includes('href="/growth/new-task"')); assert.ok(!html.includes("late-task"));
    assert.ok(html.includes('role="alert"') && html.includes("旧建议待核对"));
    assert.equal(adopted.at(-1)?.id, "new-task");
    assert.ok(!adopted.some(value => value?.id === "late-task"));
  } finally { f.cleanup(); }
});

test("the shared action panel receives the exact saved plan without a second copy in the task launcher", async () => {
  let adopted;
  const f = fixture({ onExistingTask: value => { adopted = value; }, showExistingPlan: false });
  try {
    const saved = task(); f.open(); await f.settle(f.lookup[0], saved);
    assert.equal(adopted, saved);
    assert.ok(!f.html().includes("本人保存的工程材料"));
    assert.ok(f.html().includes('href="/growth/owned-task"'));
    assert.equal(f.calls.filter(call => call[0] === "write").length, 0);
  } finally { f.cleanup(); }
});
