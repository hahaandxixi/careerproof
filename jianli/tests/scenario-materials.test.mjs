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
  for (const scenario of catalog.scenarios) {
    const html = renderToStaticMarkup(React.createElement(Component, {
      title: scenario.title, companyName: catalog.companyName, isDemo: true,
    }));
    for (const field of ["resumeFile", "projectFile"]) {
      assert.ok(html.includes(`/demo-assets/scenarios/${scenario[field]}`), scenario.title);
      assert.ok(existsSync(new URL(`../public/demo-assets/scenarios/${scenario[field]}`, import.meta.url)));
    }
    assert.match(html, /不会自动写入你的账号/);
  }
});

test("ordinary jobs and unrecognized samples do not get unrelated materials", () => {
  for (const props of [
    { title: catalog.scenarios[0].title, companyName: catalog.companyName, isDemo: false },
    { title: catalog.scenarios[0].title, companyName: "真实企业", isDemo: true },
    { title: "其他岗位", companyName: catalog.companyName, isDemo: true },
  ]) assert.equal(renderToStaticMarkup(React.createElement(Component, props)), "");
});
