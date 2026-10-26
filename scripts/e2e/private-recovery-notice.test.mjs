// Static safety + argument-closure tests for private-recovery-notice-runner.mjs
// (task card 20261011-GLM-goal41-private-recovery-pages). Pure Node — no
// services, no browser, no filesystem writes. The last test spawns a short
// throwaway minimized PowerShell window of its own to exercise the real
// ShowWindow pipeline the page run depends on (skipped when no window
// station). Run:
//   node --test scripts/e2e/private-recovery-notice.test.mjs

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  ALLOWED_RUN_ID, BACKEND, CLEAN_NOTICE, CONSTANT_WARNING_PREFIX, DB_NAME,
  DISCARD_NOTICE, FRONTEND, LOSS_NOTICE_INDEPENDENT_RENDER, READ_ONLY_PREFIX,
  READ_ONLY_SUFFIX, applicationRowsSql, buildMarker, canonicalJson,
  canonicalSnapshotHash, countRowsSql, draftRowSql, parseArgs, psWindow,
  sha256Hex,
} from "./private-recovery-notice-runner.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RUNNER_SOURCE = readFileSync(path.join(HERE, "private-recovery-notice-runner.mjs"), "utf8");
const WORKFLOW_SOURCE = readFileSync(
  path.join(HERE, "..", "..", "jianli", "src", "lib", "private-answer-workflow.ts"), "utf8");
const COMPONENT_SOURCE = readFileSync(
  path.join(HERE, "..", "..", "jianli", "src", "components", "PrivateAnswerDraft.tsx"), "utf8");

test("argument closure: only the pinned run id is accepted", () => {
  assert.deepEqual(parseArgs(["--run", "question-chain-20261010"]), { runId: "question-chain-20261010" });
});

test("argument closure: every other invocation is rejected", () => {
  const rejects = [
    [],
    ["--run"],
    ["--run", ""],
    ["--run", "--x"],
    ["--run", "closure-20261005"],
    ["--run", "question-chain-20261009"],
    ["--run", "QUESTION-CHAIN-20261010"],
    ["--run", "question-chain-20261010 "],
    ["--run", "127.0.0.1:9999"],
    ["--run", "question-chain-20261010", "--run", "question-chain-20261010"],
    ["--run", "question-chain-20261010", "--scenario", "anything"],
    ["--run", "question-chain-20261010", "--port", "9999"],
    ["--scenario", "anything"],
    ["--run", "question-chain-20261010", "--help"],
  ];
  for (const argv of rejects) assert.equal(parseArgs(argv), null, `expected rejection: ${JSON.stringify(argv)}`);
});

test("service and database targets are pinned constants", () => {
  assert.equal(ALLOWED_RUN_ID, "question-chain-20261010");
  assert.equal(FRONTEND, "http://127.0.0.1:3001");
  assert.equal(BACKEND, "http://127.0.0.1:8001");
  assert.equal(DB_NAME, "cp_e2e_question-chain-20261010");
  // No env-based overrides of the pinned targets anywhere in the runner.
  assert.doesNotMatch(RUNNER_SOURCE, /process\.env/);
  // No localhost alias: every service reference stays on 127.0.0.1.
  assert.doesNotMatch(RUNNER_SOURCE, /localhost/);
});

test("fixed notice copy is bound byte-for-byte to the product source", () => {
  assert.ok(WORKFLOW_SOURCE.includes(DISCARD_NOTICE), "discard notice text must exist verbatim in private-answer-workflow.ts");
  assert.ok(WORKFLOW_SOURCE.includes(CLEAN_NOTICE), "clean notice text must exist verbatim in private-answer-workflow.ts");
  // The lossNotice field is independent of notice and only rendered when different.
  assert.ok(COMPONENT_SOURCE.includes(LOSS_NOTICE_INDEPENDENT_RENDER),
    "PrivateAnswerDraft.tsx must keep the independent lossNotice render condition");
  assert.ok(COMPONENT_SOURCE.includes(CONSTANT_WARNING_PREFIX),
    "the constant 'save before leaving' warning must stay on the panel");
});

test("read-only SQL: SELECT-only statements inside a READ ONLY wrapper", () => {
  const statements = [
    draftRowSql("00000000-0000-0000-0000-000000000000"),
    applicationRowsSql(["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]),
    countRowsSql(),
    "SELECT id::text FROM evidence_growth_tasks WHERE created_by = 'u' ORDER BY created_at;",
  ];
  for (const sql of statements) {
    assert.match(sql, /^\s*(SELECT|WITH)/i, `not SELECT-led: ${sql.slice(0, 60)}`);
    assert.doesNotMatch(sql, /\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|VACUUM|CALL|DO)\b/i,
      `write verb found: ${sql.slice(0, 80)}`);
  }
  assert.equal(READ_ONLY_PREFIX, "BEGIN READ ONLY;");
  assert.equal(READ_ONLY_SUFFIX, "ROLLBACK;");
  // The wrapper is applied in dbQuery itself, not left to the caller.
  assert.match(RUNNER_SOURCE, /READ_ONLY_PREFIX.*\$\{sql\}.*READ_ONLY_SUFFIX/s);
  // The database is pinned: the psql call must pass DB_NAME, never a CLI value.
  assert.match(RUNNER_SOURCE, /"-d", DB_NAME/);
});

test("canonical JSON mirrors the seeder's normalized_snapshot_hash", () => {
  // evals/seed_e2e.py: json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
  // separators=(",", ":")) → sha256.
  const sample = { b: 1, a: "中文", nested: { y: [2, 1], x: null } };
  const expected = createHash("sha256")
    .update(JSON.stringify({ a: "中文", b: 1, nested: { x: null, y: [2, 1] } }), "utf8").digest("hex");
  assert.equal(canonicalSnapshotHash(sample), expected);
  assert.deepEqual(canonicalJson({ z: 1, a: { c: 2, b: 3 } }), { a: { b: 3, c: 2 }, z: 1 });
});

test("sha256Hex matches node crypto over utf8", () => {
  assert.equal(sha256Hex("技能声明"), createHash("sha256").update("技能声明", "utf8").digest("hex"));
});

test("markers are one-shot and clearly separated from the precondition seed", () => {
  const a = buildMarker("2026-10-11T00:00:00.000Z");
  const b = buildMarker("2026-10-11T00:00:00.000Z");
  assert.match(a, /^PRIVREC41-[0-9a-f]{8}-2026-10-11T00:00:00\.000Z$/);
  assert.notEqual(a, b, "two markers built at the same instant must differ (random component)");
  assert.ok(!a.includes("PRE-41-前置已保存文本"), "marker must never embed the seed text");
});

test("importing the runner module has no side effects", () => {
  // Reaching this point already proves the import neither exited the process
  // nor started Chrome nor touched the filesystem: the runner only acts under
  // its direct-run guard.
  assert.equal(typeof parseArgs, "function");
  assert.equal(typeof canonicalSnapshotHash, "function");
  assert.ok(RUNNER_SOURCE.includes("const isDirectRun"), "direct-run guard must stay in place");
  assert.ok(RUNNER_SOURCE.includes('process.exit(3)'), "invalid arguments must exit 3 before any write");
});

test("psWindow drives a real minimize/restore roundtrip on its own throwaway window", async t => {
  // The same ShowWindow pipeline the page run depends on, exercised against a
  // 20-second throwaway WinForms window created by this test and killed
  // afterwards (a GUI window gets its own HWND; console children inherit the
  // hidden console and have MainWindowHandle=0). Nothing else on the desktop
  // is touched. Skips honestly when no interactive window station is available.
  const { spawn } = await import("node:child_process");
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const child = spawn("powershell", ["-NoProfile", "-Command",
    "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; " +
    "$f = New-Object System.Windows.Forms.Form; $f.Text = 'p41probe'; " +
    "$f.Size = New-Object System.Drawing.Size(200,100); $f.Show(); " +
    "[System.Windows.Forms.Application]::DoEvents(); Start-Sleep -Seconds 20"], { stdio: "ignore" });
  try {
    await sleep(4000);
    const first = await psWindow(child.pid, 6); // SW_MINIMIZE
    if (first === "NO-WINDOW") { t.skip("no interactive window station here; the mechanism is verified at page-run time or reported blocked"); return; }
    assert.equal(first, "MINIMIZED");
    assert.equal(await psWindow(child.pid, 9), "RESTORED"); // SW_RESTORE
    assert.equal(await psWindow(child.pid, 6), "MINIMIZED"); // SW_MINIMIZE again
  } finally {
    child.kill();
  }
});
