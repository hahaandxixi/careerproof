import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { transform } = require("sucrase");
const root = fileURLToPath(new URL("../", import.meta.url));
const modules = new Map();
function ts(file) {
  if (modules.has(file)) return modules.get(file);
  if (file.endsWith(".json")) return JSON.parse(readFileSync(file, "utf8"));
  const mod = { exports: {} };
  const code = transform(readFileSync(file, "utf8"), { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  new Function("require", "module", "exports", code)(id => {
    if (!id.startsWith(".")) return require(id);
    const target = path.resolve(path.dirname(file), id);
    return /\.(js|json)$/.test(target) ? require(target) : ts(target.endsWith(".ts") ? target : target + ".ts");
  }, mod, mod.exports);
  modules.set(file, mod.exports); return mod.exports;
}
const helpers = ts(path.join(root, "src/lib/job-discovery.ts"));
const parse = value => helpers.readDiscoveryQuery(new URLSearchParams(value));

test("seven direction groups retain meaningful children without inventing published jobs", () => {
  assert.equal(helpers.CAREER_DIRECTIONS.length, 7);
  assert.equal(new Set(helpers.CAREER_DIRECTIONS.map(x => x.id)).size, 7);
  for (const group of helpers.CAREER_DIRECTIONS) assert.ok(group.specialties.length >= 4);
  assert.deepEqual(parse("direction=backend&specialty=python&city=深圳&employmentType=internship&language=python&q=API&page=2"), {
    direction: "backend", specialty: "python", city: "深圳", employmentType: "internship", language: "python", q: "API", category: "", page: 2,
  });
});
test("invalid direction/child/language/page are normalized; old q/category still work", () => {
  const invalid = parse("direction=javascript:alert(1)&specialty=python&language=unknown&employmentType=social&page=-4&q=旧岗位&category=software");
  assert.equal(invalid.direction, ""); assert.equal(invalid.specialty, ""); assert.equal(invalid.language, ""); assert.equal(invalid.employmentType, ""); assert.equal(invalid.page, 1);
  assert.equal(invalid.q, "旧岗位"); assert.equal(invalid.category, "software");
  assert.equal(parse("direction=frontend&specialty=python").specialty, "");
  assert.equal(parse("q=" + "a".repeat(300)).q.length, 200);
});
test("URLs roundtrip every independent filter and preserve legacy keyword links", () => {
  const query = parse("direction=testing&specialty=automation&language=python&city=广州&employmentType=full_time&q=a%26b&page=3");
  const url = helpers.discoveryHref(query);
  assert.deepEqual(parse(url.split("?")[1]), query);
  assert.equal(helpers.discoveryHref(helpers.EMPTY_DISCOVERY), "/jobs");
  assert.equal(parse("q=Python").q, "Python");
});

function walk(tree) {
  if (!tree || typeof tree !== "object") return [];
  return [tree, ...React.Children.toArray(tree.props?.children).flatMap(walk)];
}
function component(file, mocks) {
  const mod = { exports: {} };
  const code = transform(readFileSync(path.join(root, file), "utf8"), { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  new Function("require", "module", "exports", code)(id => { assert.ok(id in mocks, id); return mocks[id]; }, mod, mod.exports);
  return mod.exports;
}
const link = { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) };
const icon = { __esModule: true, default: () => React.createElement("svg", { "aria-hidden": true }) };

function harness(search, compact = false) {
  let cursor = 0; let effects = []; const requests = []; const routes = [];
  const state = [{ q: parse(search).q, city: parse(search).city }, null, true, "", 0];
  const api = { listJobs(filters) { return new Promise((resolve, reject) => { requests.push({ filters, resolve, reject }); }); } };
  const router = { push: href => routes.push(["push", href]), replace: href => routes.push(["replace", href]) };
  const mod = component("src/components/JobDiscovery.tsx", {
    react: { ...React, useMemo: fn => fn(), useState: () => { const n = cursor++; return [state[n], value => { state[n] = typeof value === "function" ? value(state[n]) : value; }]; }, useEffect: fn => effects.push(fn) },
    "react/jsx-runtime": require("react/jsx-runtime"), "next/link": link,
    "next/navigation": { useRouter: () => router, useSearchParams: () => new URLSearchParams(search) },
    "@/lib/api/client": { api, errorMessage: String }, "@/lib/api/domain": ts(path.join(root, "src/lib/api/domain.ts")),
    "@/lib/job-discovery": helpers, "./CareerDirectionIcon": icon,
    "./AccessGate": { ErrorNotice: ({ message }) => React.createElement("p", { role: "alert" }, message) },
  });
  return { requests, routes, state, mod, render() { cursor = 0; effects = []; return mod.default({ compact }); }, start() { this.render(); return effects.map(fn => fn()); } };
}
const tick = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };

test("public list sends all filters to the server and ignores a response after cleanup", async () => {
  const h = harness("direction=backend&specialty=python&city=深圳&employmentType=internship&page=3");
  const cleanup = h.start();
  assert.equal(h.requests[0].filters.page, 3); assert.equal(h.requests[0].filters.specialty, "python"); assert.equal(h.requests[0].filters.city, "深圳");
  assert.equal(h.requests[0].filters.pageSize, 12);
  cleanup.at(-1)(); h.requests[0].resolve({ items: [{ id: "late" }], total: 1, page: 1, pageSize: 12 }); await tick();
  assert.equal(h.state[1], null); assert.deepEqual(h.routes, []);
});
test("server clamping replaces the URL rather than displaying an impossible page", async () => {
  const h = harness("direction=backend&page=99"); h.start();
  h.requests[0].resolve({ items: [], total: 13, page: 2, pageSize: 12 }); await tick();
  assert.deepEqual(h.routes, [["replace", "/jobs?direction=backend&page=2"]]);
});
test("home view-all carries actual selection; choosing a direction retains city/type/keyword", () => {
  const h = harness("direction=backend&specialty=python&city=深圳&employmentType=internship&q=API", true);
  const tree = h.render(); const nodes = walk(tree);
  assert.ok(nodes.some(n => n.props?.href === "/jobs?direction=backend&specialty=python&city=%E6%B7%B1%E5%9C%B3&employmentType=internship&q=API"));
  const button = nodes.find(n => n.type === "button" && walk(n).some(c => c.type === "span" && c.props.children === "数据工程"));
  button.props.onClick(); const route = h.routes.at(-1)[1];
  const params = parse(route.split("?")[1]);
  assert.equal(params.direction, "data"); assert.equal(params.specialty, ""); assert.equal(params.city, "深圳"); assert.equal(params.q, "API"); assert.equal(params.employmentType, "internship");
});
test("empty and failure are separate states; cards only use saved public facts", async () => {
  const h = harness(""); h.start(); h.requests[0].resolve({ items: [], total: 0, page: 1, pageSize: 12 }); await tick();
  const html = renderToStaticMarkup(h.render()); assert.ok(html.includes("暂时没有符合条件的岗位")); assert.ok(!html.includes("合成示例岗位"));
  const failed = harness(""); failed.start(); failed.requests[0].reject(new Error("offline")); await tick();
  assert.ok(renderToStaticMarkup(failed.render()).includes("offline"));
  const card = renderToStaticMarkup(React.createElement(h.mod.DiscoveryJobCard, { job: { id: "actual-id", title: "待分类岗位", companyName: "企业原文", city: "", category: "other", employmentType: "full_time", requirementCount: 3, isDemo: true, technicalTags: [] } }));
  assert.ok(card.includes("合成示例岗位") && card.includes("全职") && card.includes("未细分"));
  assert.ok(!card.includes("社招") && !card.includes("匹配度") && !card.includes("薪资"));
});
