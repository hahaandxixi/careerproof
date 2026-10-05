// Static guard for the failure-evidence ordering fix in student-browser-runner.
// The old flow stopped Chrome before dumping failure state, so error dumps only
// ever showed "(page unavailable)". These tests pin the repaired ordering
// without launching Chrome or touching any service.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const RUNNER = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "student-browser-runner.mjs");
const SOURCE = fs.readFileSync(RUNNER, "utf8");

test("runner parses as valid ESM (no half-edited try blocks)", () => {
  const check = spawnSync(process.execPath, ["--check", RUNNER], { encoding: "utf8" });
  assert.equal(check.status, 0, `node --check failed:\n${check.stderr}`);
});

test("activeBrowser is declared: implicit global would crash in ESM", () => {
  assert.match(SOURCE, /^let activeBrowser = null;$/m);
});

test("every scenario catch dumps evidence BEFORE stopping its own Chrome", () => {
  const ordered = SOURCE.match(/await dumpFailureEvidence\(tab\)\.catch\(\(\) => \{\}\);\r?\n\s*await browser\.stop\(\)\.catch\(\(\) => \{\}\);\r?\n\s*throw error;/g) ?? [];
  assert.equal(ordered.length, 8, `expected 8 scenario catch blocks with dump-then-stop, found ${ordered.length}`);
  // And never the reversed order inside one catch block.
  const reversed = SOURCE.match(/await browser\.stop\(\)[^\n]*\r?\n\s*await dumpFailureEvidence/g) ?? [];
  assert.equal(reversed.length, 0, "a catch block stops Chrome before dumping evidence");
});

test("outer catch still backstops dump + browser cleanup", () => {
  assert.match(SOURCE, /if \(lastTab\) await dumpFailureEvidence\(lastTab\)\.catch\(\(\) => \{\}\);/);
  assert.match(SOURCE, /if \(activeBrowser\) await activeBrowser\.stop\(\)\.catch\(\(\) => \{\}\);/);
});

test("dump is idempotent and captures screenshot, network log and page text", () => {
  const dump = SOURCE.match(/async function dumpFailureEvidence\(tab\) \{[\s\S]*?\n\}/)?.[0] ?? "";
  assert.match(dump, /if \(failureEvidenceSaved \|\| !tab\) return;/);
  assert.match(dump, /error-network-log/);
  assert.match(dump, /error-page"/);
  assert.match(dump, /error-page-text/);
});

test("Chrome.stop is idempotent so double cleanup cannot double-kill", () => {
  assert.match(SOURCE, /async stop\(\) \{\r?\n\s*if \(this\.closed\) return;/);
});

test("variant-materials verdict requires citations into the new report, focus evidence rows and a resolved R1", () => {
  const block = SOURCE.match(/async function scenarioVariantMaterials\(\) \{[\s\S]*?\n\}\n\n\/\/ ---/)?.[0] ?? "";
  assert.match(block, /status: materialsOnly && citedNewReport && focusAdded && r1 \? "pass" : "fail"/);
  assert.match(block, /v-materials-new-report-missing", status: "fail"/);
  assert.match(block, /v-materials-refresh-reread", status: reloadedNewVersion \? "pass" : "fail"/);
});

test("variant-job verdict requires removed AND added requirements, separate Python rows, banner and a resolved R2", () => {
  const block = SOURCE.match(/async function scenarioVariantJob\(\) \{[\s\S]*?\n\}\n\n\/\/ ---/)?.[0] ?? "";
  assert.match(block, /status: jobOnly && crossJobBanner && removedAndAdded && pythonSeparate && r2 \? "pass" : "fail"/);
  assert.match(block, /pythonRemoved >= 1 && pythonAdded >= 1/);
  assert.match(block, /v-job-new-report-missing", status: "fail"/);
});

test("variant-both verdict requires both change labels, banner, itemized two-sided explanations and a resolved R3", () => {
  const block = SOURCE.match(/async function scenarioVariantBoth\(\) \{[\s\S]*?\n\}\n\n\/\/ ---/)?.[0] ?? "";
  assert.match(block, /status: both && crossJobBanner && itemized && r3 \? "pass" : "fail"/);
  assert.match(block, /i\.sides\.base && i\.sides\.target && i\.levelLine/);
  assert.match(block, /v-both-refresh-reread", status: claimsBack && targetBack \? "pass" : "fail"/);
});

test("variant task ids reach state immediately after UI creation, and reruns reuse the task instead of recreating", () => {
  for (const key of ["variantMaterialsTaskId", "variantJobTaskId", "variantBothTaskId"]) {
    assert.match(SOURCE, new RegExp(`saveState\\(\\{ ${key}: taskId \\}\\)`), `${key} must be saved right after task creation, before materials/analysis`);
    assert.match(SOURCE, new RegExp(`state\\.${key}`), `${key} must be checked for reuse`);
  }
  assert.match(SOURCE, /async function openGrowthTask\(tab, taskId\)/);
  // reportR1/R2/R3 are only written after the id actually resolved.
  assert.match(SOURCE, /saveState\(\{ reportR1: r1 \}\)/);
  assert.match(SOURCE, /saveState\(\{ reportR2: r2 \}\)/);
  assert.match(SOURCE, /saveState\(\{ reportR3: r3 \}\)/);
});

test("viewport390 proves real visibility: scroll below the sticky header plus hit-test, folded into the verdict", () => {
  const block = SOURCE.match(/async function scenarioViewport390\(\) \{[\s\S]*?\n\}\nasync function overflowCheck/)?.[0] ?? "";
  for (const marker of ["v390-growth-list", "v390-growth-task", "v390-report"]) assert.match(block, new RegExp(marker));
  assert.match(SOURCE, /async function visibleHeadingShot\(tab, name, locatorBody\)/);
  assert.match(SOURCE, /elementFromPoint/);
  assert.match(SOURCE, /headerBottom - 1/);
  assert.match(SOURCE, /status: !overflow\.overflow && vis\.ok \? "pass" : "fail"/);
});

test("comparison extraction is structured so assertions judge rendered evidence, not text blobs", () => {
  const block = SOURCE.match(/async function extractComparison\(tab\) \{[\s\S]*?\n\}\n/)?.[0] ?? "";
  for (const field of ["addedCount", "removedCount", "status:", "focus:", "sides:"]) assert.match(block, new RegExp(field.replace(":", "\\:")));
  assert.match(block, /任务基准/);
  assert.match(block, /目标报告/);
});
