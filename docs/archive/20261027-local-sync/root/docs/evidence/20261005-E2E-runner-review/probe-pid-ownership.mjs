// E2E-R2 offline probe v3 (post Codex independent check on v1/v2):
// (1) how libuv encodes a spawn arg containing spaces on the process command
// line — decides whether pidStillOurs() (enterprise-browser-runner.mjs:217-229)
// can return true when the repo path contains a space; (2) whether PowerShell
// round-trips the manifest startedAt instant so the Ticks equality in
// Start-E2E.ps1:253 / Stop-E2E.ps1:28-29 is stable.
//
// Evidence discipline per Codex review:
//  - the CIM/PowerShell child's stderr and exit code are captured and printed;
//  - an empty CommandLine or non-zero exit is recorded as UNVERIFIED and is
//    never counted as evidence that the runner's includes() check is false;
//  - the target is self-terminating (exits by itself after ~3s); taskkill is
//    issued ONLY when the observed command line is verified to contain this
//    probe's own needle — mirroring the runner's verify-before-kill guard.
//    No kill happens on any unverified observation.
//  - .NET Ticks conversion uses epoch 621355968000000000 (year 1) with BigInt.
//    (116444736000000000 is the FILETIME 1601 offset — must not be used here.)
//
// Side effects: one transient self-exiting node process (~3s), two one-shot
// powershell evaluations, and at most one conditional taskkill on a verified
// PID. No browser, no database, no build, no service, no network, no
// credential or .env access. The profile path is a SYNTHETIC string; nothing
// is created on disk outside this evidence directory.
import { spawn } from "node:child_process";
import fs from "node:fs";

const OUT = [];
const log = (...a) => { const line = a.join(" "); OUT.push(line); console.log(line); };

const FAKE_PROFILE = "D:\\jbcode\\web ai\\jianli\\backend\\.tmp\\e2e-browser\\sha-probe\\profile-enterprise";

function runProbe(command, args, timeoutMs = 8000) {
  return new Promise(resolve => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", c => { out += String(c); });
    child.stderr.on("data", c => { err += String(c); });
    const timer = setTimeout(() => {
      child.kill();
      resolve({ out, err, code: null, timedOut: true });
    }, timeoutMs);
    child.on("exit", code => { clearTimeout(timer); resolve({ out, err, code, timedOut: false }); });
    child.on("error", e => { clearTimeout(timer); resolve({ out, err: `${err}${e.message}`, code: null, timedOut: false }); });
  });
}

// ---- 1. libuv arg encoding probe ------------------------------------------
// node -e "<idle>" -- <dummy>: node stays alive and `--` protects the dummy
// arg from node's own option parser, so libuv must encode it exactly like the
// runner encodes --user-data-dir=<path with spaces>.
log("== libuv command-line encoding for a spawn arg containing a space ==");
const target = spawn(process.execPath, [
  "-e", "setTimeout(() => process.exit(0), 3000)",
  "--", `--user-data-dir=${FAKE_PROFILE}`,
], { stdio: "ignore", windowsHide: true });
await new Promise(r => setTimeout(r, 800));
const q = await runProbe("powershell", ["-NoProfile", "-Command",
  `(Get-CimInstance Win32_Process -Filter 'ProcessId=${target.pid}').CommandLine`]);
log(`  spawned arg list: [..., "--user-data-dir=${FAKE_PROFILE}"]`);
log(`  CIM probe exit code: ${q.code}${q.timedOut ? " (timed out, killed)" : ""}`);
log(`  CIM probe stderr   : ${JSON.stringify(q.err.slice(0, 400))}`);
const observed = q.out.trim();
let verdict;
if (q.code !== 0 || q.timedOut || !observed) {
  verdict = "UNVERIFIED (CIM query failed, empty, or timed out — no claim about pidStillOurs either way)";
  log(`  observed CommandLine: ${observed || "<empty>"}`);
  log(`  verdict: ${verdict}`);
  log(`  no taskkill issued on an unverified observation; target self-exits.`);
} else {
  log(`  observed CommandLine : ${observed}`);
  const needleSeen = observed.includes(`--user-data-dir=${FAKE_PROFILE}`);
  const quotedForm = observed.includes(`"--user-data-dir=${FAKE_PROFILE}"`);
  log(`  runner check needle  : --user-data-dir=${FAKE_PROFILE}`);
  log(`  out.includes(needle) -> ${needleSeen}   (pidStillOurs uses exactly this check at line 226)`);
  log(`  whole-arg quoted form: ${quotedForm} (libuv quotes args containing spaces; the quote sits at arg start, not between = and path)`);
  verdict = needleSeen ? "VERIFIED: needle found, guard can pass on this repo layout" : "VERIFIED: needle NOT found in observed command line";
  log(`  verdict: ${verdict}`);
  if (needleSeen) {
    // Verified-ours only: mirrors the runner's own verify-before-kill guard.
    const kill = await runProbe("taskkill", ["/PID", String(target.pid), "/T", "/F"], 5000);
    log(`  conditional taskkill (verified needle only): exit ${kill.code}, stderr=${JSON.stringify(kill.err.slice(0, 200))}`);
  } else {
    log(`  needle not verified as ours: no taskkill; target self-exits.`);
  }
}

// ---- 2. PowerShell startedAt round-trip ------------------------------------
log("\n== PowerShell [datetime] round-trip of the manifest startedAt instant ==");
log("  manifest writes StartTime.ToUniversalTime().ToString('o') (Start-E2E.ps1:160);");
log("  Stop-E2E.ps1:28-29 compares ([datetime]$record.startedAt).ToUniversalTime().Ticks");
log("  for EQUALITY with Get-Process StartTime.ToUniversalTime().Ticks.");
const STAMP = "2026-10-05T04:35:26.9920000Z";
const ps = await runProbe("powershell", ["-NoProfile", "-Command",
  `$d=[datetime]'${STAMP}'; '{0}|{1}|{2}' -f $d.Kind, $d.Ticks, $d.ToUniversalTime().Ticks`]);
log(`  PS probe exit code: ${ps.code}${ps.timedOut ? " (timed out, killed)" : ""}`);
log(`  PS probe stderr   : ${JSON.stringify(ps.err.slice(0, 400))}`);
const trueUtcTicks = 621355968000000000n + BigInt(Date.parse(STAMP)) * 10000n; // .NET epoch = year 1, BigInt
const parts = ps.out.trim().split("|");
if (ps.code !== 0 || ps.timedOut || parts.length !== 3) {
  log(`  PS probe verdict: UNVERIFIED (exit ${ps.code}, output=${JSON.stringify(ps.out.trim().slice(0, 120))})`);
} else {
  log(`  manifest value : ${STAMP}`);
  log(`  powershell     : Kind|Ticks|ToUniversalTime().Ticks = ${ps.out.trim()}`);
  log(`  true UTC ticks : ${trueUtcTicks}`);
  const equal = BigInt(parts[2]) === trueUtcTicks;
  log(`  cast('Z') -> Kind=${parts[0]}; ToUniversalTime().Ticks equals true UTC ticks: ${equal}`);
  log(`  => Stop-E2E Ticks equality is stable against the manifest value: ${equal}`);
}

fs.writeFileSync(new URL("./probe-pid-ownership-output-v3.txt", import.meta.url), OUT.join("\n") + "\n");
console.log("\n[saved] probe-pid-ownership-output-v3.txt");
