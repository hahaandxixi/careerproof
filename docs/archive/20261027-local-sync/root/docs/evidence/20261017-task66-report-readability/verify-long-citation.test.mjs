// task66 bounded verification: a very long, unbreakable citation id and gap text must
// not produce an element that can widen the page at 390px. Static HTML cannot measure
// layout, so this asserts the two things that are decidable offline: the wrapping
// classes are present on the text containers, and a long token is emitted unbroken
// (so wrapping must come from CSS, not from truncation).

import test from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import fs from "node:fs";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
// Walk up from this probe until the directory that contains the jianli frontend.
function findFrontend(start) {
  let cursor = start;
  for (let depth = 0; depth < 8; depth += 1) {
    if (fs.existsSync(path.join(cursor, "jianli", "package.json"))) return path.join(cursor, "jianli");
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  throw new Error(`cannot locate jianli frontend above ${start}`);
}
const FRONTEND = findFrontend(here);
const SRC = path.join(FRONTEND, "src");
const require = createRequire(path.join(FRONTEND, "package.json"));
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
const { default: Workspace } = await import(pathToFileURL(path.join(SRC, "components/ReportEvidenceWorkspace.tsx")).href);
const { default: EvidenceSnippet } = await import(pathToFileURL(path.join(SRC, "components/EvidenceSnippet.tsx")).href);

const LONG_TOKEN = "R" + "9".repeat(120);
const LONG_GAP = "缺口说明" + "超长不可断词".repeat(40);

const item = () => ({
  requirementId: "widget",
  requirementTitle: "很长很长的要求标题" + "超长".repeat(30),
  skill: "widget",
  weight: 3,
  verdict: "gap",
  confirmationStatus: "pending",
  evidenceLevelGap: LONG_GAP,
  explanation: "",
  evidenceList: [{ citationId: LONG_TOKEN }],
});

test("a 120-char citation id and a 280-char gap token stay inside wrapping containers", () => {
  const action = {
    requirementId: "widget",
    requirementTitle: "标题",
    skill: "widget",
    weight: 3,
    currentLevel: null,
    source: "ai_suggestion",
    action: "保存可复现的记录",
    evidenceGap: "",
    citationIds: [LONG_TOKEN],
  };
  const html = renderToStaticMarkup(
    React.createElement(Workspace, { report: { id: "r", items: [item()], actionPlan: [action] } })
  );
  // The citation label is emitted whole; wrapping must come from CSS on its containers.
  assert.ok(html.includes(`查看引用 ${LONG_TOKEN}`), "citation label must not be truncated");
  assert.ok(html.includes(LONG_GAP), "gap text must not be truncated");
  // Containers that hold those tokens must carry break-words (and min-w-0 on list items).
  assert.ok(html.includes("break-words"), "wrapping class must be present");
  assert.ok(html.includes("min-w-0"), "min-w-0 must bound the flex children");
  // The citation row itself wraps rather than extending one line.
  assert.ok(html.includes("flex-wrap"), "citation row must wrap");
  // No fixed pixel width can force a horizontal overflow on a text container.
  assert.ok(!/class="[^"]*\bw-\[\d{3,}px\]/.test(html), "no fixed wide pixel container");
});

test("the evidence snippet keeps long source text inside a scroll container", () => {
  const html = renderToStaticMarkup(
    React.createElement(EvidenceSnippet, {
      evidence: {
        citationId: LONG_TOKEN,
        filePath: "src/" + "x".repeat(120) + ".ts",
        lineStart: 1,
        lineEnd: 1,
        snippet: "y".repeat(400),
        contextComplete: true,
        contextNote: "",
      },
    })
  );
  assert.ok(html.includes("max-w-full"), "snippet must cap width");
  assert.ok(html.includes("overflow-auto"), "snippet must scroll instead of widening the page");
  assert.ok(html.includes("min-w-0"), "snippet wrapper must allow shrinking");
});
