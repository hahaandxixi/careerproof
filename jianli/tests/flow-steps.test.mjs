import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(here, "../src");
const require = createRequire(import.meta.url);
const { transform } = require("sucrase");

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("next/") && !specifier.endsWith(".js")) {
      try { return nextResolve(specifier + ".js", context); } catch {}
      return nextResolve(specifier, context);
    }
    if (specifier.startsWith("@/")) {
      const base = path.join(SRC, specifier.slice(2));
      for (const candidate of [base, base + ".ts", base + ".tsx", path.join(base, "index.ts"), path.join(base, "index.tsx")]) {
        try { return nextResolve(pathToFileURL(candidate).href, context); } catch {}
      }
      throw new Error(`无法解析别名导入：${specifier}`);
    }
    if ((specifier.startsWith("./") || specifier.startsWith("../")) && !path.extname(specifier)) {
      for (const suffix of ["", ".ts", ".tsx", "/index.ts", "/index.tsx", ".js", "/index.js"]) {
        try { return nextResolve(new URL(specifier + suffix, context.parentURL).href, context); } catch {}
      }
      return nextResolve(specifier, context);
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".ts") || url.endsWith(".tsx")) {
      const out = transform(readFileSync(fileURLToPath(url), "utf8"), {
        transforms: ["typescript", "jsx"], jsxRuntime: "automatic", production: false, filePath: url,
      });
      return { format: "module", source: out.code, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});

const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const { default: FlowSteps } = await import(pathToFileURL(path.join(SRC, "components/FlowSteps.tsx")).href);
const { FLOW_STEPS, studentFlowLocation, flowStepsForLocation } = await import(pathToFileURL(path.join(SRC, "lib/flow-steps.ts")).href);

test("student routes identify location without claiming progress or leaking to other roles", () => {
  for (const [url, key] of [["/portfolio", "materials"], ["/materials/project/v2", "materials"], ["/recommendations", "recommendations"], ["/reports/r1", "matching"], ["/jobs/job1", "matching"], ["/growth/g1", "growth"]]) {
    assert.equal(studentFlowLocation(url, "student"), key);
    for (const role of [undefined, "enterprise", "admin"]) assert.equal(studentFlowLocation(url, role), null);
  }
  for (const url of ["/login", "/demo/heatmap", "/notifications", "/jobs/new", "/jobs/mine", "/jobs/manage", "/jobs/job1/edit", "/jobs/job1/applications", "/applications"]) assert.equal(studentFlowLocation(url, "student"), null);
});

test("navigation retains all five ordered steps and only one current location", () => {
  const html = renderToStaticMarkup(React.createElement(FlowSteps, { steps: flowStepsForLocation("/recommendations"), currentKey: "recommendations" }));
  assert.equal((html.match(/aria-current="step"/g) || []).length, 1);
  assert.ok(html.includes("当前位置"));
  let previous = -1;
  for (const step of FLOW_STEPS) { const position = html.indexOf(step.label); assert.ok(position > previous); previous = position; }
  assert.ok(!/已完成|✓|aria-disabled|emerald|amber|rose|sky/.test(html));
  assert.ok(!html.includes('href="#"'));
  assert.ok(!html.includes('href="/applications"'));
  assert.ok(html.includes('href="/growth"')); // Optional guidance, not a completion gate.
});

test("confirmation is text until a concrete report supplies the existing confirmation anchor", () => {
  for (const pathname of ["/portfolio", "/recommendations", "/reports", "/growth/g1"]) assert.equal(flowStepsForLocation(pathname).at(-1).href, null);
  const steps = flowStepsForLocation("/reports/r1");
  assert.equal(steps.at(-1).href, "/reports/r1#application-submit");
  const html = renderToStaticMarkup(React.createElement(FlowSteps, { steps, currentKey: "matching" }));
  assert.ok(html.includes('href="/reports/r1#application-submit"'));
  assert.ok(!html.includes("已完成"));
});
