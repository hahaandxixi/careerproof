import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { ENTERPRISE_SCENARIOS, parseRunnerArgs, parseCredentialDocument,
  withdrawnNotificationStatus, prepareEvidenceRecord, withdrawnOpenCardsStatus } from "./runner-input.mjs";

test("documented defaults and existing scenario names remain usable", () => {
  assert.deepEqual(parseRunnerArgs([]), { runId: "audit-20261005", scenario: "skeleton" });
  for (const scenario of ENTERPRISE_SCENARIOS) {
    assert.deepEqual(parseRunnerArgs(["--scenario", scenario, "--run", "closure-20261005"]),
      { runId: "closure-20261005", scenario });
  }
});

for (const args of [
  ["--run", ".."], ["--run", "."], ["--run", "a..b"],
  ["--run", "--scenario", "skeleton"], ["--run"],
  ["--run", "valid", "--run", "other"], ["--other", "valid"],
  ["--scenario", "../../outside"], ["--scenario", "..\\..\\outside"],
  ["--scenario", "not-a-scenario"], ["--run", "a".repeat(33)],
]) {
  test(`reject unsafe or ambiguous CLI ${JSON.stringify(args)}`, () => {
    assert.throws(() => parseRunnerArgs(args), /Invalid runner arguments/);
  });
}

test("actual CLI refuses a scenario traversal before creating runtime/evidence directories", () => {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const run = "cli-refusal-20261005";
  const runtime = path.join(root, "backend", ".tmp", "e2e-browser", run);
  // Use the tracked evidence root; historical run folders may be untracked.
  const evidence = path.join(root, "docs", "evidence");
  const before = fs.readdirSync(evidence).sort();
  assert.equal(fs.existsSync(runtime), false, "test run directory must not preexist");
  const result = spawnSync(process.execPath, [fileURLToPath(new URL("./enterprise-browser-runner.mjs", import.meta.url)),
    "--run", run, "--scenario", "../../outside"], { encoding: "utf8", timeout: 10000 });
  assert.equal(result.error, undefined);
  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /no files were written/);
  assert.equal(fs.existsSync(runtime), false);
  assert.deepEqual(fs.readdirSync(evidence).sort(), before);
});

test("malformed synthetic credentials never expose JSON source fragments", () => {
  for (const input of ['{"password":"synthetic-do-not-print",broken}', "null", "[]", '"secret"']) {
    assert.throws(() => parseCredentialDocument(input), error => {
      assert.equal(error.message, "Invalid synthetic credential document");
      assert.equal(error.cause, undefined);
      assert.equal(error.stack.includes("synthetic-do-not-print"), false);
      return true;
    });
  }
  assert.deepEqual(parseCredentialDocument('{"runId":"synthetic"}'), { runId: "synthetic" });
});

test("withdrawn notification needs positive unavailable evidence, missing evidence is blocked", () => {
  assert.equal(withdrawnNotificationStatus("unavailable-notice"), "pass");
  assert.equal(withdrawnNotificationStatus("REPORT-STILL-READABLE"), "fail");
  for (const outcome of [null, undefined, "no-notice-no-report", "unknown"]) {
    assert.equal(withdrawnNotificationStatus(outcome), "blocked");
  }
});

test("unexpected secret-bearing detail is redacted in both console and JSON evidence", () => {
  const source = { name: "unexpected-error", status: "fail", detail: "failed synthetic-private-value twice synthetic-private-value" };
  const { entry, line } = prepareEvidenceRecord(source, 1, ["synthetic-private-value"], "synthetic-time");
  assert.equal(JSON.stringify(entry).includes("synthetic-private-value"), false);
  assert.equal(line.includes("synthetic-private-value"), false);
  assert.equal(entry.detail, "failed <redacted> twice <redacted>");
  assert.equal(line, "[1] fail unexpected-error :: failed <redacted> twice <redacted>");
  assert.equal(source.detail.includes("synthetic-private-value"), true);
});

test("withdrawn-card verification requires every open card to land, and rejects the withdrawn target", () => {
  const a = "11111111-1111-4111-8111-111111111111";
  const b = "22222222-2222-4222-8222-222222222222";
  const c = "33333333-3333-4333-8333-333333333333";
  const proof = { inaccessibleCount: 2, withdrawalEventFound: true, olderUnavailableCount: 1,
    openCount: 2, openAnchors: [`#application-${b}`, `#application-${c}`], withdrawnId: a };
  assert.equal(withdrawnOpenCardsStatus(proof), "pass");
  for (const openAnchors of [["no-landing:{}", ""], [`#application-${b}`, "no-landing:{}"], [`#application-${b}`]]) {
    assert.equal(withdrawnOpenCardsStatus({ ...proof, openAnchors }), "blocked");
  }
  assert.equal(withdrawnOpenCardsStatus({ ...proof, openCount: 0, openAnchors: [] }), "blocked");
  assert.equal(withdrawnOpenCardsStatus({ ...proof, withdrawalEventFound: false }), "blocked");
  assert.equal(withdrawnOpenCardsStatus({ ...proof, openAnchors: [`#application-${a}`, "no-landing:{}"] }), "fail");
});
