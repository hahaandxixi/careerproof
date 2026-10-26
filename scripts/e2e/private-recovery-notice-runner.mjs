// PRIVATE-RECOVERY-41 private draft discard-notice real-page acceptance runner
// (task card 20261011-GLM-goal41-private-recovery-pages).
// Drives the REAL production page at http://127.0.0.1:3001 through a real
// HEADED Chrome over raw CDP with an independent profile. The discard notice
// under acceptance is triggered by a REAL OS-level window minimize/restore
// (Win32 ShowWindow on this run's own Chrome window) — never by dispatching a
// synthetic visibilitychange or by overriding document.visibilityState.
// Every draft action (read, type, save the precondition seed, re-read) goes
// through the page UI only; Node-side authenticated API calls and psql are
// preflight/read-only cross-checks, never a substitute for the page. The
// one-shot synthetic marker text is typed into the textarea but NEVER saved:
// the only PUT in the whole run is the precondition seed save, so the final
// read-only psql compare proves the server draft, the three delivery
// snapshots and the existing sent reply are byte-identical before/after.
// No SQL writes anywhere (BEGIN READ ONLY ... ROLLBACK, pinned to the e2e
// database cp_e2e_question-chain-20261010; the business database is never
// touched).
//
// Usage: node scripts/e2e/private-recovery-notice-runner.mjs --run question-chain-20261010
// The run id is pinned (only question-chain-20261010 is accepted); services
// are pinned to 127.0.0.1:8001 (backend) / 127.0.0.1:3001 (frontend) and there
// are no CLI knobs for run id, host or port.
// Exit codes: 0 pass, 1 fail, 2 blocked (e.g. services not ready), 3 invalid
// arguments (nothing is written in that case).
//
// Secrets (synthetic passwords, cookie values) are loaded programmatically,
// kept in memory, scrubbed from every log/evidence file and never printed.
// Write surface: this file + scripts/e2e/private-recovery-notice.test.mjs +
// docs/evidence/20261011-GLM-goal41/ + own ignored browser profile under
// backend/.tmp/e2e-browser/question-chain-20261010-private-recovery.

import { spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseCredentialDocument } from "./runner-input.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
export const FRONTEND = "http://127.0.0.1:3001";
export const BACKEND = "http://127.0.0.1:8001";
const API = `${BACKEND}/api/v1`;
const BACKEND_DIR = path.join(ROOT, "backend");
export const ALLOWED_RUN_ID = "question-chain-20261010";
export const DB_NAME = `cp_e2e_${ALLOWED_RUN_ID}`;
const EVIDENCE_DIR = path.join(ROOT, "docs", "evidence", "20261011-GLM-goal41");
const RUNTIME_DIR = path.join(BACKEND_DIR, ".tmp", "e2e-browser", `${ALLOWED_RUN_ID}-private-recovery`);
const CREDS_FILE = path.join(BACKEND_DIR, ".tmp", "e2e", `${ALLOWED_RUN_ID}.json`);
const MANIFEST_FILE = path.join(BACKEND_DIR, ".tmp", "e2e-run", `processes-${ALLOWED_RUN_ID}.json`);

// Fixed copy under acceptance — must match the product byte-for-byte
// (jianli/src/lib/private-answer-workflow.ts). The static test re-reads the
// product source to keep this binding honest.
export const DISCARD_NOTICE =
  "页面已隐藏或切换身份：私人草稿状态已清除，未保存的修改已丢弃（草稿没有发送给企业）；恢复可见后将重新读取已保存草稿。";
export const CLEAN_NOTICE =
  "页面已隐藏或切换身份：私人草稿状态已清除；没有未保存的编辑，恢复可见后将重新读取。";
export const CONSTANT_WARNING_PREFIX = "离开或最小化窗口会清除未保存的编辑";
export const LOSS_NOTICE_INDEPENDENT_RENDER = "state.lossNotice && state.lossNotice !== state.notice";

export const READ_ONLY_PREFIX = "BEGIN READ ONLY;";
export const READ_ONLY_SUFFIX = "ROLLBACK;";

// Precondition seed (saved through the real UI when the server has no draft
// yet). Deliberately distinct from the marker prefix; it is the only text the
// runner ever saves and it becomes the "original draft" whose version and
// digest must be unchanged at the end.
function buildSeedText(at) {
  return `PRE-41-前置已保存文本 ${at}`;
}
export function buildMarker(at) {
  return `PRIVREC41-${randomBytes(4).toString("hex")}-${at}`;
}

// ---------------------------------------------------------------------------
// Arguments: strictly closed — only "--run question-chain-20261010".
// ---------------------------------------------------------------------------
export function parseArgs(argv) {
  const seen = new Set();
  let runId = null;
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i], value = argv[i + 1];
    if (key !== "--run" || seen.has(key)) return null;
    if (typeof value !== "string" || !value || value.startsWith("--")) return null;
    seen.add(key);
    runId = value;
  }
  return runId === ALLOWED_RUN_ID ? { runId } : null;
}

// ---------------------------------------------------------------------------
// Read-only SQL (SELECT only; wrapped READ ONLY server-side; pinned to the
// e2e database). Exported for the static safety test.
// ---------------------------------------------------------------------------
export function draftRowSql(taskId) {
  return `SELECT COALESCE(json_agg(json_build_object('revision', d.revision, 'text', d.text, 'updated_at', d.updated_at, 'references', d."references")), '[]'::json)::text FROM growth_answer_drafts d WHERE d.growth_task_id = '${taskId}';`;
}
export function applicationRowsSql(applicationIds) {
  const ids = applicationIds.map(id => `'${id}'`).join(", ");
  return `SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)::text FROM (SELECT id, status, report_id, report_snapshot, reply_kind, reply_text, reply_references, version, created_at, updated_at FROM applications WHERE id IN (${ids}) ORDER BY id) t;`;
}
export function countRowsSql() {
  return `SELECT 'match_reports', count(*) FROM match_reports UNION ALL SELECT 'analysis_tasks', count(*) FROM analysis_tasks UNION ALL SELECT 'ai_usage_logs', count(*) FROM ai_usage_logs UNION ALL SELECT 'notifications', count(*) FROM notifications UNION ALL SELECT 'application_events', count(*) FROM application_events UNION ALL SELECT 'agent_steps', count(*) FROM agent_steps UNION ALL SELECT 'growth_answer_drafts', count(*) FROM growth_answer_drafts UNION ALL SELECT 'applications', count(*) FROM applications;`;
}

// ---------------------------------------------------------------------------
// Canonical JSON + hashing (mirror of evals/seed_e2e.py
// normalized_snapshot_hash: json.dumps(sort_keys=True, ensure_ascii=False,
// separators=(",", ":"))). Used for the informative fixture snapshotSha256
// cross-check; the hard invariant is the raw-text before/after compare.
// ---------------------------------------------------------------------------
export function canonicalJson(value) {
  if (Array.isArray(value)) return value.map(canonicalJson);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonicalJson(value[k])]));
  }
  return value;
}
export function sha256Hex(text) {
  return createHash("sha256").update(String(text), "utf8").digest("hex");
}
export function canonicalSnapshotHash(snapshot) {
  return sha256Hex(JSON.stringify(canonicalJson(snapshot)));
}

// ---------------------------------------------------------------------------
// Evidence plumbing (same conventions as the private-answer-page runner)
// ---------------------------------------------------------------------------
let STAGE_DIR = null;
const results = { runId: ALLOWED_RUN_ID, runner: "private-recovery-notice-runner", startedAt: null, steps: [], artifacts: [] };
let stepCounter = 0;
let exitCode = 0;

const SCRUB = [];
function scrub(text) {
  let value = String(text);
  for (const secret of SCRUB) if (secret) value = value.split(secret).join("<redacted>");
  return value;
}
function record(step) {
  stepCounter += 1;
  const entry = { n: stepCounter, at: new Date().toISOString(), ...step };
  if (entry.detail !== undefined) entry.detail = scrub(entry.detail);
  results.steps.push(entry);
  if (entry.status === "fail") exitCode = exitCode === 0 ? 1 : exitCode;
  if (entry.status === "blocked") exitCode = exitCode === 0 ? 2 : exitCode;
  console.log(`[${entry.n}] ${step.status ?? "info"} ${step.name}${entry.detail ? " :: " + entry.detail : ""}`);
  persist();
  return entry;
}
function persist() {
  if (!STAGE_DIR) return;
  results.finishedAt = new Date().toISOString();
  fs.writeFileSync(path.join(STAGE_DIR, "results.json"), JSON.stringify(results, null, 2));
}
function saveJson(name, data) {
  const file = path.join(STAGE_DIR, `${name}.json`);
  fs.writeFileSync(file, JSON.stringify(scrubDeep(data), null, 2));
  results.artifacts.push(path.relative(ROOT, file));
  return file;
}
function scrubDeep(value) {
  if (typeof value === "string") return scrub(value);
  if (Array.isArray(value)) return value.map(scrubDeep);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v] = []) => [k, scrubDeep(v)]));
  return value;
}
async function saveShot(tab, name, fullPage = true) {
  const file = path.join(STAGE_DIR, `${String(stepCounter + 1).padStart(2, "0")}-${name}.png`);
  await tab.screenshot(file, fullPage);
  record({ name: `screenshot:${name}`, status: "evidence", detail: path.relative(ROOT, file) });
  return file;
}

// ---------------------------------------------------------------------------
// Credentials (synthetic; loaded programmatically, never printed)
// ---------------------------------------------------------------------------
function loadCredentials() {
  if (!path.resolve(CREDS_FILE).startsWith(path.resolve(BACKEND_DIR, ".tmp"))) {
    throw new Error("credential path escaped isolated root");
  }
  const raw = parseCredentialDocument(fs.readFileSync(CREDS_FILE, "utf8").replace(/^\uFEFF/, ""));
  if (raw.runId !== ALLOWED_RUN_ID) throw new Error("credential file runId mismatch");
  for (const account of Object.values(raw.accounts ?? {})) {
    if (typeof account?.password === "string" && account.password) SCRUB.push(account.password);
  }
  return raw;
}

// ---------------------------------------------------------------------------
// Read-only DB diagnostics (docker compose exec psql; SELECT only, READ ONLY
// transaction enforced server-side, database pinned to the e2e database).
// ---------------------------------------------------------------------------
function dbQuery(sql) {
  const readOnlySql = `${READ_ONLY_PREFIX} ${sql} ${READ_ONLY_SUFFIX}`;
  return new Promise((resolve, reject) => {
    const child = spawn("docker", ["compose", "exec", "-T", "postgres", "psql", "-U", "careerproof",
      "-d", DB_NAME, "-At", "-c", readOnlySql],
      { cwd: BACKEND_DIR, stdio: ["ignore", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", chunk => { out += String(chunk); });
    child.stderr.on("data", chunk => { err += String(chunk); });
    child.on("exit", code => {
      if (code !== 0) { reject(new Error(`psql exit ${code}: ${err.slice(0, 200)}`)); return; }
      resolve(out.split("\n").map(l => l.replace(/\r$/, "")).filter(l => l !== "BEGIN" && l !== "ROLLBACK" && l !== "COMMIT").join("\n").trim());
    });
    child.on("error", reject);
  });
}

function portOwners(ports) {
  return new Promise((resolve, reject) => {
    const child = spawn("netstat", ["-ano", "-p", "tcp"], { stdio: ["ignore", "pipe", "ignore"] });
    let out = "";
    child.stdout.on("data", chunk => { out += String(chunk); });
    child.on("exit", () => {
      const owners = {};
      for (const line of out.split("\n")) {
        const cols = line.trim().split(/\s+/);
        if (cols.length >= 5 && cols[3] === "LISTENING") {
          const port = Number(cols[1].split(":").pop());
          if (ports.includes(port) && !owners[port]) owners[port] = Number(cols[4]);
        }
      }
      resolve(owners);
    });
    child.on("error", reject);
  });
}

// Minimal authenticated API client for READ-ONLY preflight/target checks:
// login via the real endpoint, keep the cookie in memory only, scrub it from
// anything recorded. No write-capable method exists on this client by design.
async function apiLogin(account) {
  const response = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: account.email, password: account.password }),
  });
  if (response.status !== 200) throw new Error(`api login status ${response.status}`);
  const setCookie = response.headers.getSetCookie?.() ?? [];
  const cookie = setCookie.map(c => c.split(";")[0]).filter(c => c.startsWith("careerproof_access=")).join("; ");
  if (!cookie) throw new Error("api login returned no access cookie");
  SCRUB.push(cookie);
  const user = (await response.json())?.data?.user;
  record({ name: "api-login-read-only", status: "pass", detail: `userId=${user?.id} role=${user?.role}` });
  return {
    async getJson(pathname) {
      const r = await fetch(`${API}${pathname}`, { headers: { Cookie: cookie } });
      if (r.status !== 200) throw new Error(`GET ${pathname} -> ${r.status}`);
      return (await r.json())?.data;
    },
  };
}

// ---------------------------------------------------------------------------
// Real window minimize/restore (Win32 ShowWindow on THIS run's Chrome window).
// This is the user action "最小化窗口" from the 31号审查 audit — the page sees a
// genuine browser-driven visibilitychange, not a synthetic DOM event.
// ---------------------------------------------------------------------------
const PS_WINDOW_BODY = [
  "$sig = '[DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow); [DllImport(\"user32.dll\")] public static extern bool IsIconic(IntPtr hWnd);'",
  "Add-Type -MemberDefinition $sig -Name U41 -Namespace W32",
  "$h = (Get-Process -Id __PID__ -ErrorAction Stop).MainWindowHandle",
  "if ($h -eq [IntPtr]::Zero) { Write-Output 'NO-WINDOW'; exit }",
  "[void][W32.U41]::ShowWindow($h, __CMD__)",
  "Start-Sleep -Milliseconds 400",
  "if ([W32.U41]::IsIconic($h)) { Write-Output 'MINIMIZED' } else { Write-Output 'RESTORED' }",
].join("; ");

// pid/cmdShow are embedded into the command string (numbers produced by this
// run itself): `powershell -Command <script> arg1 arg2` does NOT bind $args.
// Exported so the static test can exercise the real pipeline against a
// throwaway window of its own.
export function psWindow(pid, cmdShow) {
  const command = PS_WINDOW_BODY.replace("__PID__", String(pid)).replace("__CMD__", String(cmdShow));
  return new Promise((resolve, reject) => {
    const child = spawn("powershell", ["-NoProfile", "-Command", command],
      { stdio: ["ignore", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", chunk => { out += String(chunk); });
    child.stderr.on("data", chunk => { err += String(chunk); });
    child.on("exit", code => {
      const state = out.trim();
      if (code !== 0 || !["MINIMIZED", "RESTORED", "NO-WINDOW"].includes(state)) {
        reject(new Error(`ShowWindow exit=${code} out=${state || "(empty)"} err=${err.slice(0, 120)}`));
        return;
      }
      resolve(state);
    });
    child.on("error", reject);
  });
}

// ---------------------------------------------------------------------------
// Chrome + CDP (raw, self-contained; headed so a real window can minimize)
// ---------------------------------------------------------------------------
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
class CdpError extends Error {}

function processFacts(pid) {
  return new Promise((resolve, reject) => {
    const child = spawn("powershell", ["-NoProfile", "-Command",
      `Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}' | Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine | ConvertTo-Json -Compress`],
      { stdio: ["ignore", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", chunk => { out += String(chunk); });
    child.stderr.on("data", chunk => { err += String(chunk); });
    child.on("exit", () => {
      try { resolve(JSON.parse(out.trim())); } catch { resolve(null); }
    });
    child.on("error", reject);
  });
}
async function processFact(pid, field) {
  const facts = await processFacts(pid);
  if (!facts || typeof facts !== "object") throw new Error("process facts unavailable");
  return Array.isArray(facts) ? (facts[0]?.[field] ?? null) : facts[field];
}

class Chrome {
  constructor({ width = 1280, height = 900, stamp } = {}) {
    if (!stamp) throw new Error("Chrome requires this run's own stamp for its isolated profile");
    this.profileDir = path.join(RUNTIME_DIR, `profile-${stamp}`);
    fs.mkdirSync(this.profileDir, { recursive: true });
    this.width = width; this.height = height;
    this.child = null; this.ws = null; this.port = null;
    this.nextId = 1; this.pending = new Map(); this.eventHandlers = [];
    this.closed = false;
  }
  async launch() {
    const portFile = path.join(this.profileDir, "DevToolsActivePort");
    if (fs.existsSync(portFile)) fs.rmSync(portFile);
    this.child = spawn(CHROME, [
      "--remote-debugging-port=0",
      `--user-data-dir=${this.profileDir}`,
      "--no-first-run", "--no-default-browser-check", "--disable-extensions",
      "--disable-sync", "--disable-gpu", "--disable-search-engine-choice-screen",
      "--remote-allow-origins=*", `--window-size=${this.width},${this.height}`, "about:blank",
    ], { stdio: "ignore", windowsHide: false });
    this.creationDate = await processFact(this.child.pid, "CreationDate").catch(() => null);
    const deadline = Date.now() + 20000;
    let lines = [];
    while (Date.now() < deadline) {
      if (fs.existsSync(portFile)) {
        lines = fs.readFileSync(portFile, "utf8").split("\n").map(s => s.trim()).filter(Boolean);
        if (lines.length >= 1) { this.port = Number(lines[0]); break; }
      }
      await sleep(200);
    }
    if (!this.port) throw new CdpError("DevToolsActivePort did not appear");
    const wsUrl = `ws://127.0.0.1:${this.port}${lines[1] ?? "/devtools/browser"}`;
    await new Promise((resolve, reject) => {
      const deadline2 = Date.now() + 10000;
      const attempt = () => {
        const ws = new WebSocket(wsUrl);
        this.ws = ws;
        ws.addEventListener("open", () => resolve());
        ws.addEventListener("error", () => { if (Date.now() > deadline2) reject(new CdpError("ws connect failed")); else setTimeout(attempt, 250); });
        ws.addEventListener("message", event => this.#onMessage(event));
        ws.addEventListener("close", () => { if (!this.closed) for (const entry of this.pending.values()) entry.reject(new CdpError("cdp closed")); });
      };
      attempt();
    });
    record({ name: "chrome-launched", status: "info", detail: `headed pid=${this.child.pid} port ${this.port}` });
    return this;
  }
  #onMessage(event) {
    let msg; try { msg = JSON.parse(String(event.data)); } catch { return; }
    if (msg.id !== undefined) {
      const entry = this.pending.get(msg.id);
      if (entry) {
        this.pending.delete(msg.id);
        if (msg.error) entry.reject(new CdpError(`${entry.method}: ${msg.error.message}`));
        else entry.resolve(msg.result);
      }
      return;
    }
    if (msg.method) this.eventHandlers.forEach(handler => handler(msg));
  }
  send(method, params = {}, sessionId = undefined, timeoutMs = 20000) {
    if (!this.ws || this.ws.readyState !== 1) throw new CdpError(`cdp not connected: ${method}`);
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new CdpError(`cdp timeout ${timeoutMs}ms: ${method}`)); }, timeoutMs);
      this.pending.set(id, { resolve: v => { clearTimeout(timer); resolve(v); }, reject: e => { clearTimeout(timer); reject(e); }, method });
      this.ws.send(JSON.stringify(payload));
    });
  }
  async openTab(url = "about:blank") {
    const { targetId } = await this.send("Target.createTarget", { url });
    const { sessionId } = await this.send("Target.attachToTarget", { targetId, flatten: true });
    return new Tab(this, sessionId, targetId);
  }
  onEvent(handler) { this.eventHandlers.push(handler); }
  async stop() {
    if (this.closed) return;
    this.closed = true;
    try { await this.send("Browser.close"); } catch { /* fall through to wait */ }
    if (this.child && this.child.exitCode === null) {
      await Promise.race([new Promise(resolve => this.child.on("exit", resolve)), sleep(3000)]);
    }
    if (this.child && this.child.exitCode === null && this.child.pid) {
      // Force-kill guard: PID + CreationDate + executable + this run's unique
      // --user-data-dir must all still match, or the kill is skipped honestly.
      const facts = await processFacts(this.child.pid).catch(() => null);
      const cmdline = String(facts?.CommandLine ?? "");
      const verified =
        facts && facts.ProcessId === this.child.pid &&
        typeof facts.CreationDate === "string" && !!this.creationDate &&
        facts.CreationDate === this.creationDate &&
        typeof facts.ExecutablePath === "string" &&
        facts.ExecutablePath.toLowerCase() === CHROME.toLowerCase() &&
        cmdline.includes(`--user-data-dir=${this.profileDir}`);
      if (!verified) {
        record({ name: "chrome-kill-skipped", status: "warn", detail: `pid=${this.child.pid} could not be re-verified as this run's own Chrome; left running` });
      } else {
        spawn("taskkill", ["/PID", String(this.child.pid), "/T", "/F"], { stdio: "ignore" });
        const deadline = Date.now() + 5000;
        while (this.child.exitCode === null && Date.now() < deadline) await sleep(200);
      }
    }
    record({ name: "chrome-stopped", status: "info", detail: `exitCode=${this.child?.exitCode ?? "n/a"}` });
  }
}

class Tab {
  constructor(browser, sessionId, targetId) {
    this.browser = browser; this.sessionId = sessionId; this.targetId = targetId;
    this.networkLog = [];
    this.draftCapture = []; // /answer-draft requests (method/url/status/bodies)
    const pendingBodies = new Map();
    browser.onEvent(msg => {
      if (msg.sessionId !== this.sessionId) return;
      const p = msg.params ?? {};
      if (msg.method === "Network.requestWillBeSent") {
        this.networkLog.push({ at: new Date().toISOString(), phase: "request", method: p.request.method, url: this.#shortUrl(p.request.url) });
        if (/\/answer-draft/.test(p.request.url) && !/\/references/.test(p.request.url)) {
          const entry = { at: new Date().toISOString(), method: p.request.method, url: this.#shortUrl(p.request.url), requestBody: p.request.postData ?? null, status: null, responseBody: null };
          this.draftCapture.push(entry);
          pendingBodies.set(p.requestId, entry);
        }
      } else if (msg.method === "Network.responseReceived") {
        this.networkLog.push({ at: new Date().toISOString(), phase: "response", url: this.#shortUrl(p.response.url), status: p.response.status });
        const entry = pendingBodies.get(p.requestId);
        if (entry) entry.status = p.response.status;
      } else if (msg.method === "Network.loadingFinished") {
        const entry = pendingBodies.get(p.requestId);
        if (entry && entry.status !== null && entry.responseBody === null) {
          this.send("Network.getResponseBody", { requestId: p.requestId })
            .then(body => { entry.responseBody = body?.body ? Buffer.from(body.body, body.base64 ? "base64" : "utf8").toString("utf8") : null; })
            .catch(() => { entry.responseBody = "(unavailable)"; });
        }
      }
    });
  }
  #shortUrl(url) { return url.replace(/^https?:\/\/127\.0\.0\.1:[0-9]+/, ""); }
  send(method, params) { return this.browser.send(method, params, this.sessionId); }
  async enable() {
    await this.send("Page.enable");
    await this.send("Network.enable");
    await this.send("Runtime.enable");
  }
  // Real transport-level offline condition imposed by the browser (used only
  // for the recovery read-failure step; clearly recorded, and if it cannot be
  // observed the step is reported as unverified instead of faked).
  async setOffline(offline) {
    await this.send("Network.emulateNetworkConditions", {
      offline, latency: 0, downloadThroughput: 0, uploadThroughput: 0,
    });
  }
  async goto(url, timeoutMs = 30000) {
    const loaded = this.waitForEvent("Page.loadEventFired", timeoutMs).catch(() => null);
    await this.send("Page.navigate", { url });
    await loaded;
    await this.evalJs("document.readyState").catch(() => "loading");
    return this;
  }
  waitForEvent(method, timeoutMs) {
    return new Promise((resolve, reject) => {
      const handler = msg => {
        if (msg.sessionId === this.sessionId && msg.method === method) { cleanup(); resolve(msg.params); }
      };
      const timer = setTimeout(() => { cleanup(); reject(new CdpError(`event timeout ${timeoutMs}ms: ${method}`)); }, timeoutMs);
      const cleanup = () => { clearTimeout(timer); this.browser.eventHandlers = this.browser.eventHandlers.filter(h => h !== handler); };
      this.browser.onEvent(handler);
    });
  }
  async evalJs(expression, options = {}) {
    try { return await this.#evalOnce(expression, options); }
    catch (error) {
      if (!/cdp timeout/.test(String(error?.message))) throw error;
      await sleep(1000);
      return this.#evalOnce(expression, options);
    }
  }
  async #evalOnce(expression, { timeoutMs = 15000, awaitPromise = false } = {}) {
    const result = await this.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise, userGesture: true, timeout: timeoutMs }, undefined, timeoutMs + 6000);
    if (result.exceptionDetails) {
      throw new CdpError(`evaluate failed: ${String(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text).slice(0, 300)}`);
    }
    return result.result?.value;
  }
  async waitFor(pageExpression, { timeoutMs = 20000, pollMs = 200, label = "condition" } = {}) {
    const wrapped = `(async () => {
      const t0 = Date.now();
      while (Date.now() - t0 < ${timeoutMs}) {
        try { const v = Boolean(eval((${JSON.stringify(pageExpression)}))()); if (v) return { ok: true }; } catch {}
        await new Promise(r => setTimeout(r, ${pollMs}));
      }
      return { ok: false };
    })()`;
    const outcome = await this.evalJs(wrapped, { timeoutMs: timeoutMs + 8000, awaitPromise: true });
    if (!outcome?.ok) throw new CdpError(`waitFor timeout ${timeoutMs}ms: ${label}`);
    return true;
  }
  async installFinder() {
    await this.evalJs(`(() => {
      window.__e2eFind = (opts) => {
        const { tag, text, exact, attr, attrValue } = opts;
        const wanted = (text ?? "").trim();
        const nodes = Array.from(document.querySelectorAll(tag ?? "button,a,h1,h2,h3,h4,p,li,label,span,select,option,input,textarea,summary,article,section"));
        const matches = [];
        for (const el of nodes) {
          const style = getComputedStyle(el);
          if (style.display === "none" || style.visibility === "hidden") continue;
          const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(" ").trim();
          const full = (el.textContent ?? "").trim();
          const hay = [own, full, el.getAttribute("aria-label") ?? "", el.getAttribute("placeholder") ?? ""];
          let hit = !wanted;
          for (const candidate of hay) { if (exact ? candidate === wanted : candidate.includes(wanted)) { hit = true; break; } }
          if (attr && el.getAttribute(attr) !== (attrValue ?? true)) hit = false;
          if (!hit) continue;
          const rect = el.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) continue;
          matches.push({ tag: el.tagName.toLowerCase(), text: full.slice(0, 140), x: Math.round(rect.x + rect.width / 2), y: Math.round(rect.y + rect.height / 2), top: Math.round(rect.top), h: Math.round(rect.height), disabled: el.disabled === true });
          if (matches.length > 40) break;
        }
        return matches;
      };
      window.__e2eScrollTo = (x, y) => window.scrollTo({ top: y, behavior: "instant" });
      return true;
    })()`);
  }
  async find(opts) { return this.evalJs(`window.__e2eFind(${JSON.stringify(opts)})`); }
  async findUnique(opts, label) {
    const matches = await this.find(opts);
    if (matches.length !== 1) throw new CdpError(`findUnique(${label ?? opts.text ?? ""}): ${matches.length} matches: ${JSON.stringify(matches.slice(0, 3))}`);
    return matches[0];
  }
  async recentreAndFind(el) {
    const scrollY = await this.evalJs("Math.round(window.scrollY)");
    await this.evalJs(`window.__e2eScrollTo(0, ${Math.max(0, scrollY + el.top - Math.floor(this.browser.height / 2))})`);
    await sleep(180);
    const matches = await this.find(el.text ? { tag: el.tag, text: el.text } : { tag: el.tag });
    let best = el, bestDelta = Infinity;
    for (const match of matches || []) {
      const delta = Math.abs(match.x - el.x) + Math.abs(match.h - el.h);
      if (delta < bestDelta) { best = match; bestDelta = delta; }
    }
    return best;
  }
  async click(optsOrEl, { label } = {}) {
    const el = optsOrEl.x !== undefined ? optsOrEl : await this.findUnique(optsOrEl, label);
    const target = await this.recentreAndFind(el);
    for (const type of ["mousePressed", "mouseReleased"]) {
      await this.send("Input.dispatchMouseEvent", { type, x: target.x, y: target.y, button: "left", clickCount: 1, buttons: type === "mousePressed" ? 1 : 0 });
    }
    await sleep(180);
    return target;
  }
  async fillText(opts, text, { label, expectValue } = {}) {
    const el = await this.click(opts, { label });
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
    await this.send("Input.insertText", { text });
    await sleep(150);
    if (expectValue !== undefined) {
      const got = await this.evalJs(`(document.activeElement?.value ?? "").trim()`);
      if (got !== expectValue) throw new CdpError(`fillText mismatch: label=${label ?? "?"} expectedLength=${expectValue.length} gotLength=${String(got).length}`);
    }
    return el;
  }
  async screenshot(filePath, fullPage = true) {
    const params = { format: "png" };
    if (fullPage) {
      const metrics = await this.send("Page.getLayoutMetrics");
      const content = metrics.cssContentSize ?? metrics.contentSize;
      if (content && content.height > 0) params.clip = { x: 0, y: 0, width: Math.min(content.width, 2000), height: Math.min(content.height, 14000), scale: 1 };
    }
    const { data } = await this.send("Page.captureScreenshot", params);
    fs.writeFileSync(filePath, Buffer.from(data, "base64"));
    return filePath;
  }
  // Panel state snapshot: the whole evidence unit for the notice lifecycle.
  async panelState() {
    return this.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return null;
      const savedLine = Array.from(section.querySelectorAll('p')).map(p => p.textContent.trim()).find(t => t.startsWith('已保存：') || t.startsWith('尚未保存过草稿')) ?? null;
      const textarea = section.querySelector('#private-answer-text');
      const alerts = Array.from(section.querySelectorAll('[role=alert]')).map(e => e.textContent.trim()).filter(Boolean);
      const statuses = Array.from(section.querySelectorAll('[role=status]')).map(e => e.textContent.trim()).filter(Boolean);
      const visibleTexts = [...alerts, ...statuses];
      return {
        path: location.pathname, visibility: document.visibilityState,
        constantWarningPresent: Array.from(section.querySelectorAll('p')).some(p => p.textContent.includes(${JSON.stringify(CONSTANT_WARNING_PREFIX)})),
        savedLine, text: textarea ? textarea.value : null, disabled: textarea ? textarea.disabled : null,
        alerts, statuses,
        discardAlertVisible: alerts.some(t => t === ${JSON.stringify(DISCARD_NOTICE)}),
        cleanNoticeVisible: visibleTexts.some(t => t === ${JSON.stringify(CLEAN_NOTICE)}),
        discardTextVisible: visibleTexts.some(t => t === ${JSON.stringify(DISCARD_NOTICE)}),
        reading: statuses.some(t => t.includes('正在读取已保存草稿')),
        anyDiscardWording: visibleTexts.some(t => t.includes('已丢弃')),
      };
    })()`);
  }
  async overflowMetrics() {
    return this.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return {
        innerWidth: window.innerWidth, innerHeight: window.innerHeight,
        docNoHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
        sectionNoHorizontalOverflow: !!section && section.scrollWidth <= section.clientWidth,
        longReferenceLabelsContained: !!section && Array.from(section.querySelectorAll('fieldset li label')).every(l => l.scrollWidth <= l.clientWidth + 1),
        docScrollWidth: document.documentElement.scrollWidth,
        sectionScrollWidth: section ? section.scrollWidth : null,
        sectionClientWidth: section ? section.clientWidth : null,
      };
    })()`);
  }
  async leakScan(markers) {
    return this.evalJs(`(() => {
      const dumpStorage = (storage) => Array.from({ length: storage.length }, (_, i) => {
        const k = storage.key(i);
        return k + "=" + String(storage.getItem(k));
      }).join("\\n");
      const needles = ${JSON.stringify(markers)};
      const texts = [document.body.innerText];
      for (const el of document.querySelectorAll('textarea, input')) texts.push(el.value ?? "");
      texts.push(dumpStorage(window.localStorage), dumpStorage(window.sessionStorage), document.cookie);
      const joined = texts.join("\\n||\\n");
      return {
        found: needles.filter(n => joined.includes(n)),
        localStorageEntries: window.localStorage.length,
        sessionStorageEntries: window.sessionStorage.length,
        localStorageDump: dumpStorage(window.localStorage).slice(0, 400),
        sessionStorageDump: dumpStorage(window.sessionStorage).slice(0, 400),
      };
    })()`);
  }
  async setViewport(width, height) {
    await this.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 2, mobile: width <= 500 });
    await sleep(300);
  }
}

// ---------------------------------------------------------------------------
// Shared UI flows
// ---------------------------------------------------------------------------
async function login(tab, account) {
  await tab.goto(`${FRONTEND}/login`);
  await tab.installFinder();
  await tab.waitFor(`() => document.querySelector('input[type=email]') && document.querySelector('input[type=password]')`, { label: "login form" });
  await tab.fillText({ tag: "input[type=email]" }, account.email, { label: "email", expectValue: account.email });
  await tab.fillText({ tag: "input[type=password]" }, account.password, { label: "password", expectValue: account.password });
  await tab.click({ tag: "button[type=submit]" }, { label: "login submit" });
  await tab.waitFor(`() => !location.pathname.startsWith("/login")`, { timeoutMs: 20000, label: "redirect after login" });
  await sleep(800);
  await tab.installFinder();
  record({ name: "login-ok", status: "pass", detail: await tab.evalJs("location.pathname") });
}

async function openDraftPage(tab, taskId) {
  await tab.goto(`${FRONTEND}/growth/${taskId}`);
  await tab.installFinder();
  await tab.waitFor(`() => Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿'))`, { timeoutMs: 30000, label: "private answer draft section" });
  await tab.waitFor(`() => !document.querySelector('#private-answer-text')?.disabled`, { timeoutMs: 15000, label: "draft textarea enabled (reading done)" });
}

const TEXTAREA = { tag: "textarea", attr: "id", attrValue: "private-answer-text" };

// Node-side panel polling (unaffected by hidden-page timer throttling).
async function pollPanel(tab, predicate, { timeoutMs = 10000, pollMs = 25 } = {}) {
  const t0 = Date.now();
  const seen = [];
  while (Date.now() - t0 < timeoutMs) {
    const state = await tab.panelState().catch(() => null);
    if (state) {
      seen.push(state);
      if (predicate(state)) return { matched: true, state, seen };
    }
    await sleep(pollMs);
  }
  return { matched: false, state: seen[seen.length - 1] ?? null, seen };
}

// Real minimize: Win32 ShowWindow + page-reported visibilityState=hidden.
// Returns false when the OS state could not be verified — callers must record
// blocked instead of faking a hide.
async function realHide(tab, pid) {
  const osState = await psWindow(pid, 6 /* SW_MINIMIZE */);
  if (osState !== "MINIMIZED") return { ok: false, reason: `ShowWindow state=${osState}` };
  const page = await pollPanel(tab, state => state.visibility === "hidden", { timeoutMs: 8000, pollMs: 50 });
  if (!page.matched) return { ok: false, reason: `page visibilityState=${page.state?.visibility ?? "?"} after OS minimize` };
  return { ok: true, hiddenState: page.state, seen: page.seen };
}

async function realRestore(tab, pid) {
  const osState = await psWindow(pid, 9 /* SW_RESTORE */);
  if (osState !== "RESTORED") return { ok: false, reason: `ShowWindow state=${osState}` };
  const page = await pollPanel(tab, state => state.visibility === "visible", { timeoutMs: 8000, pollMs: 50 });
  if (!page.matched) return { ok: false, reason: `page visibilityState=${page.state?.visibility ?? "?"} after OS restore` };
  return { ok: true, visibleState: page.state, seen: page.seen };
}

class PageAbortError extends Error {}

// Guard before every step that types or clicks: the page must REALLY be
// visible, or the remaining page steps abort honestly (no input into a
// minimized window, no faked visibility).
async function ensureVisible(tab, pid, label) {
  const cur = await tab.panelState().catch(() => null);
  if (cur && cur.visibility === "visible") return cur;
  record({ name: `ensure-visible:${label}`, status: "info", detail: `page not visible (${cur?.visibility ?? "unknown"}); restoring the real window before continuing` });
  const restored = await realRestore(tab, pid);
  if (!restored.ok) throw new PageAbortError(`could not restore the real window before ${label}: ${restored.reason}`);
  return restored.visibleState;
}

// ---------------------------------------------------------------------------
// Read-only invariants (draft row / three deliveries / sent reply / counts)
// ---------------------------------------------------------------------------
async function captureInvariants(label, taskId, fixture) {
  const at = new Date().toISOString();
  const draftRaw = await dbQuery(draftRowSql(taskId));
  const draftRows = JSON.parse(draftRaw);
  const appRaw = await dbQuery(applicationRowsSql(Object.values(fixture.applications).map(a => a.id)));
  const appRows = JSON.parse(appRaw);
  const countsRaw = await dbQuery(countRowsSql());
  const counts = Object.fromEntries(countsRaw.split("\n").filter(Boolean).map(line => {
    const [name, value] = line.split("|");
    return [name, Number(value)];
  }));
  const apps = appRows.map(row => {
    const slot = Object.entries(fixture.applications).find(([, v]) => v.id === row.id)?.[0] ?? "?";
    return {
      slot, id: row.id, status: row.status, version: row.version,
      rowSha256: sha256Hex(JSON.stringify(row)),
      // Informative only: the seeder's normalized_snapshot_hash cannot be
      // replicated byte-exactly in JS (Python floats like 55.0 survive the DB
      // text but collapse to 55 in JS numbers). The frozen-snapshot guarantee
      // itself is enforced by the raw before/after equality below and by the
      // seeder's own --verify-only run; this field only documents drift if a
      // re-run ever disagrees with itself.
      fixtureSnapshotSha256: fixture.applications[slot]?.snapshotSha256 ?? null,
      canonicalSnapshotSha256: row.report_snapshot === null ? null : canonicalSnapshotHash(row.report_snapshot),
      replyKind: row.reply_kind ?? null,
      replyTextSha256: row.reply_text ? sha256Hex(row.reply_text) : null,
    };
  });
  const snapshot = {
    label, at,
    appsRawSha256: sha256Hex(appRaw),
    draftRawSha256: sha256Hex(draftRaw),
    draftRows: draftRows.map(row => ({ ...row, textSha256: sha256Hex(row.text ?? ""), textLength: (row.text ?? "").length, referenceCount: Array.isArray(row.references) ? row.references.length : null })),
    apps, counts,
  };
  saveJson(`invariants-${label}`, snapshot);
  return snapshot;
}

function compareInvariants(baseline, after, markers) {
  const checks = [];
  checks.push(["draft-rows-unchanged", JSON.stringify(baseline.draftRows) === JSON.stringify(after.draftRows),
    `before=${JSON.stringify(baseline.draftRows)} after=${JSON.stringify(after.draftRows)}`]);
  checks.push(["draft-marker-never-saved",
    after.draftRows.every(row => markers.every(m => !(row.textSha256 === sha256Hex(m)))),
    "no draft row text digest equals a marker digest"]);
  const beforeById = new Map(baseline.apps.map(a => [a.id, a]));
  for (const app of after.apps) {
    const before = beforeById.get(app.id);
    checks.push([`delivery-${app.slot}-row-unchanged`, !!before && before.rowSha256 === app.rowSha256,
      `before=${before?.rowSha256 ?? "missing"} after=${app.rowSha256}`]);
  }
  checks.push(["deliveries-raw-text-unchanged", baseline.appsRawSha256 === after.appsRawSha256,
    `before=${baseline.appsRawSha256} after=${after.appsRawSha256}`]);
  checks.push(["draft-raw-text-unchanged", baseline.draftRawSha256 === after.draftRawSha256,
    `before=${baseline.draftRawSha256} after=${after.draftRawSha256}`]);
  checks.push(["sent-reply-digest-unchanged",
    JSON.stringify(baseline.apps.map(a => a.replyTextSha256)) === JSON.stringify(after.apps.map(a => a.replyTextSha256)) &&
    after.apps.some(a => a.replyTextSha256 !== null),
    `before=${JSON.stringify(baseline.apps.map(a => a.replyTextSha256))} after=${JSON.stringify(after.apps.map(a => a.replyTextSha256))}`]);
  checks.push(["row-counts-unchanged", JSON.stringify(baseline.counts) === JSON.stringify(after.counts),
    `before=${JSON.stringify(baseline.counts)} after=${JSON.stringify(after.counts)}`]);
  return checks;
}

// ---------------------------------------------------------------------------
// Main flow
// ---------------------------------------------------------------------------
async function main() {
  const RUN_STAMP_LOCAL = new Date().toISOString().replace(/[:.]/g, "-");
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  STAGE_DIR = path.join(EVIDENCE_DIR, `page-run-${RUN_STAMP_LOCAL}`);
  fs.mkdirSync(STAGE_DIR, { recursive: true });
  results.startedAt = new Date().toISOString();
  record({ name: "runner-start", status: "info", detail: `pinned run=${ALLOWED_RUN_ID} frontend=${FRONTEND} backend=${BACKEND} db=${DB_NAME} (read-only)` });

  const CREDS = loadCredentials();
  try {
    const manifest = parseCredentialDocument(fs.readFileSync(MANIFEST_FILE, "utf8"));
    record({ name: "manifest", status: "info", detail: `db=${manifest.databaseName} provider=${manifest.aiProvider} external=${manifest.aiExternalEnabled} frontendStage=${manifest.frontendStage ?? "?"} distDir=${manifest.distDir ?? "?"}` });
    if (manifest.databaseName && manifest.databaseName !== DB_NAME) {
      record({ name: "manifest-db-mismatch", status: "fail", detail: `manifest db=${manifest.databaseName} expected=${DB_NAME}` });
    }
  } catch (error) {
    record({ name: "manifest", status: "warn", detail: `manifest not readable at run time (${String(error?.message ?? error).slice(0, 120)}); DB identity is decided by the read-only cross-check below` });
  }

  // Preflight: services healthy on the pinned ports only.
  const feHealth = await fetch(`${FRONTEND}/login`, { redirect: "manual" }).then(r => r.status).catch(() => null);
  record({ name: "frontend-health", status: feHealth === 200 ? "pass" : "blocked", detail: `GET ${FRONTEND}/login -> ${feHealth}` });
  const beHealth = await fetch(`${API}/health`).then(async r => ({ status: r.status, body: (await r.text()).slice(0, 120) })).catch(e => ({ status: null, body: String(e.message).slice(0, 120) }));
  record({ name: "backend-health", status: beHealth.status === 200 ? "pass" : "blocked", detail: `GET ${API}/health -> ${beHealth.status} ${scrub(beHealth.body)}` });
  if (feHealth !== 200 || beHealth.status !== 200) throw new Error("services not ready on 127.0.0.1:3001/8001 — waiting for Codex go-ahead, nothing was executed against the page");

  const owners = await portOwners([3001, 8001]);
  record({ name: "port-owners", status: "info", detail: JSON.stringify(owners) });
  if (!owners[3001] || !owners[8001]) throw new Error("pinned ports not both LISTENING; refusing to continue");

  const auth = await apiLogin(CREDS.accounts.student);
  const taskPage = await auth.getJson("/growth-tasks?page=1&pageSize=20");
  const tasks = taskPage.items;
  if (!Array.isArray(tasks) || tasks.length === 0) throw new Error("no own growth task visible through the read-only API");
  const target = tasks[0];
  const draftPreflight = await auth.getJson(`/growth-tasks/${target.id}/answer-draft`).catch(() => "ERROR");
  record({ name: "target-task", status: "info", detail: `taskId=${target.id} title=${target.requirementTitle} preflightDraft=${draftPreflight === "ERROR" ? "read-error" : draftPreflight === null ? "none" : `rev=${draftPreflight.revision}`}` });
  const dbTaskIds = (await dbQuery(`SELECT id::text FROM evidence_growth_tasks WHERE created_by = '${CREDS.accounts.student.userId}' ORDER BY created_at;`)).split("\n").filter(Boolean);
  const dbIdentityOk = dbTaskIds.includes(target.id);
  record({ name: "backend-db-identity", status: dbIdentityOk ? "pass" : "blocked", detail: `api own tasks=${tasks.length} db own tasks=${dbTaskIds.length} targetInDb=${dbIdentityOk}` });
  if (!dbIdentityOk) throw new Error("backend on 8001 does not serve the e2e database for this run");

  // Read-only invariant snapshot BEFORE any page action.
  const markers = [];
  const before = await captureInvariants("before", target.id, CREDS);
  record({ name: "invariants-before", status: "pass", detail: `deliveries=${before.apps.length} draftRows=${before.draftRows.length} counts=${JSON.stringify(before.counts)}` });

  let baseline = null;
  const browser = new Chrome({ stamp: RUN_STAMP_LOCAL });
  let tab = null;
  try {
    await browser.launch();
    tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);
    await openDraftPage(tab, target.id);
    await sleep(600);

    const initialGets = tab.draftCapture.filter(e => e.method === "GET");
    const initialDraft = initialGets.length ? captureData(initialGets[initialGets.length - 1]) : "NOT-CAPTURED";
    record({ name: "draft-initial-get", status: initialGets.length && initialGets[initialGets.length - 1].status === 200 ? "pass" : "fail", detail: `GET status=${initialGets[initialGets.length - 1]?.status} hasDraft=${initialDraft === null ? "none" : initialDraft === "NOT-CAPTURED" ? "not-captured" : `rev=${initialDraft.revision}`}` });

    let state = await tab.panelState();
    record({ name: "panel-initial", status: "info", detail: JSON.stringify(state) });
    await saveShot(tab, "panel-initial");

    // Precondition: the e2e database has no saved draft (verified read-only in
    // invariants-before). Establish one through the REAL UI save — never the
    // marker, never the API.
    let seedText;
    if (before.draftRows.length === 0) {
      await ensureVisible(tab, browser.child.pid, "precondition seed");
      seedText = buildSeedText(new Date().toISOString());
      await tab.fillText(TEXTAREA, seedText, { label: "seed text", expectValue: seedText });
      const mark = tab.draftCapture.length;
      await tab.click({ tag: "button", text: "保存草稿", exact: true }, { label: "save precondition seed" });
      await tab.waitFor(`() => (() => {
        const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
        if (!section) return false;
        const p = Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()).find(t => t.startsWith('已保存：'));
        return !!p && p.includes('与已保存内容一致');
      })()`, { timeoutMs: 20000, label: "seed save receipt" });
      await sleep(600);
      const puts = tab.draftCapture.slice(mark).filter(e => e.method === "PUT");
      const receipt = puts.length ? captureData(puts[0]) : null;
      record({ name: "precondition-seed-ui-save", status: puts.length === 1 && puts[0].status === 200 && receipt?.revision === 1 ? "pass" : "fail", detail: `PUT status=${puts[0]?.status} revision=${receipt?.revision} seedLength=${seedText.length} (seed, not marker)` });
      if (puts.length !== 1 || puts[0].status !== 200 || receipt?.revision !== 1) throw new Error("precondition seed save via UI failed");
      state = await tab.panelState();
      record({ name: "panel-after-seed", status: "info", detail: JSON.stringify({ savedLine: state.savedLine, textLength: state.text?.length }) });
      await saveShot(tab, "panel-after-seed");
    } else {
      seedText = before.draftRows[0].text;
      record({ name: "precondition-existing-draft", status: "info", detail: `server draft already present rev=${before.draftRows[0].revision} length=${before.draftRows[0].textLength}; used as the original draft` });
    }

    // Baseline AFTER the precondition — the "original draft" for the final
    // read-only compare.
    baseline = await captureInvariants("after-seed", target.id, CREDS);
    record({ name: "invariants-after-seed", status: "pass", detail: `draftRev=${baseline.draftRows[0]?.revision} draftTextSha256=${baseline.draftRows[0]?.textSha256}` });

    // Step 1 — 读取已保存草稿: the textarea must show the server version.
    state = await tab.panelState();
    record({
      name: "step1-read-saved-draft", status: state.text === seedText && state.constantWarningPresent ? "pass" : "fail",
      detail: `textMatchesServer=${state.text === seedText} savedLine=${state.savedLine} constantWarning=${state.constantWarningPresent}`,
    });

    // Step 2 — 未编辑隐藏再恢复：must NOT claim a discard.
    let hide = await realHide(tab, browser.child.pid);
    if (!hide.ok) {
      record({ name: "step2-real-hide", status: "blocked", detail: `could not truly minimize (${hide.reason}); not faking visibility — hide/restore steps unverified` });
    } else {
      record({ name: "step2-real-hide", status: "pass", detail: `OS minimized + page visibilityState=hidden; midHidden=${JSON.stringify(hide.hiddenState)}` });
      const mid = hide.hiddenState;
      record({
        name: "step2-mid-hidden-clean", status: mid.text === "" && mid.cleanNoticeVisible && !mid.anyDiscardWording ? "pass" : "fail",
        detail: `textCleared=${mid.text === ""} cleanNotice=${mid.cleanNoticeVisible} noFalseDiscard=${!mid.anyDiscardWording}`,
      });
      const restore = await realRestore(tab, browser.child.pid);
      if (!restore.ok) {
        record({ name: "step2-restore", status: "blocked", detail: `could not restore (${restore.reason})` });
      } else {
        const done = await pollPanel(tab, s => s.visibility === "visible" && !s.disabled && s.text === seedText, { timeoutMs: 20000 });
        const end = done.state;
        record({
          name: "step2-restored-no-false-discard", status: end && end.text === seedText && !end.anyDiscardWording ? "pass" : "fail",
          detail: `textRestored=${end?.text === seedText} noDiscardClaim=${!end?.anyDiscardWording} savedLine=${end?.savedLine}`,
        });
        await saveShot(tab, "step2-restored");
      }
    }

    // Step 3 — 输入合成marker后真实隐藏/恢复：文字恢复服务器版本，丢弃提示保持。
    await ensureVisible(tab, browser.child.pid, "step3 marker typing");
    const marker1 = buildMarker(new Date().toISOString());
    markers.push(marker1);
    await tab.fillText(TEXTAREA, marker1, { label: "synthetic marker", expectValue: marker1 });
    state = await tab.panelState();
    record({
      name: "step3-marker-typed", status: state.text === marker1 && (state.savedLine ?? "").includes("有未保存修改") ? "pass" : "fail",
      detail: `markerTyped=${state.text === marker1} dirtyLine=${(state.savedLine ?? "").includes("有未保存修改")} (marker never saved)`,
    });
    await saveShot(tab, "step3-marker-before-hide");

    hide = await realHide(tab, browser.child.pid);
    if (!hide.ok) {
      record({ name: "step3-real-hide", status: "blocked", detail: `could not truly minimize (${hide.reason}); not faking visibility` });
    } else {
      const mid = hide.hiddenState;
      record({
        name: "step3-mid-hidden-discard", status: mid.text === "" && mid.discardTextVisible && mid.visibility === "hidden" ? "pass" : "fail",
        detail: `textCleared=${mid.text === ""} fixedDiscardText=${mid.discardTextVisible}`,
      });
      const restore = await realRestore(tab, browser.child.pid);
      if (!restore.ok) {
        record({ name: "step3-restore", status: "blocked", detail: `could not restore (${restore.reason})` });
      } else {
        // 读取期间：the discard notice must already be visible while the
        // recovery load is in flight (polling is best-effort; if the load is
        // faster than one poll this is recorded honestly, the hard gate is
        // the after-success visibility).
        const readingObserved = await pollPanel(tab, s => s.reading && s.discardAlertVisible, { timeoutMs: 4000, pollMs: 20 });
        record({
          name: "step3-during-reading-notice", status: readingObserved.matched ? "pass" : "info",
          detail: readingObserved.matched ? "discard alert visible while 正在读取已保存草稿 was on screen" : "recovery load finished faster than one poll; during-reading visibility not observed (best-effort, not faked)",
        });
        const done = await pollPanel(tab, s => s.visibility === "visible" && !s.disabled && s.text === seedText, { timeoutMs: 20000 });
        const end = done.state;
        record({
          name: "step3-restored-server-version", status: end && end.text === seedText && end.discardAlertVisible ? "pass" : "fail",
          detail: `textRestored=${end?.text === seedText} discardAlertStillVisible=${end?.discardAlertVisible} savedLine=${end?.savedLine}`,
        });
        await saveShot(tab, "step3-restored-discard-notice");
      }
    }

    // Step 4 — 重复隐藏保持提示（恢复后状态干净，第二次clear不得抹去既有提示）。
    hide = await realHide(tab, browser.child.pid);
    if (!hide.ok) {
      record({ name: "step4-real-hide", status: "blocked", detail: `could not truly minimize (${hide.reason})` });
    } else {
      const mid = hide.hiddenState;
      record({
        name: "step4-mid-hidden-carried", status: mid.cleanNoticeVisible && mid.discardAlertVisible ? "pass" : "fail",
        detail: `cleanStatusNotice=${mid.cleanNoticeVisible} carriedDiscardAlert=${mid.discardAlertVisible} (38号审查: second clear keeps the live lossNotice)`,
      });
      const restore = await realRestore(tab, browser.child.pid);
      if (!restore.ok) {
        record({ name: "step4-restore", status: "blocked", detail: `could not restore (${restore.reason})` });
      } else {
        const done = await pollPanel(tab, s => s.visibility === "visible" && !s.disabled && s.text === seedText, { timeoutMs: 20000 });
        const end = done.state;
        record({
          name: "step4-restored-notice-kept", status: end && end.text === seedText && end.discardAlertVisible ? "pass" : "fail",
          detail: `noticeKeptAfterSecondCycle=${end?.discardAlertVisible} textRestored=${end?.text === seedText}`,
        });
        await saveShot(tab, "step4-restored-notice-kept");
      }
    }

    // Step 5 — 重新编辑后提示结束；随后重读恢复服务器版本。
    await ensureVisible(tab, browser.child.pid, "step5 re-edit");
    await tab.fillText(TEXTAREA, "E", { label: "re-edit neutral char", expectValue: "E" });
    state = await tab.panelState();
    record({
      name: "step5-reedit-ends-notice", status: !state.anyDiscardWording && state.text === "E" ? "pass" : "fail",
      detail: `discardGone=${!state.anyDiscardWording} text="E"`,
    });
    await tab.click({ tag: "button", text: "重读已保存草稿", exact: true }, { label: "re-read saved draft" });
    const reread = await pollPanel(tab, s => !s.disabled && s.text === seedText, { timeoutMs: 20000 });
    record({
      name: "step5-reread-restores-server", status: reread.matched && !reread.state.anyDiscardWording ? "pass" : "fail",
      detail: `textRestored=${reread.state?.text === seedText} discardGone=${!reread.state?.anyDiscardWording}`,
    });

    // Step 6 — 恢复读取失败路径（浏览器级真实断网；无法观察则如实记为未验）。
    await ensureVisible(tab, browser.child.pid, "step6 failure path");
    const marker2 = buildMarker(new Date().toISOString());
    markers.push(marker2);
    await tab.fillText(TEXTAREA, marker2, { label: "synthetic marker (failure path)", expectValue: marker2 });
    hide = await realHide(tab, browser.child.pid);
    if (!hide.ok) {
      record({ name: "step6-real-hide", status: "blocked", detail: `could not truly minimize (${hide.reason})` });
    } else {
      await tab.setOffline(true);
      record({ name: "step6-offline-enabled", status: "info", detail: "browser-level network offline (real transport failure, clearly recorded)" });
      const restore = await realRestore(tab, browser.child.pid);
      if (!restore.ok) {
        record({ name: "step6-restore", status: "blocked", detail: `could not restore (${restore.reason})` });
        await tab.setOffline(false).catch(() => {});
      } else {
        const failed = await pollPanel(tab, s => !s.reading && !s.disabled && s.text === "" && s.alerts.length > 0, { timeoutMs: 20000 });
        if (!failed.matched) {
          record({ name: "step6-recovery-read-failure", status: "blocked", detail: "offline recovery read failure not observed within timeout — recorded as UNVERIFIED, not faked" });
        } else {
          const end = failed.state;
          record({
            name: "step6-recovery-read-failure", status: end.discardAlertVisible && end.text === "" ? "pass" : "fail",
            detail: `errorShown=${end.alerts.length > 0} discardAlertStillVisible=${end.discardAlertVisible} textCleared=${end.text === ""} alerts=${JSON.stringify(end.alerts).slice(0, 200)}`,
          });
          await saveShot(tab, "step6-read-failure");
        }
        await tab.setOffline(false);
        record({ name: "step6-offline-disabled", status: "info", detail: "network back online" });
        await tab.click({ tag: "button", text: "重读已保存草稿", exact: true }, { label: "re-read after failure" });
        const recovered = await pollPanel(tab, s => !s.disabled && s.text === seedText, { timeoutMs: 20000 });
        record({
          name: "step6-success-after-failure", status: recovered.matched && recovered.state.discardAlertVisible ? "pass" : "fail",
          detail: `textRestored=${recovered.state?.text === seedText} discardAlertStillVisible=${recovered.state?.discardAlertVisible}`,
        });
        await saveShot(tab, "step6-success-after-failure");
      }
    }

    // Step 7 — 严格390px关键路径：真实隐藏/恢复 + 横向溢出 + marker不泄露。
    await ensureVisible(tab, browser.child.pid, "step7 390px path");
    const marker3 = buildMarker(new Date().toISOString());
    markers.push(marker3);
    await tab.setViewport(390, 844);
    await tab.installFinder();
    await tab.fillText(TEXTAREA, marker3, { label: "synthetic marker (390px)", expectValue: marker3 });
    state = await tab.panelState();
    record({
      name: "step7-390-marker-typed", status: state.text === marker3 && (state.savedLine ?? "").includes("有未保存修改") ? "pass" : "fail",
      detail: `viewport390 markerTyped=${state.text === marker3} dirtyLine=${(state.savedLine ?? "").includes("有未保存修改")}`,
    });
    hide = await realHide(tab, browser.child.pid);
    if (!hide.ok) {
      record({ name: "step7-real-hide", status: "blocked", detail: `could not truly minimize (${hide.reason})` });
    } else {
      const restore = await realRestore(tab, browser.child.pid);
      if (!restore.ok) {
        record({ name: "step7-restore", status: "blocked", detail: `could not restore (${restore.reason})` });
      } else {
        const done = await pollPanel(tab, s => s.visibility === "visible" && !s.disabled && s.text === seedText, { timeoutMs: 20000 });
        const end = done.state;
        record({
          name: "step7-390-restored", status: end && end.text === seedText && end.discardAlertVisible ? "pass" : "fail",
          detail: `textRestored=${end?.text === seedText} discardAlertVisible=${end?.discardAlertVisible} viewport=${end ? "390" : "?"}`,
        });
        const overflow = await tab.overflowMetrics();
        record({
          name: "step7-390-no-horizontal-overflow", status: overflow.docNoHorizontalOverflow && overflow.sectionNoHorizontalOverflow && overflow.longReferenceLabelsContained ? "pass" : "fail",
          detail: JSON.stringify(overflow),
        });
        await saveShot(tab, "step7-390-restored", false);
        const leak = await tab.leakScan(markers);
        record({
          name: "step7-no-marker-leak", status: leak.found.length === 0 ? "pass" : "fail",
          detail: `markersScanned=${markers.length} leaked=${JSON.stringify(leak.found)} (DOM/storage/cookies after final restore)`,
        });
        saveJson("step7-390-leak-scan", { markersScanned: markers.map(m => `${m.slice(0, 12)}…`), found: leak.found, localStorageEntries: leak.localStorageEntries, sessionStorageEntries: leak.sessionStorageEntries, localStorageDump: leak.localStorageDump, sessionStorageDump: leak.sessionStorageDump });
      }
    }

    // Only one PUT may exist for the whole run (the precondition seed).
    const putCount = tab.draftCapture.filter(e => e.method === "PUT").length;
    record({ name: "page-put-count", status: putCount === 1 ? "pass" : "fail", detail: `PUT answer-draft calls=${putCount} (expected exactly 1: the precondition seed; marker never sent)` });
    saveJson("network-log", { network: tab.networkLog, answerDraft: tab.draftCapture });
  } catch (error) {
    if (error instanceof PageAbortError) {
      record({ name: "page-flow-aborted", status: "blocked", detail: `remaining page steps aborted honestly: ${String(error.message).slice(0, 300)}` });
    } else {
      throw error;
    }
  } finally {
    await browser.stop().catch(() => {});
  }

  // Read-only invariant compare AFTER all page actions.
  if (baseline) {
    const after = await captureInvariants("after", target.id, CREDS);
    for (const [name, ok, detail] of compareInvariants(baseline, after, markers)) {
      record({ name: `invariant-${name}`, status: ok ? "pass" : "fail", detail: ok ? "" : detail });
    }
    const fixtureAgreement = after.apps.filter(a => a.canonicalSnapshotSha256 === a.fixtureSnapshotSha256).length;
    record({
      name: "invariant-frozen-snapshot-fixture-note", status: "info",
      detail: `canonical-vs-fixture agreement=${fixtureAgreement}/${after.apps.length} (informative only: Python-float serialization prevents byte-exact JS replication; the hard guarantee is the raw before/after equality above)`,
    });
  } else {
    record({ name: "invariants-after", status: "blocked", detail: "page flow aborted before the after-seed baseline; before/after compare not meaningful and skipped" });
  }

  record({ name: "runner-done", status: exitCode === 0 ? "pass" : exitCode === 1 ? "fail" : "blocked", detail: `exitCode=${exitCode}` });
  return exitCode;
}

function captureData(entry) {
  if (!entry?.responseBody || entry.responseBody === "(unavailable)") return null;
  try { return JSON.parse(entry.responseBody)?.data ?? null; } catch { return null; }
}

// Direct-run guard: importing this module (tests) performs no side effects.
const isDirectRun = process.argv[1] ? import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href : false;
if (isDirectRun) {
  const selection = parseArgs(process.argv.slice(2));
  if (!selection) {
    console.error("Invalid --run arguments; only --run question-chain-20261010 is accepted; no files were written.");
    process.exit(3);
  }
  main()
    .then(code => { process.exit(code); })
    .catch(error => {
      console.error(`blocked: ${scrub(String(error?.message ?? error))}`);
      try { record({ name: "runner-blocked", status: "blocked", detail: String(error?.message ?? error).slice(0, 400) }); } catch { /* evidence dir may not exist yet */ }
      process.exit(2);
    });
}
