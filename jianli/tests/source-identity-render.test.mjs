// Real component SSR: source labels may change, saved identity and code must not.
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
const { default: SourceIdentity, SourceIdentityDetails } = await import(pathToFileURL(path.join(SRC, "components/SourceIdentity.tsx")).href);
const { default: EvidenceSnippet } = await import(pathToFileURL(path.join(SRC, "components/EvidenceSnippet.tsx")).href);
const { default: SourceCoverage } = await import(pathToFileURL(path.join(SRC, "components/SourceCoverage.tsx")).href);
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));

const A1 = "aaaaaaaa-1111-4111-8111-111111111111";
const A2 = "aaaaaaaa-2222-4222-8222-222222222222";
const B1 = "bbbbbbbb-3333-4333-8333-333333333333";
const LEGAL = "cccccccc-4444-4444-8444-444444444444";
const materials = [
  { kind: "project", id: A1, title: "订单服务", versionNumber: 1 },
  { kind: "project", id: A2, title: "订单服务", versionNumber: 2 },
  { kind: "project", id: B1, title: "库存服务", versionNumber: 1 },
];
const source = (version = A1, extra = {}) => ({
  filePath: `${version}/service.py`, projectVersionId: version,
  lineStart: 4, lineEnd: 5, citationId: "R1-E1", contentHash: "a".repeat(64),
  evidenceType: "python_code", provenance: "portfolio", contextComplete: true,
  contextNote: "保存的原文", snippet: "def read():\n    return 1", ...extra,
});

test("same filename distinguishes projects and versions in the rendered label", () => {
  const labels = [A1, A2, B1].map(version => render(SourceIdentity, { source: source(version), materials }));
  assert.equal(new Set(labels).size, 3);
  assert.ok(labels[0].includes("订单服务 · 第 1 版 · service.py"));
  assert.ok(labels[1].includes("订单服务 · 第 2 版 · service.py"));
  assert.ok(labels[2].includes("库存服务 · 第 1 版 · service.py"));
});

test("details preserve full identity while a legal UUID inside code and filename survives", () => {
  const evidence = Object.freeze(source(A1, {
    filePath: `${A1}/src/${LEGAL}/service.py`, lineStart: 21, lineEnd: 22,
    snippet: `path = "${LEGAL}/service.py"\nassert left < right and value != '&'`,
  }));
  const label = render(SourceIdentity, { source: evidence, materials });
  assert.ok(label.includes(`src/${LEGAL}/service.py`));
  const details = render(SourceIdentityDetails, { source: evidence });
  for (const text of [evidence.filePath, A1, "R1-E1", evidence.contentHash, "第 21–22 行", "python_code"]) {
    assert.ok(details.includes(text), text);
  }
  const html = render(EvidenceSnippet, { evidence, materials });
  assert.ok(html.includes("订单服务 · 第 1 版"));
  const code = html.match(/<code>([\s\S]*?)<\/code>/)[1]
    .replace(/<span aria-hidden="true"[^>]*>[\s\S]*?<\/span>/g, "");
  const decode = text => text.replace(/&quot;/g, '"').replace(/&#x27;/g, "'")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
  const lines = [...code.matchAll(/<span class="block">([\s\S]*?)<\/span>/g)].map(match => decode(match[1]));
  assert.equal(lines.join("\n"), evidence.snippet);
});

test("legacy source retains raw UUID-shaped path and declares missing version", () => {
  const evidence = source(null, { filePath: `${LEGAL}/service.py`, citationId: null });
  assert.ok(render(SourceIdentity, { source: evidence, materials }).includes(evidence.filePath));
  const details = render(SourceIdentityDetails, { source: evidence });
  assert.ok(details.includes(evidence.filePath));
  assert.ok(details.includes("历史版本未记录，保留原始路径"));
  assert.ok(details.includes("规则层来源，无模型引用编号"));
});

test("coverage keeps separate ranges and links of the same file", () => {
  const ranges = [[4, 5], [10, 11]];
  const evidenceList = ranges.map(([start, end], index) => source(A1, {
    lineStart: start, lineEnd: end, functionLineStart: start, functionLineEnd: end,
    sourceLineCount: 20, citationId: `R1-E${index + 1}`,
  }));
  const item = { evidenceList, functionSourceCoverage: ranges.map(([start, end], index) => ({
    file_path: `${A1}/service.py`, function_line_start: start, function_line_end: end,
    covered_line_count: 2, fully_covered: true, citation_ids: [`R1-E${index + 1}`],
  })) };
  const html = render(SourceCoverage, { item, materials });
  for (const text of ["第 4–5 行", "第 10–11 行", 'href="#citation-R1-E1"', 'href="#citation-R1-E2"']) {
    assert.ok(html.includes(text), text);
  }
  assert.equal((html.match(/订单服务 · 第 1 版 · service.py/g) || []).length, 2);
});
