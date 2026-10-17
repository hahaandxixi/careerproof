import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const { transform } = require("sucrase");

function fixture(hash = "") {
  const effects = [], values = [], windowListeners = new Map(), documentListeners = new Map();
  let cursor = 0;
  const modules = {
    react: { useEffect: fn => effects.push(fn), useRef: current => ({ current }), useState: initial => { const i = cursor++; values[i] = initial; return [initial, value => { values[i] = value; }]; } },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/link": { __esModule: true, default: () => null },
    "next/navigation": { useRouter: () => ({ push() { throw Error("unexpected navigation"); } }) },
    "@/lib/api/client": { api: new Proxy({}, { get() { return () => { throw Error("unexpected API write/read"); }; } }), errorMessage: String },
    "@/lib/analysis-status": { adoptGrowthAdvice() { throw Error("unexpected advice"); } },
    "./EvidenceLink": { __esModule: true, default: () => null },
    "./EnterpriseReplyContext": { __esModule: true, default: () => null },
  };
  const mod = { exports: {} };
  const code = transform(readFileSync(new URL("../src/components/GrowthTaskStart.tsx", import.meta.url), "utf8"), { transforms: ["typescript", "jsx", "imports"], jsxRuntime: "automatic", production: true }).code;
  new Function("require", "module", "exports", code)(id => { assert.ok(id in modules, id); return modules[id]; }, mod, mod.exports);
  const original = { window: globalThis.window, document: globalThis.document, Element: globalThis.Element };
  class Node {
    constructor(href) { this.href = href; }
    closest() { return this.href == null ? null : { getAttribute: () => this.href }; }
  }
  globalThis.Element = Node;
  globalThis.window = { location: { hash, search: "" }, addEventListener: (name, fn) => windowListeners.set(name, fn), removeEventListener: name => windowListeners.delete(name) };
  globalThis.document = { addEventListener: (name, fn) => documentListeners.set(name, fn), removeEventListener: name => documentListeners.delete(name) };
  mod.exports.default({ reportId: "report", requirementId: "redis" });
  const cleanup = effects[1]();
  return {
    values, windowListeners, documentListeners,
    click(href, extra = {}) { documentListeners.get("click")?.({ target: new Node(href), button: 0, ...extra }); },
    close() { values[0] = false; },
    cleanup() { cleanup(); Object.assign(globalThis, original); },
  };
}

test("same-document link opens the task even when SPA navigation emits no hashchange", () => {
  const f = fixture();
  try { f.click("#growth-redis"); assert.equal(f.values[0], true); }
  finally { f.cleanup(); }
});

test("repeating the same hash link reopens a deliberately collapsed form", () => {
  const f = fixture("#growth-redis");
  try { assert.equal(f.values[0], true); f.close(); f.click("#growth-redis"); assert.equal(f.values[0], true); }
  finally { f.cleanup(); }
});

test("other requirements, modified clicks and non-links cannot open this task", () => {
  const f = fixture();
  try {
    for (const extra of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) f.click("#growth-redis", extra);
    f.click("#growth-other"); f.click(null); assert.equal(f.values[0], false);
  } finally { f.cleanup(); }
});

test("unmount removes navigation listeners while direct-bookmark opening remains supported", () => {
  const f = fixture("#growth-redis");
  assert.equal(f.values[0], true); f.cleanup();
  assert.equal(f.windowListeners.size, 0); assert.equal(f.documentListeners.size, 0);
});
