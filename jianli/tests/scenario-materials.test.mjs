import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
const { transform } = require("sucrase");
const source = readFileSync(new URL("../src/components/ScenarioMaterials.tsx", import.meta.url), "utf8");
const compiled = transform(source, { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "classic" }).code;
const compiledModule = { exports: {} };
new Function("module", "exports", "React", compiled)(compiledModule, compiledModule.exports, React);
const Component = compiledModule.exports.default;
const catalog = JSON.parse(readFileSync(new URL("../../demo/market-scenarios.json", import.meta.url), "utf8"));

test("each canonical sample renders its own real downloadable files", () => {
  const paired = catalog.scenarios.filter(scenario => scenario.resumeFile && scenario.projectFile);
  assert.equal(paired.length, 3, "the original three material pairs must remain available");
  for (const scenario of paired) {
    const html = renderToStaticMarkup(React.createElement(Component, {
      title: scenario.title, companyName: catalog.companyName, isDemo: true,
    }));
    for (const field of ["resumeFile", "projectFile"]) {
      assert.ok(html.includes(`/demo-assets/scenarios/${scenario[field]}`), scenario.title);
      assert.ok(existsSync(new URL(`../public/demo-assets/scenarios/${scenario[field]}`, import.meta.url)));
    }
    assert.match(html, /href="\/portfolio"/);
    assert.equal((html.match(/\bdownload=""/g) ?? []).length, 2);
    assert.doesNotMatch(html, /<form\b|<button\b/);
  }
});

test("new discovery-only samples do not advertise nonexistent downloads", () => {
  const unpaired = catalog.scenarios.filter(scenario => !scenario.resumeFile);
  assert.equal(unpaired.length, 6);
  for (const scenario of unpaired) assert.equal(renderToStaticMarkup(React.createElement(Component, {
    title: scenario.title, companyName: catalog.companyName, isDemo: true,
  })), "");
});

test("ordinary jobs and unrecognized samples do not get unrelated materials", () => {
  for (const props of [
    { title: catalog.scenarios[0].title, companyName: catalog.companyName, isDemo: false },
    { title: catalog.scenarios[0].title, companyName: "真实企业", isDemo: true },
    { title: "其他岗位", companyName: catalog.companyName, isDemo: true },
  ]) assert.equal(renderToStaticMarkup(React.createElement(Component, props)), "");
});

test("demo page delegates cases to the gallery and retains synthetic boundary copy", () => {
  const samples = JSON.parse(readFileSync(new URL("../src/app/demo/samples.json", import.meta.url), "utf8"));
  const page = readFileSync(new URL("../src/app/demo/page.tsx", import.meta.url), "utf8");
  const mod = { exports: {} };
  const modules = {
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: props => React.createElement("a", props) },
    "@/components/SourceCoverageDemo": { __esModule: true, default: () => null },
    "@/components/DemoCaseGallery": { __esModule: true, default: ({samples}) => React.createElement("div", {"data-cases": samples.length}) },
    "@/components/StickyRail": { __esModule: true, default: ({children}) => React.createElement("aside", null, children) },
    "./samples.json": { __esModule: true, default: samples },
    "./coverage.json": { __esModule: true, default: [] },
  };
  new Function("require", "module", "exports", transform(page, {transforms:["typescript","jsx","imports"],jsxRuntime:"automatic",production:true}).code)(id => { assert.ok(id in modules,id); return modules[id]; },mod,mod.exports);
  const html=renderToStaticMarkup(React.createElement(mod.exports.default));
  assert.ok(html.includes(`data-cases="${samples.length}"`));
  assert.ok(html.includes("所有人物、经历和指标均为虚构"));
});
