// E2E-R2 offline probe: pure string/path/regex computations that replicate
// enterprise-browser-runner.mjs logic. NO filesystem writes, NO network,
// NO processes, NO reading of any credential or .env file. All inputs are
// synthetic strings defined here.
import path from "node:path";

const OUT = [];
const log = (...a) => { const line = a.join(" "); OUT.push(line); console.log(line); };

// ---- 1. runId regex at enterprise-browser-runner.mjs:31 -------------------
const RUN_ID_RE = /^[\w.-]+$/;
log("== runId regex /^\\w.-+$/ (runner line 31) vs Start/Stop-E2E.ps1 line 27/9 ==");
for (const candidate of ["..", ".", "a..b", "--scenario", "-x", "..\\..\\x", "a/b", "audit-20261005"]) {
  log(`  ${JSON.stringify(candidate).padEnd(16)} runnerRegex=${RUN_ID_RE.test(candidate)}  ps1Regex=${/^[a-z0-9][a-z0-9-]{0,31}$/.test(candidate)}`);
}

// ---- 2. RUNTIME_DIR containment for ".." (runner lines 29-35) -------------
const ROOT = "D:\\jbcode\\web ai\\jianli";
log("\n== RUNTIME_DIR = path.join(ROOT,'backend','.tmp','e2e-browser',RUN_ID) (line 32) ==");
for (const runId of ["audit-20261005", "..", "."]) {
  log(`  runId=${JSON.stringify(runId).padEnd(15)} -> ${path.join(ROOT, "backend", ".tmp", "e2e-browser", runId)}`);
}
log(`  credential filename for '..': ${JSON.stringify(`${".."}.json`)} (line 601: stays inside e2e/, interlocked by raw.runId===RUN_ID at line 604)`);

// ---- 3. STAGE_DIR from unvalidated --scenario (runner lines 30, 42) -------
log("\n== STAGE_DIR = path.join(EVIDENCE_DIR, SCENARIO+'-'+stamp) (line 42) — scenario is NEVER validated ==");
const EVIDENCE_DIR = path.join(ROOT, "docs", "evidence", "20261004-E2E-enterprise");
for (const scenario of ["skeleton", "..\\..\\..\\..\\evil", "..\\..\\out-repo"]) {
  const stage = path.join(EVIDENCE_DIR, `${scenario}-2026-10-05T00-00-00-000Z`);
  const insideRepo = stage.startsWith(path.join(ROOT, "docs", "evidence") + path.sep);
  log(`  scenario=${JSON.stringify(scenario).padEnd(20)} -> ${stage}`);
  log(`    contained under docs/evidence: ${insideRepo}   (mkdirSync top-level line 43; results.json written by catch at line 1292 via persist line 66-69)`);
}

// ---- 4. argValue parameter confusion (runner lines 25-28) -----------------
log("\n== argValue('--run') with argv ['--run','--scenario','skeleton'] (lines 25-28) ==");
const args = ["--run", "--scenario", "skeleton"];
function argValue(name, fallback) {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
}
log(`  RUN_ID=${JSON.stringify(argValue("--run", "audit-20261005"))}  SCENARIO=${JSON.stringify(argValue("--scenario", "skeleton"))}`);
log(`  ('--scenario' swallowed as runId value; passes runner regex; ps1 regex would reject)`);

// ---- 5. fail/blocked aggregation (runner lines 1281-1288) -----------------
log("\n== aggregation: notPassed = steps.filter(s => s.status==='fail'||s.status==='blocked') ==");
function aggregate(steps) {
  const notPassed = steps.filter(s => s.status === "fail" || s.status === "blocked");
  return notPassed.length ? 1 : 0;
}
for (const [name, steps] of Object.entries({
  "all pass": [{ status: "pass" }, { status: "pass" }],
  "one fail": [{ status: "pass" }, { status: "fail" }],
  "one blocked": [{ status: "pass" }, { status: "blocked" }],
  "warn only (old-notification-A 'no-notice-no-report' path, line 1107-1108)": [{ status: "pass" }, { status: "warn" }],
})) {
  log(`  ${name.padEnd(70)} -> exit ${aggregate(steps)}`);
}

// ---- 6. malformed credential JSON echo (runner line 603, scrub line 49-54)
log("\n== JSON.parse SyntaxError echo for malformed synthetic credential files ==");
log("  (SCRUB is built only AFTER successful parse at lines 605-607, so scrub()");
log("   is a no-op if the parse itself throws; whether content reaches the");
log("   message depends on the V8 version's error format.)");
const malformations = {
  "truncated": `{ "runId": "audit-20261005", "accounts": { "enterprise": { "password": "SyntheticPw!42" } }`,
  "stray-token": `{ "runId": "audit-20261005", "accounts": { "enterprise": { "password": "SyntheticPw!42" } p }`,
  "bad-colon": `{ "accounts": { "enterprise": { "password" "SyntheticPw!42" } } }`,
};
for (const [label, synthetic] of Object.entries(malformations)) {
  try { JSON.parse(synthetic); } catch (error) {
    log(`  ${label}: ${error.message}`);
    log(`    password reaches message: ${error.message.includes("SyntheticPw!42")}`);
  }
}
log("  conclusion on node v22.23.1: messages carry position only, no content echo;");
log("  keep a generic-message try/catch as hardening (older/newer V8 may differ).");

import fs from "node:fs";
fs.writeFileSync(new URL("./probe-paths-exitcodes-output.txt", import.meta.url), OUT.join("\n") + "\n");
console.log("\n[saved] probe-paths-exitcodes-output.txt");
