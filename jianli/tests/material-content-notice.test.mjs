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
    if (specifier === "next/link") return next(pathToFileURL(require.resolve("next/link.js")).href, context);
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
const { default: Notice } = await import(pathToFileURL(path.join(SRC, "components/MaterialContentNotice.tsx")).href);
const payload = findings => ({ version: "local-content-warnings-v1", warningOnly: true, findings, truncated: false });
const finding = (category = "spam", extra = {}) => ({ category, path: "docs/profile.txt", line: 8, ruleId: "local-rule", ...extra });
const render = report => renderToStaticMarkup(React.createElement(Notice, { report }));

test("real notice renders category and original location without repeating source content", () => {
  const html = render(payload([finding("recruitment_fraud", { snippet: "DO-NOT-ECHO", matched: "SECRET-TEXT" })]));
  for (const text of ["本地内容核对提示", "疑似招聘收费或诈骗诱导", "docs/profile.txt", "第 8 行", "不是违规判定", "测试字符串", "不修改材料原文或评级", 'href="/portfolio"']) {
    assert.ok(html.includes(text), text);
  }
  assert.ok(!html.includes("DO-NOT-ECHO") && !html.includes("SECRET-TEXT"));
  assert.ok(!html.includes("aria-live"), "history should not repeatedly announce all matches");
});

test("four categories remain distinct and markup-like filenames are escaped", () => {
  const html = render(payload([
    finding("sexual_solicitation"), finding("abuse_threat"),
    finding("recruitment_fraud"), finding("spam", { path: '<script>alert("x")</script>.txt' }),
  ]));
  for (const text of ["疑似色情招揽", "疑似辱骂或威胁", "疑似招聘收费或诈骗诱导", "疑似垃圾广告"]) assert.ok(html.includes(text));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("break-all"));
});

test("malformed and unknown schemas never become a safety certification", () => {
  for (const value of [null, [], "raw", {}, { findings: [] }, { ...payload([]), warningOnly: false }, payload([finding("unknown"), finding("spam", { line: -1 }), null])]) {
    assert.equal(render(value), "");
  }
  assert.equal(render(payload([])), "");
});

test("truncation is visible even when no match was retained", () => {
  const html = render({ ...payload([]), truncated: true });
  assert.ok(html.includes("未完整覆盖"));
  assert.ok(html.includes("并非完整清单"));
  assert.ok(!html.includes("<details"));
});

test("rendering stays bounded and cannot expose arbitrary payload fields", () => {
  const html = render(payload(Array.from({ length: 100 }, (_, index) => finding("spam", { path: "a".repeat(1100), line: index + 1 }))));
  assert.equal((html.match(/<li>/g) ?? []).length, 30);
  assert.ok(html.includes("并非完整清单"));
  assert.ok(!html.includes("a".repeat(1025)));
});
