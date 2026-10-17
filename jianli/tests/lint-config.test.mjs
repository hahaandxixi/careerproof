import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

const generatedIgnores = [
  "node_modules/**",
  ".next/**",
  ".next-e2e/**",
  "out/**",
  "next-env.d.ts",
];

test("lint script runs the ESLint CLI noninteractively", () => {
  const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
  assert.equal(pkg.scripts.lint, "eslint .");
});

test("lint devDependencies are pinned to exact compatible versions", () => {
  const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
  assert.equal(pkg.devDependencies.eslint, "9.39.5");
  assert.equal(pkg.devDependencies["eslint-config-next"], "15.5.27");
  assert.equal(pkg.devDependencies["@eslint/eslintrc"], "3.3.7");
  assert.equal(pkg.dependencies.next, "^15.5.27");
  assert.equal(pkg.dependencies.react, "19.0.0");
});

test("flat config loads and extends the Next presets", () => {
  const cfgText = readFileSync(join(root, "eslint.config.mjs"), "utf8");
  assert.ok(cfgText.includes("next/core-web-vitals"));
  assert.ok(cfgText.includes("next/typescript"));
});

test("ESLint resolves the flat config with React Hooks and Next plugins active", () => {
  const result = spawnSync(
    process.execPath,
    [join(root, "node_modules", "eslint", "bin", "eslint.js"), "--print-config", "eslint.config.mjs"],
    { cwd: root, encoding: "utf8" },
  );
  assert.equal(result.status, 0, `eslint --print-config failed: ${result.stderr}`);
  assert.ok(result.stdout.includes("react-hooks"), "react-hooks plugin missing");
  assert.ok(result.stdout.includes("@next/next"), "@next/next plugin missing");
  assert.ok(result.stdout.includes("@typescript-eslint"), "typescript plugin missing");
});

test("flat config sets no local rule overrides (no off / no severity edits)", () => {
  const cfgText = readFileSync(join(root, "eslint.config.mjs"), "utf8");
  assert.ok(!cfgText.includes("rules:"), "config must rely on shared presets only");
});

test("ignores are limited to generated build artifacts", () => {
  const cfgText = readFileSync(join(root, "eslint.config.mjs"), "utf8");
  const match = cfgText.match(/ignores:\s*\[([^\]]*)\]/s);
  assert.ok(match, "config must declare its ignore list");
  const entries = [...match[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(entries, generatedIgnores);
});
