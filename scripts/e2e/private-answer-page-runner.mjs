// PRODUCT-01 private answer draft page acceptance runner (task card
// 20261006-PRODUCT-01-page-acceptance, matrix 20261005-PRODUCT-01-codex).
// Drives the REAL production pages at http://127.0.0.1:3001 through a real
// headless Chrome over raw CDP with an independent profile. All draft actions
// (read, type, select reference, save, refresh) go through the UI only; the
// Node-side authenticated API calls are preflight/target selection and
// server-truth cross-checks, never a substitute for the page. Read-only psql
// verifies what the UI produced. No SQL writes anywhere.
//
// Usage: node scripts/e2e/private-answer-page-runner.mjs --run closure-20261005 --scenario s1-save-refresh
// The run id is pinned to closure-20261005 (PRODUCT-01 acceptance target).
// Exit codes: 0 pass, 1 fail, 2 blocked, 3 invalid arguments.
//
// Secrets (synthetic passwords, cookie values) are loaded programmatically,
// kept in memory, scrubbed from every log/evidence file and never printed.
// Write surface: this file + docs/evidence/20261006-PRODUCT-01-pages/ +
// own ignored runtime under backend/.tmp/e2e-browser/<run>-private-answer.

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { parseCredentialDocument } from "./runner-input.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const FRONTEND = "http://127.0.0.1:3001";
const BACKEND = "http://127.0.0.1:8001";
const API = `${BACKEND}/api/v1`;
const BACKEND_DIR = path.join(ROOT, "backend");
const EVIDENCE_DIR = path.join(ROOT, "docs", "evidence", "20261007-PRODUCT-01-pages");

const SCENARIOS = Object.freeze([
  "s1-save-refresh", "s2-clear-explicit-save", "s3-save-inflight-edit",
  "s3b-request-stage-delay", "s4-dual-window-409", "s5-network-error",
  "s6-identity-late-response", "s6b-identity-switch-race", "s7-requirement-crossjob",
  "s8-invalid-reference", "s9-third-party-reference",
  "s10-preview-confirm-copy", "s11-viewport390", "s12-old-state-unchanged",
]);

// ---------------------------------------------------------------------------
// Arguments (run-id format matches Start/Stop-E2E + seeder)
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const values = { "--run": "", "--scenario": "" };
  const seen = new Set();
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i], value = argv[i + 1];
    if (!Object.hasOwn(values, key) || seen.has(key) || !value || value.startsWith("--")) return null;
    seen.add(key); values[key] = value;
  }
  if (values["--run"] !== "closure-20261005") return null;
  if (!SCENARIOS.includes(values["--scenario"])) return null;
  return { runId: values["--run"], scenario: values["--scenario"] };
}
const selection = parseArgs(process.argv.slice(2));
if (!selection) { console.error("Invalid --run/--scenario arguments; no files were written."); process.exit(3); }
const { runId: RUN_ID, scenario: SCENARIO } = selection;

fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
const RUNTIME_DIR = path.join(BACKEND_DIR, ".tmp", "e2e-browser", `${RUN_ID}-private-answer`);
fs.mkdirSync(RUNTIME_DIR, { recursive: true });

// ---------------------------------------------------------------------------
// Evidence plumbing (same conventions as the student/enterprise runners)
// ---------------------------------------------------------------------------
const RUN_STAMP = new Date().toISOString().replace(/[:.]/g, "-");
const STAGE_DIR = path.join(EVIDENCE_DIR, `${SCENARIO}-${RUN_STAMP}`);
fs.mkdirSync(STAGE_DIR, { recursive: true });
const results = { runId: RUN_ID, scenario: SCENARIO, startedAt: new Date().toISOString(), steps: [], artifacts: [] };
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
  results.finishedAt = new Date().toISOString();
  fs.writeFileSync(path.join(STAGE_DIR, "results.json"), JSON.stringify(results, null, 2));
}
async function saveShot(tab, name, fullPage = true) {
  const file = path.join(STAGE_DIR, `${String(stepCounter + 1).padStart(2, "0")}-${name}.png`);
  await tab.screenshot(file, fullPage);
  record({ name: `screenshot:${name}`, status: "evidence", detail: path.relative(ROOT, file) });
  return file;
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
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, scrubDeep(v)]));
  return value;
}

// ---------------------------------------------------------------------------
// Credentials (synthetic; loaded programmatically, never printed)
// ---------------------------------------------------------------------------
function loadCredentials() {
  const file = path.join(BACKEND_DIR, ".tmp", "e2e", `${RUN_ID}.json`);
  if (!path.resolve(file).startsWith(path.resolve(BACKEND_DIR, ".tmp"))) throw new Error("credential path escaped isolated root");
  const raw = parseCredentialDocument(fs.readFileSync(file, "utf8"));
  if (raw.runId !== RUN_ID) throw new Error("credential file runId mismatch");
  for (const account of Object.values(raw.accounts ?? {})) {
    if (typeof account?.password === "string" && account.password) SCRUB.push(account.password);
  }
  return raw;
}
const CREDS = loadCredentials();

// ---------------------------------------------------------------------------
// Read-only DB diagnostics (docker compose exec psql; SELECT only)
// ---------------------------------------------------------------------------
function dbQuery(sql) {
  // READ ONLY is enforced by the server: any statement that would write fails.
  const readOnlySql = `BEGIN READ ONLY; ${sql} ROLLBACK;`;
  return new Promise((resolve, reject) => {
    const child = spawn("docker", ["compose", "exec", "-T", "postgres", "psql", "-U", "careerproof",
      "-d", `cp_e2e_${RUN_ID}`, "-At", "-c", readOnlySql],
      { cwd: BACKEND_DIR, stdio: ["ignore", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", chunk => { out += String(chunk); });
    child.stderr.on("data", chunk => { err += String(chunk); });
    child.on("exit", code => {
      if (code !== 0) { reject(new Error(`psql exit ${code}: ${err.slice(0, 200)}`)); return; }
      // -c multi-statement prints the BEGIN/ROLLBACK command tags; they are
      // not data. The transaction itself stays READ ONLY on the server.
      resolve(out.split("\n").map(l => l.replace(/\r$/, "")).filter(l => l !== "BEGIN" && l !== "ROLLBACK" && l !== "COMMIT").join("\n").trim());
    });
    child.on("error", reject);
  });
}

// ---------------------------------------------------------------------------
// Preflight: manifest, health, real port owners, backend DB identity
// ---------------------------------------------------------------------------
async function preflight() {
  const manifestPath = path.join(BACKEND_DIR, ".tmp", "e2e-run", `processes-${RUN_ID}.json`);
  const manifest = parseCredentialDocument(fs.readFileSync(manifestPath, "utf8"));
  if (manifest.runId !== RUN_ID) throw new Error("manifest runId mismatch");
  record({ name: "manifest", status: "info", detail: `db=${manifest.databaseName} provider=${manifest.aiProvider} external=${manifest.aiExternalEnabled} distDir=${manifest.distDir}` });
  if (manifest.aiProvider !== "mock" || manifest.aiExternalEnabled !== "false") {
    record({ name: "manifest-mock-check", status: "fail", detail: "expected provider=mock external=false" });
  } else {
    record({ name: "manifest-mock-check", status: "pass" });
  }

  const feHealth = await fetch(`${FRONTEND}/login`, { redirect: "manual" }).then(r => r.status).catch(() => null);
  record({ name: "frontend-health", status: feHealth === 200 ? "pass" : "blocked", detail: `GET /login -> ${feHealth}` });
  const beHealth = await fetch(`${API}/health`).then(async r => ({ status: r.status, body: (await r.text()).slice(0, 200) })).catch(e => ({ status: null, body: String(e.message).slice(0, 120) }));
  record({ name: "backend-health", status: beHealth.status === 200 ? "pass" : "blocked", detail: `GET /api/v1/health -> ${beHealth.status} ${scrub(beHealth.body)}` });
  if (feHealth !== 200 || beHealth.status !== 200) throw new Error("preflight: services not healthy");

  const owners = await portOwners([3001, 8001]);
  record({ name: "port-owners", status: "info", detail: JSON.stringify(owners) });
  const manifestPids = new Set([manifest.backend?.id, ...((manifest.processes ?? []).map(p => p.id))].filter(Boolean));
  const live = [owners[3001], owners[8001]].filter(Boolean);
  const matches = live.filter(pid => manifestPids.has(pid)).length;
  record({
    name: "process-identity",
    status: matches > 0 ? "pass" : "blocked",
    detail: `live=[${live.join(",")}] manifest=[${[...manifestPids].join(",")}] matched=${matches}` +
      (matches === 0 ? " — no manifest PID alive; DB identity cross-check below decides" : ""),
  });

  // Empirical DB identity: the session the backend actually serves must see
  // exactly the growth tasks stored in cp_e2e_<run> (read-only psql).
  const auth = await apiLogin(CREDS.accounts.student);
  const tasks = await auth.getJson("/growth-tasks");
  const uiIds = tasks.map(t => t.id).sort();
  // GET /growth-tasks returns only the caller's own tasks; the closure DB also
  // holds other fixture users' tasks, so filter by the same owner.
  const dbIds = (await dbQuery(`SELECT id::text FROM evidence_growth_tasks WHERE created_by = '${CREDS.accounts.student.userId}' ORDER BY created_at;`)).split("\n").filter(Boolean).sort();
  // The list view skips tasks with historical snapshot drift (defensive, by
  // design), so require every API id to exist in this DB for this owner —
  // a different database would return a disjoint id set.
  const dbMatch = uiIds.length > 0 && uiIds.every(id => dbIds.includes(id));
  record({
    name: "backend-db-identity",
    status: dbMatch ? "pass" : "blocked",
    detail: `api own tasks=${uiIds.length} db own tasks=${dbIds.length} apiIdsInDb=${dbMatch}`,
  });
  if (!dbMatch) throw new Error("preflight: backend on 8001 does not serve the closure database");
  return { manifest, auth, tasks };
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

// Minimal authenticated API client: login via the real endpoint, keep the
// cookie in memory only, scrub it from anything recorded.
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
  record({ name: "api-login", status: "pass", detail: `userId=${user?.id} role=${user?.role}` });
  return {
    async getJson(path) {
      const r = await fetch(`${API}${path}`, { headers: { Cookie: cookie } });
      if (r.status !== 200) throw new Error(`GET ${path} -> ${r.status}`);
      return (await r.json())?.data;
    },
    async status(path) {
      const r = await fetch(`${API}${path}`, { headers: { Cookie: cookie } });
      return r.status;
    },
    async putStatus(path, payload) {
      const r = await fetch(`${API}${path}`, { method: "PUT", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      let code = null;
      try { code = (await r.json())?.code; } catch { /* non-JSON body */ }
      return { status: r.status, code };
    },
  };
}

// ---------------------------------------------------------------------------
// Chrome + CDP (same self-contained pattern as the student runner, plus
// answer-draft response body capture and page reload)
// ---------------------------------------------------------------------------
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
class CdpError extends Error {}

// WMI facts for one pid as JSON (ProcessId/CreationDate/ExecutablePath/
// CommandLine); null when the process is gone or WMI is unavailable.
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
  constructor(label, { width = 1440, height = 900 } = {}) {
    this.label = label;
    this.profileDir = path.join(RUNTIME_DIR, `profile-${label}-${RUN_STAMP}`);
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
      "--headless=new", "--remote-debugging-port=0",
      `--user-data-dir=${this.profileDir}`,
      "--no-first-run", "--no-default-browser-check", "--disable-extensions",
      "--disable-sync", "--disable-gpu", "--disable-search-engine-choice-screen",
      "--remote-allow-origins=*", `--window-size=${this.width},${this.height}`, "about:blank",
    ], { stdio: "ignore" });
    // Capture the OS-level creation time right after spawn: the force-kill
    // guard later requires PID + CreationDate + executable + unique profile to
    // all still match this run's own process.
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
    if (!this.port) throw new CdpError(`DevToolsActivePort did not appear (${this.label})`);
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
    record({ name: "chrome-launched", status: "info", detail: `${this.label} port ${this.port}` });
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
      // Force-kill guard: PID alone is not identity (PIDs are reused). Require
      // the recorded CreationDate, the exact Chrome executable path and this
      // run's unique --user-data-dir in the live command line; skip the kill
      // with an honest warning when any fact cannot be verified.
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
        record({
          name: "chrome-kill-skipped",
          status: "warn",
          detail: `${this.label} pid=${this.child.pid} could not be re-verified as this run's own Chrome (pid/creationDate/executable/profile); left running instead of risking another process`,
        });
      } else {
        spawn("taskkill", ["/PID", String(this.child.pid), "/T", "/F"], { stdio: "ignore" });
        const deadline = Date.now() + 5000;
        while (this.child.exitCode === null && Date.now() < deadline) await sleep(200);
        record({
          name: this.child.exitCode === null ? "chrome-force-kill-pending" : "chrome-force-killed",
          status: "warn",
          detail: `${this.label} verified pid+creationDate+executable+unique profile before kill; exited=${this.child.exitCode !== null}`,
        });
      }
    }
    record({ name: "chrome-stopped", status: "info", detail: `${this.label} exitCode=${this.child?.exitCode ?? "n/a"}` });
  }
}

class Tab {
  constructor(browser, sessionId, targetId) {
    this.browser = browser; this.sessionId = sessionId; this.targetId = targetId;
    this.networkLog = [];
    this.answerCapture = []; // answer-draft requests: method/url/status/bodies
    // Clearly-marked network-layer fault injection (matrix rows 3/5): a queue
    // consumed one-per-matching answer-draft request. delay holds the request
    // in the Fetch domain (response arrives late); fail aborts it as a network
    // error. Everything is recorded in faultLog for the evidence file.
    this.answerFaults = [];
    this.faultLog = [];
    this.heldResponses = [];
    const pendingBodies = new Map(); // requestId -> capture entry
    browser.onEvent(msg => {
      if (msg.sessionId !== this.sessionId) return;
      const p = msg.params ?? {};
      if (msg.method === "Network.requestWillBeSent") {
        this.networkLog.push({ at: new Date().toISOString(), phase: "request", method: p.request.method, url: this.#shortUrl(p.request.url) });
        if (/\/answer-draft/.test(p.request.url)) {
          const entry = { at: new Date().toISOString(), method: p.request.method, url: this.#shortUrl(p.request.url), requestBody: p.request.postData ?? null, status: null, responseBody: null };
          this.answerCapture.push(entry);
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
            .then(body => { entry.responseBody = body ? Buffer.from(body.base64 ? body.body : body.body, body.base64 ? "base64" : "utf8").toString("utf8") : null; })
            .catch(() => { entry.responseBody = "(unavailable)"; });
        }
      } else if (msg.method === "Fetch.requestPaused") {
        const isAnswerDraft = /\/answer-draft/.test(p.request.url);
        if (isAnswerDraft && p.request.postData) {
          for (let i = this.answerCapture.length - 1; i >= 0; i--) {
            const e = this.answerCapture[i];
            if (e.method === p.request.method && e.requestBody === null) { e.requestBody = p.request.postData.slice(0, 4000); break; }
          }
        }
        // Peek before shift: a fault is consumed only when method, endpoint
        // and stage all match, so a draft GET or /references request can
        // never consume a PUT fault.
        const stage = p.responseStatusCode !== undefined ? "response" : "request";
        let faultIdx = -1;
        if (isAnswerDraft) {
          for (let i = 0; i < this.answerFaults.length; i++) {
            const f = this.answerFaults[i];
            if ((f.method ?? "PUT") !== p.request.method) continue;
            if ((f.stage ?? "request") !== stage) continue;
            if (f.url && !new RegExp(f.url).test(p.request.url)) continue;
            if (f.exactEndpoint && !/\/answer-draft$/.test(p.request.url)) continue;
            faultIdx = i; break;
          }
        }
        const fault = faultIdx >= 0 ? this.answerFaults.splice(faultIdx, 1)[0] : null;
        if (!fault) {
          this.send("Fetch.continueRequest", { requestId: p.requestId }).catch(() => {});
        } else if (fault.kind === "hold-response") {
          // Response-stage pause: the server already answered (status in
          // p.responseStatusCode); the receipt is held back from the page
          // until releaseHeldResponse() explicitly continues it.
          const entry = { at: new Date().toISOString(), kind: "hold-response", method: p.request.method, stage, status: p.responseStatusCode ?? null, released: false, releasedAt: null };
          this.faultLog.push(entry);
          this.heldResponses.push({ requestId: p.requestId, entry });
        } else if (fault.kind === "modify-response") {
          // Clearly-marked RESPONSE-body rewrite (e.g. degrade a reference to
          // available=false/snippet=null): reads the server's real body,
          // applies the runner's transform, then fulfills with the modified
          // body. Never touches the database; the server keeps its own truth.
          const entry = { at: new Date().toISOString(), kind: "modify-response", method: p.request.method, stage, status: p.responseStatusCode ?? null, fulfilled: null };
          this.faultLog.push(entry);
          void (async () => {
            try {
              const body = await this.send("Fetch.getResponseBody", { requestId: p.requestId });
              // Some Chrome builds return base64 content with base64=false;
              // detect the encoding instead of trusting the flag alone.
              let text = String(body.body);
              if (body.base64 || !text.trimStart().startsWith("{")) {
                text = Buffer.from(text, "base64").toString("utf8");
              }
              entry.originalBodyLen = text.length;
              const modified = fault.transform(JSON.parse(text));
              const b64 = Buffer.from(JSON.stringify(modified), "utf8").toString("base64");
              await this.send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 200, body: b64, responseHeaders: [{ name: "content-type", value: "application/json" }] });
              entry.fulfilled = true;
            } catch (error) {
              entry.fulfilled = false;
              entry.error = String(error?.message ?? error).slice(0, 160);
              // Never leave a request hanging: fall back to the server's
              // original body so the page keeps working and the failure is
              // visible in the evidence instead of a silent timeout.
              this.send("Fetch.continueRequest", { requestId: p.requestId }).catch(() => {});
            }
          })();
        } else if (fault.kind === "delay") {
          const entry = { at: new Date().toISOString(), kind: "delay", method: p.request.method, stage, ms: fault.ms };
          this.faultLog.push(entry);
          setTimeout(() => { entry.releasedAt = new Date().toISOString(); this.send("Fetch.continueRequest", { requestId: p.requestId }).catch(() => {}); }, fault.ms);
        } else if (fault.kind === "fail") {
          this.faultLog.push({ at: new Date().toISOString(), kind: "fail", method: p.request.method, stage });
          this.send("Fetch.failRequest", { requestId: p.requestId, errorReason: "Failed" }).catch(() => {});
        } else {
          this.send("Fetch.continueRequest", { requestId: p.requestId }).catch(() => {});
        }
      }
    });
  }
  #shortUrl(url) { return url.replace(/^https?:\/\/127\.0\.0\.1:[0-9]+\/backend?/, "").replace(/^https?:\/\/127\.0\.0\.1:[0-9]+/, ""); }
  send(method, params) { return this.browser.send(method, params, this.sessionId); }
  async enable() {
    await this.send("Page.enable");
    await this.send("Network.enable");
    await this.send("Runtime.enable");
    await this.send("Fetch.enable", { patterns: [{ urlPattern: "*" }], handleAuthRequests: false });
  }
  // Pause answer-draft requests at the RESPONSE stage (server already
  // answered and persisted): required for the late-receipt scenarios, where
  // the first PUT/GET really landed before the page sees its receipt.
  async useResponseStageAnswerDraft() {
    await this.send("Fetch.disable").catch(() => {});
    await this.send("Fetch.enable", {
      patterns: [
        { urlPattern: "*/answer-draft", requestStage: "Response" },
        { urlPattern: "*" },
      ],
      handleAuthRequests: false,
    });
  }
  async releaseHeldResponse(index) {
    const held = this.heldResponses[index];
    if (!held || held.entry.released) return false;
    try {
      await this.send("Fetch.continueRequest", { requestId: held.requestId });
      held.entry.released = true;
      held.entry.releasedAt = new Date().toISOString();
      return "released";
    } catch (error) {
      // After the owning page context is gone (logout/navigation destroyed
      // it), the interception id is invalid: the late receipt physically
      // cannot reach any page anymore. Record that fact honestly.
      if (/Invalid InterceptionId/.test(String(error?.message))) {
        held.entry.released = true;
        held.entry.releasedAt = new Date().toISOString();
        held.entry.releaseOutcome = "interception-invalid-after-context-destroyed";
        return "invalid-after-navigation";
      }
      throw error;
    }
  }
  async waitHeldResponse(method, timeoutMs = 8000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      const idx = this.heldResponses.findIndex(h => h.entry.method === method && !h.entry.released);
      if (idx >= 0) return idx;
      await sleep(100);
    }
    return -1;
  }
  async goto(url, timeoutMs = 30000) {
    const loaded = this.waitForEvent("Page.loadEventFired", timeoutMs).catch(() => null);
    await this.send("Page.navigate", { url });
    await loaded;
    await this.evalJs("document.readyState").catch(() => "loading");
    return this;
  }
  async reload(timeoutMs = 30000) {
    const loaded = this.waitForEvent("Page.loadEventFired", timeoutMs).catch(() => null);
    await this.send("Page.reload");
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
    // The client-side CDP ceiling must exceed the in-page awaitPromise loop,
    // or a long waitFor dies as "cdp timeout" instead of returning {ok:false}.
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
          const secret = el.tagName === "INPUT" && el.type === "password";
          const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(" ").trim();
          const full = (el.textContent ?? "").trim();
          const hay = secret ? [] : [own, full, el.getAttribute("aria-label") ?? "", el.getAttribute("placeholder") ?? ""];
          let hit = !wanted;
          for (const candidate of hay) { if (exact ? candidate === wanted : candidate.includes(wanted)) { hit = true; break; } }
          if (attr && el.getAttribute(attr) !== (attrValue ?? true)) hit = false;
          if (!hit) continue;
          const rect = el.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) continue;
          matches.push({ tag: el.tagName.toLowerCase(), text: secret ? "(password)" : full.slice(0, 140), x: Math.round(rect.x + rect.width / 2), y: Math.round(rect.y + rect.height / 2), top: Math.round(rect.top), h: Math.round(rect.height), disabled: el.disabled === true });
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
  // Click a node that a page expression scrolled into view and stashed on
  // window.__e2eClickEl (for elements the text finder cannot disambiguate).
  async clickStored(locatorExpression, label) {
    const found = await this.evalJs(locatorExpression);
    if (!found) throw new CdpError(`clickStored: target not found (${label})`);
    await sleep(250);
    const point = await this.evalJs(`(() => {
      const el = window.__e2eClickEl;
      if (!el || !el.isConnected) return null;
      const r = el.getBoundingClientRect();
      const x = Math.round(r.x + Math.min(Math.max(r.width / 2, 8), r.width - 8)), y = Math.round(r.y + Math.max(r.height / 2, 6));
      const hit = document.elementFromPoint(x, y);
      return { x, y, hitIsEl: hit === el || el.contains(hit) };
    })()`);
    if (!point || point.x <= 0 || point.y <= 0 || !point.hitIsEl) throw new CdpError(`clickStored: no clickable rect for ${label}: ${JSON.stringify(point)}`);
    for (const type of ["mousePressed", "mouseReleased"]) {
      await this.send("Input.dispatchMouseEvent", { type, x: point.x, y: point.y, button: "left", clickCount: 1, buttons: type === "mousePressed" ? 1 : 0 });
    }
    await sleep(180);
  }
  // Click a stored node AND guarantee it holds focus afterwards (real clicks
  // occasionally leave activeElement=BODY on this app); the fallback calls
  // el.focus() so subsequent keystrokes are still real input events.
  async clickFocusStored(locatorExpression, label) {
    await this.clickStored(locatorExpression, label);
    const state = await this.evalJs(`(() => { const el = window.__e2eClickEl; return el ? { focused: document.activeElement === el, tag: el.tagName } : null; })()`);
    if (!state) throw new CdpError(`clickFocusStored: element vanished (${label})`);
    if (!state.focused) {
      await this.evalJs(`window.__e2eClickEl && window.__e2eClickEl.focus()`);
      await sleep(120);
      const ok = await this.evalJs(`window.__e2eClickEl === document.activeElement`);
      if (!ok) throw new CdpError(`clickFocusStored: focus failed (${label})`);
      record({ name: "focus-fallback", status: "info", detail: `${label}: real click did not focus; el.focus() applied before real keyboard input` });
    }
    return true;
  }
  // Attach a local file to a real <input type=file> via DOM.setFileInputFiles.
  async setFileInput(selector, absolutePath) {
    const { root } = await this.send("DOM.getDocument", { depth: 1 });
    const { nodeId } = await this.send("DOM.querySelector", { nodeId: root.nodeId, selector });
    if (!nodeId) throw new CdpError(`setFileInput: ${selector} not found`);
    await this.send("DOM.setFileInputFiles", { files: [absolutePath], nodeId });
    await sleep(200);
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
  // Select-all + Delete on a focused field: the real "clear the textarea"
  // user action (an empty insertText is not guaranteed to delete a selection).
  async clearText(opts, label) {
    await this.click(opts, { label });
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46 });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46 });
    await sleep(200);
    const got = await this.evalJs(`(document.activeElement?.value ?? "")`);
    if (got !== "") throw new CdpError(`clearText failed: ${label} remaining length=${got.length}`);
  }
  // Click into a field, move the caret to the very end, then type more text.
  async appendText(opts, text, label) {
    await this.click(opts, { label });
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, key: "End", code: "End", windowsVirtualKeyCode: 35 });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, key: "End", code: "End", windowsVirtualKeyCode: 35 });
    await this.send("Input.insertText", { text });
    await sleep(200);
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
  bodyText() { return this.evalJs("document.body.innerText"); }
  async setViewport(width, height) {
    await this.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 2, mobile: width <= 500 });
    await sleep(300);
  }
  async draftSnapshot() {
    return this.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return null;
      const savedLine = Array.from(section.querySelectorAll('p')).map(p => p.textContent.trim()).find(t => t.startsWith('已保存：')) ?? null;
      const textarea = section.querySelector('#private-answer-text');
      const checked = Array.from(section.querySelectorAll('input[type=checkbox]'))
        .filter(b => b.checked).map(b => (b.closest('label')?.textContent ?? '').trim());
      const alertTexts = Array.from(section.querySelectorAll('[role=alert]')).map(e => e.textContent.trim()).filter(Boolean);
      return { path: location.pathname, savedLine, text: textarea ? textarea.value : null, checkedReferences: checked, alerts: alertTexts };
    })()`);
  }
}

// ---------------------------------------------------------------------------
// Shared UI flows
// ---------------------------------------------------------------------------
async function login(tab, account) {
  await tab.goto(`${FRONTEND}/login`);
  await tab.installFinder();
  await tab.waitFor(`() => document.querySelector('input[type=email]') && document.querySelector('input[type=password]')`, { label: "login form" });
  await saveShot(tab, "login-empty");
  await tab.fillText({ tag: "input[type=email]" }, account.email, { label: "email", expectValue: account.email });
  await tab.fillText({ tag: "input[type=password]" }, account.password, { label: "password", expectValue: account.password });
  await tab.click({ tag: "button[type=submit]" }, { label: "login submit" });
  await tab.waitFor(`() => !location.pathname.startsWith("/login")`, { timeoutMs: 20000, label: "redirect after login" });
  await sleep(800);
  await tab.installFinder();
  record({ name: "login-ok", status: "pass", detail: await tab.evalJs("location.pathname") });
}

async function openDraftSection(tab, taskId) {
  await tab.goto(`${FRONTEND}/growth/${taskId}`);
  await tab.installFinder();
  await tab.waitFor(`() => Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿'))`, { timeoutMs: 30000, label: "private answer draft section" });
  await tab.waitFor(`() => !document.querySelector('#private-answer-text')?.disabled`, { timeoutMs: 15000, label: "draft textarea enabled (reading done)" });
}

// Long full-page CDP captures render below-fold sections blank on this app, so
// readable visual evidence must scroll the draft panel into the real viewport
// and capture what is actually displayed; a second lower shot covers panels
// taller than one viewport.
async function saveDraftPanelShots(tab, name) {
  const found = await tab.evalJs(`(() => {
    const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
    if (!section) return false;
    section.scrollIntoView({ block: 'start' });
    return true;
  })()`);
  if (!found) throw new Error("draft section not found for panel screenshot");
  await sleep(350);
  const info = await tab.evalJs(`(() => {
    const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
    const r = section.getBoundingClientRect();
    return { top: Math.round(r.top), height: Math.round(r.height), viewportH: window.innerHeight, viewportW: window.innerWidth };
  })()`);
  if (info.top < 0 || info.top >= info.viewportH - 40) throw new Error(`draft section not in viewport after scrollIntoView: ${JSON.stringify(info)}`);
  await saveShot(tab, `panel-${name}`, false);
  record({ name: `panel-visible:${name}`, status: "info", detail: `viewport=${info.viewportW}x${info.viewportH} sectionTop=${info.top} sectionHeight=${info.height}` });
  if (info.top + info.height > info.viewportH) {
    await tab.evalJs(`window.scrollBy(0, ${info.viewportH - 120})`);
    await sleep(350);
    await saveShot(tab, `panel-${name}-lower`, false);
  }
}

// ---------------------------------------------------------------------------
// Scenario 1: 初次保存与刷新 (initial save and refresh)
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Shared scenario helpers
// ---------------------------------------------------------------------------
// Pick the first own task whose selectable references include a baseline
// (基准报告) option — read-only API used for target selection only.
async function selectDraftTarget(auth, tasks) {
  let target = null;
  for (const task of tasks) {
    const refs = await auth.getJson(`/growth-tasks/${task.id}/answer-draft/references`).catch(() => null);
    const baseCount = Array.isArray(refs) ? refs.filter(r => r.reportKind === "base").length : 0;
    record({ name: `task-options:${task.requirementTitle}`, status: "info", detail: `taskId=${task.id} job=${task.jobTitle} baseOptions=${baseCount} totalOptions=${Array.isArray(refs) ? refs.length : "n/a"}` });
    if (!target && baseCount > 0) target = { task, refs };
  }
  if (!target) throw new Error("no own task with baseline reference options");
  return target;
}

// Load the draft page and return the real server baseline from the captured
// initial GET (revision 0 semantics when the server has no draft yet).
async function openDraftWithBaseline(tab, taskId) {
  const mark = tab.answerCapture.length;
  await openDraftSection(tab, taskId);
  await sleep(500); // let the initial draft GET response body settle
  const gets = tab.answerCapture.slice(mark)
    .filter(e => e.method === "GET" && e.url.includes("/answer-draft") && !e.url.includes("/references"));
  if (!gets.length) throw new Error("initial draft GET not captured on page load");
  const data = captureData(gets[gets.length - 1]);
  const baseline = data === null ? 0 : data.revision;
  record({
    name: "draft-initial-get",
    status: gets[gets.length - 1].status === 200 ? "pass" : "fail",
    detail: `GET status=${gets[gets.length - 1].status} hasDraft=${data !== null} baselineRevision=${baseline}`,
  });
  return { baseline, savedText: data?.text ?? "", savedRefs: citationIds(data?.references) };
}

// Real refresh, then reread the draft from page + server.
async function reloadDraft(tab) {
  const mark = tab.answerCapture.length;
  await tab.reload();
  await tab.installFinder();
  await tab.waitFor(`() => Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿'))`, { timeoutMs: 30000, label: "draft section after refresh" });
  await tab.waitFor(`() => !document.querySelector('#private-answer-text')?.disabled`, { timeoutMs: 15000, label: "textarea enabled after refresh" });
  await sleep(600);
  const gets = tab.answerCapture.slice(mark)
    .filter(e => e.method === "GET" && e.url.includes("/answer-draft") && !e.url.includes("/references"));
  return { gets, data: gets.length ? captureData(gets[gets.length - 1]) : null };
}

// Click 保存草稿 and wait for the receipt line; requireClean waits for the
// 与已保存内容一致 state, otherwise any 已保存 line with the expected version.
async function saveDraftAndAwait(tab, { expectRevision, requireClean = true } = {}) {
  const mark = tab.answerCapture.length;
  await tab.click({ tag: "button", text: "保存草稿", exact: true }, { label: "save draft" });
  await tab.waitFor(`() => (() => {
    const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
    if (!section) return false;
    const p = Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()).find(t => t.startsWith('已保存：'));
    if (!p) return false;
    ${expectRevision !== undefined ? "if (!p.includes('版本 " + expectRevision + "')) return false;" : ""}
    ${requireClean ? "if (!p.includes('与已保存内容一致')) return false;" : ""}
    return true;
  })()`, { timeoutMs: 20000, label: `save receipt${expectRevision !== undefined ? " rev " + expectRevision : ""}` });
  await sleep(600);
  return tab.answerCapture.slice(mark).filter(e => e.method === "PUT");
}

// ---------------------------------------------------------------------------
// Scenario 1: 初次保存与刷新 (initial save and refresh)
// ---------------------------------------------------------------------------
async function scenarioSaveRefresh(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  saveJson("s1-target-task", { taskId: target.task.id, requirementTitle: target.task.requirementTitle, jobTitle: target.task.jobTitle, options: target.refs });

  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);

    const { baseline: baselineRevision } = await openDraftWithBaseline(tab, target.task.id);
    const initial = await tab.draftSnapshot();
    record({ name: "draft-initial-state", status: "info", detail: JSON.stringify(initial) });
    await saveShot(tab, "draft-initial");
    await saveDraftPanelShots(tab, "initial");

    // Named synthetic text with a newline: verbatim round-trip check.
    const stamp = new Date().toISOString().replace(/[:.]/g, "");
    const draftText = `PRODUCT01-S1-私人草稿保存刷新验证 ${stamp}\n第二行：换行与标点，原样保存检查。`;
    const baseOption = target.refs.find(r => r.reportKind === "base");
    const baseOptionLabel = `基准报告 ${baseOption.citationId}`;

    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, draftText, { label: "draft text", expectValue: draftText });

    // Select the server baseline reference checkbox by its label text.
    await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const box = section && Array.from(section.querySelectorAll('input[type=checkbox]'))
        .find(b => ((b.closest('label')?.textContent ?? '')).includes(${JSON.stringify(baseOptionLabel)}));
      if (!box) return false;
      box.scrollIntoView({ block: 'center' });
      window.__e2eClickEl = box;
      return true;
    })()`);
    if (!(await tab.evalJs("!!window.__e2eClickEl"))) throw new Error(`baseline reference checkbox not found: ${baseOptionLabel}`);
    // A real click on a checkbox both focuses and toggles it; Space is only
    // the fallback when the click landed without changing the state.
    await tab.clickStored(`(() => window.__e2eClickEl && window.__e2eClickEl.isConnected)()`, "baseline reference checkbox");
    await sleep(300);
    if (!(await tab.evalJs("window.__e2eClickEl.checked"))) {
      await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
      await tab.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
      await sleep(300);
    }
    const boxChecked = await tab.evalJs("window.__e2eClickEl.checked");
    if (boxChecked !== true) throw new Error("baseline reference checkbox not checked after real toggle");
    record({ name: "reference-selected", status: "pass", detail: baseOptionLabel });

    const beforeSave = await tab.draftSnapshot();
    record({ name: "before-save-state", status: "info", detail: JSON.stringify({ savedLine: beforeSave.savedLine, checked: beforeSave.checkedReferences, textLength: beforeSave.text?.length }) });
    await saveShot(tab, "before-save");
    await saveDraftPanelShots(tab, "before-save");

    // Explicit save. Capture the PUT request/response (real save receipt).
    const mark = tab.answerCapture.length;
    await tab.click({ tag: "button", text: "保存草稿", exact: true }, { label: "save draft" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return false;
      const p = Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()).find(t => t.startsWith('已保存：'));
      return !!p && p.includes('与已保存内容一致');
    })()`, { timeoutMs: 20000, label: "save receipt with clean state" });
    await sleep(600); // let the captured response body settle
    const putCalls = tab.answerCapture.slice(mark).filter(e => e.method === "PUT");
    record({ name: "save-put-captured", status: putCalls.length === 1 ? "pass" : "fail", detail: JSON.stringify(putCalls) });
    const afterSave = await tab.draftSnapshot();
    record({ name: "after-save-state", status: "info", detail: JSON.stringify({ savedLine: afterSave.savedLine, checked: afterSave.checkedReferences, textLength: afterSave.text?.length }) });
    await saveShot(tab, "after-save");
    await saveDraftPanelShots(tab, "after-save");
    if (putCalls.length !== 1 || putCalls[0].status !== 200) throw new Error(`expected exactly one PUT answer-draft with 200, got ${JSON.stringify(putCalls.map(p => p.status))}`);
    const putRequest = JSON.parse(putCalls[0].requestBody ?? "{}");
    const putReceipt = captureData(putCalls[0]);

    // Real refresh (page reload), then reread everything from the page.
    const markGet = tab.answerCapture.length;
    await tab.reload();
    await tab.installFinder();
    await tab.waitFor(`() => Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿'))`, { timeoutMs: 30000, label: "draft section after refresh" });
    await tab.waitFor(`() => !document.querySelector('#private-answer-text')?.disabled`, { timeoutMs: 15000, label: "textarea enabled after refresh" });
    await sleep(600);
    const getCalls = tab.answerCapture.slice(markGet).filter(e => e.method === "GET" && !e.url.includes("/references"));
    record({ name: "refresh-get-captured", status: getCalls.length >= 1 ? "pass" : "fail", detail: JSON.stringify(getCalls.map(g => ({ method: g.method, url: g.url, status: g.status }))) });
    const getBody = getCalls.length ? captureData(getCalls[getCalls.length - 1]) : null;
    const afterRefresh = await tab.draftSnapshot();
    record({ name: "after-refresh-state", status: "info", detail: JSON.stringify({ savedLine: afterRefresh.savedLine, checked: afterRefresh.checkedReferences, textLength: afterRefresh.text?.length, textMatches: afterRefresh.text === draftText }) });
    await saveShot(tab, "after-refresh");
    await saveDraftPanelShots(tab, "after-refresh");

    // Server truth from an authenticated in-page GET (same session cookie).
    const pageGet = await tab.evalJs(`fetch('/backend/api/v1/growth-tasks/${target.task.id}/answer-draft', { credentials: 'include' }).then(r => r.json()).then(j => j.data)`, { awaitPromise: true });

    // Server truth from the database itself (read-only).
    const dbRow = JSON.parse(await dbQuery(`SELECT COALESCE(json_agg(json_build_object('revision', d.revision, 'text', d.text, 'references', d."references")), '[]'::json)::text FROM growth_answer_drafts d WHERE d.growth_task_id = '${target.task.id}';`));

    const putRefs = citationIds(putReceipt.references);
    const getRefs = citationIds(getBody?.references);
    const pageGetRefs = citationIds(pageGet?.references);
    const dbRefs = citationIds(dbRow[0]?.references);
    const uiRefs = afterRefresh.checkedReferences.map(t => (t.match(/基准报告 (\S+?) ·|目标报告 (\S+?) ·/) ?? []).slice(1).filter(Boolean)[0]).filter(Boolean);

    saveJson("s1-server-truth", {
      baselineRevision, putRequest, putReceipt, getBody, pageGet, dbRow: dbRow[0] ?? null,
      uiAfterRefresh: afterRefresh, draftTextLength: draftText.length,
    });

    const checks = [
      ["put-response-200", putCalls[0].status === 200],
      ["ui-text-verbatim", afterRefresh.text === draftText],
      ["saved-line-consistent", (afterRefresh.savedLine ?? "").includes(`版本 ${putReceipt.revision}`)],
      ["get-after-refresh-matches-put", getBody !== null && getBody.text === putReceipt.text && getBody.revision === putReceipt.revision],
      ["page-get-matches-put", pageGet !== null && pageGet.text === putReceipt.text && pageGet.revision === putReceipt.revision],
      ["db-row-matches-put", dbRow.length === 1 && dbRow[0].text === putReceipt.text && dbRow[0].revision === putReceipt.revision],
      ["reference-selected-and-persisted", putRefs.includes(baseOption.citationId) && getRefs.includes(baseOption.citationId) && pageGetRefs.includes(baseOption.citationId) && dbRefs.includes(baseOption.citationId)],
      ["ui-checked-labels-show-citation", uiRefs.includes(baseOption.citationId)],
      ["no-alerts-after-refresh", (afterRefresh.alerts ?? []).length === 0],
      ["revision-expected-matches-baseline", putRequest.expectedRevision === baselineRevision],
      ["revision-receipt-is-baseline-plus-one", putReceipt.revision === baselineRevision + 1],
      ["get-after-refresh-revision-equals-receipt", getBody !== null && getBody.revision === putReceipt.revision],
    ];
    for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `putRev=${putReceipt.revision} getRev=${getBody?.revision} pageRev=${pageGet?.revision} dbRev=${dbRow[0]?.revision} putRefs=${JSON.stringify(putRefs)} getRefs=${JSON.stringify(getRefs)} dbRefs=${JSON.stringify(dbRefs)} uiRefs=${JSON.stringify(uiRefs)} textEqual=${afterRefresh.text === draftText}` });
    saveJson("s1-network-log", { network: tab.networkLog, answerDraft: tab.answerCapture });
  } finally {
    await browser.stop().catch(() => {});
  }
}

function citationIds(references) {
  if (!Array.isArray(references)) return [];
  return references.map(r => r.citationId ?? r.get?.("citationId")).filter(Boolean);
}
// Parse a captured answer-draft response envelope; null data = no draft yet.
function captureData(entry) {
  if (!entry?.responseBody || entry.responseBody === "(unavailable)") return null;
  const parsed = JSON.parse(entry.responseBody);
  return parsed?.data ?? null;
}
// Full reference identity triples for comparison (S5).
function citationIdentities(references, optionPool) {
  if (!Array.isArray(references)) return null;
  return references.map(ref => {
    const option = (optionPool ?? []).find(o => o.citationId === ref.citationId);
    return {
      citationId: ref.citationId,
      reportId: ref.reportId ?? option?.reportId ?? null,
      requirementId: ref.requirementId ?? option?.requirementId ?? null,
    };
  });
}

// ---------------------------------------------------------------------------
// Scenario 2: 清空是显式保存 (clearing only takes effect via explicit save)
// ---------------------------------------------------------------------------
async function scenarioClearExplicitSave(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);

    let { baseline, savedText } = await openDraftWithBaseline(tab, target.task.id);
    // Deterministic precondition: a non-empty saved draft (revision may have
    // been left empty by an earlier scenario run on the same own task).
    if (savedText === "") {
      const seed = `PRODUCT01-S2-前置非空草稿 ${new Date().toISOString()}`;
      await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, seed, { label: "seed text", expectValue: seed });
      await saveDraftAndAwait(tab, { expectRevision: baseline + 1 });
      baseline += 1; savedText = seed;
      record({ name: "s2-precondition-seeded", status: "info", detail: `seeded non-empty draft rev=${baseline}` });
    }

    // Step 1: only delete the text, then refresh WITHOUT saving.
    await tab.clearText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, "clear textarea (unsaved)");
    let snap = await tab.draftSnapshot();
    record({ name: "cleared-unsaved-state", status: "info", detail: JSON.stringify({ savedLine: snap.savedLine, textLength: snap.text?.length, checked: snap.checkedReferences.length }) });
    await saveDraftPanelShots(tab, "cleared-unsaved");
    const r1 = await reloadDraft(tab);
    const snapAfterRefresh1 = await tab.draftSnapshot();
    record({ name: "refresh-keeps-old-content", status: "info", detail: JSON.stringify({ textMatchesSaved: snapAfterRefresh1.text === savedText, savedLine: snapAfterRefresh1.savedLine }) });
    await saveDraftPanelShots(tab, "refresh-restores-old");

    // Step 2: clear again and explicitly save, then refresh.
    await tab.clearText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, "clear textarea (before explicit save)");
    const puts = await saveDraftAndAwait(tab, { expectRevision: baseline + 1 });
    const put = puts.find(p => p.status === 200);
    const putRequest = put ? JSON.parse(put.requestBody ?? "{}") : null;
    record({ name: "explicit-clear-save", status: !!put ? "pass" : "fail", detail: `PUT status=${put?.status} requestTextEmpty=${putRequest?.text === ""}` });
    await saveDraftPanelShots(tab, "after-clear-save");
    const r2 = await reloadDraft(tab);
    const snapAfterRefresh2 = await tab.draftSnapshot();
    record({ name: "refresh-after-clear-save", status: "info", detail: JSON.stringify({ textEmpty: snapAfterRefresh2.text === "", savedLine: snapAfterRefresh2.savedLine, checked: snapAfterRefresh2.checkedReferences }) });
    await saveDraftPanelShots(tab, "refresh-empty-saved");

    const dbRow = JSON.parse(await dbQuery(`SELECT COALESCE(json_agg(json_build_object('revision', d.revision, 'text', d.text, 'references', d."references")), '[]'::json)::text FROM growth_answer_drafts d WHERE d.growth_task_id = '${target.task.id}';`));
    saveJson("s2-server-truth", { baseline, savedTextLength: savedText.length, putRequest, refresh1: r1.data, refresh2: r2.data, dbRow: dbRow[0] ?? null, ui1: snapAfterRefresh1, ui2: snapAfterRefresh2 });

    const checks = [
      ["clear-without-save-keeps-old-on-refresh", snapAfterRefresh1.text === savedText && r1.data?.revision === baseline],
      ["explicit-clear-save-versions-bump", r2.data?.revision === baseline + 1 && putRequest?.expectedRevision === baseline],
      ["empty-text-after-explicit-save", snapAfterRefresh2.text === "" && r2.data?.text === ""],
      ["db-row-empty-and-bumped", dbRow.length === 1 && dbRow[0].text === "" && dbRow[0].revision === baseline + 1],
      ["refs-preserved-through-clear-save", citationIds(r2.data?.references).length > 0 && snapAfterRefresh2.checkedReferences.length > 0],
    ];
    for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `r1rev=${r1.data?.revision} r2rev=${r2.data?.revision} r2textLen=${r2.data?.text?.length} ui2Len=${snapAfterRefresh2.text?.length} dbRev=${dbRow[0]?.revision} r2refs=${citationIds(r2.data?.references).length}` });
    saveJson("s2-network-log", { network: tab.networkLog, answerDraft: tab.answerCapture, faults: tab.faultLog });
  } finally {
    await browser.stop().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Scenario 3: 保存中继续编辑 (keep typing while the save RECEIPT is late)
// Response-stage hold: the first PUT really reaches the server and lands
// (verified read-only mid-hold), only its 200 receipt is held back.
// ---------------------------------------------------------------------------
async function scenarioSaveInflightEdit(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await tab.useResponseStageAnswerDraft();
    await login(tab, CREDS.accounts.student);

    const { baseline } = await openDraftWithBaseline(tab, target.task.id);
    const stamp = new Date().toISOString().replace(/[:.]/g, "");
    const textV1 = `PRODUCT01-S3-保存中继续编辑基线 ${stamp}`;
    const appended = "；保存中追加的文字，回执到达后不得覆盖。";
    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, textV1, { label: "draft v1", expectValue: textV1 });

    // Hold the first PUT's RESPONSE (server already persisted at this point).
    tab.answerFaults.push({ kind: "hold-response", method: "PUT", stage: "response", exactEndpoint: true });
    const mark = tab.answerCapture.length;
    await tab.click({ tag: "button", text: "保存草稿", exact: true }, { label: "save draft (receipt will be held)" });
    const heldIdx = await tab.waitHeldResponse("PUT");
    if (heldIdx < 0) throw new Error("PUT response was never held (fault did not hit)");
    const heldEntry = tab.heldResponses[heldIdx].entry;
    record({ name: "hold-confirmed", status: heldEntry.status === 200 ? "pass" : "fail", detail: JSON.stringify(heldEntry) });

    // While the receipt is held, the server ALREADY has the save: prove it
    // with a read-only GET and the database before any release.
    const serverNow = await auth.getJson(`/growth-tasks/${target.task.id}/answer-draft`);
    const dbNow = JSON.parse(await dbQuery(`SELECT COALESCE(json_agg(json_build_object('revision', d.revision, 'text', d.text)), '[]'::json)::text FROM growth_answer_drafts d WHERE d.growth_task_id = '${target.task.id}';`));
    record({
      name: "persisted-while-held",
      status: serverNow?.revision === baseline + 1 && serverNow?.text === textV1 && dbNow[0]?.revision === baseline + 1 && dbNow[0]?.text === textV1 ? "pass" : "fail",
      detail: `GET rev=${serverNow?.revision} db rev=${dbNow[0]?.revision} textMatch=${serverNow?.text === textV1}`,
    });

    // Order step: keep editing AFTER the persisted-verified point.
    await tab.appendText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, appended, "append while receipt held");
    const duringHold = await tab.draftSnapshot();
    record({ name: "edited-while-held", status: "info", detail: JSON.stringify({ textIsV1PlusAppend: duringHold.text === textV1 + appended, savedLine: duringHold.savedLine }) });
    await saveDraftPanelShots(tab, "receipt-held");

    // Order step: release the ORIGINAL real receipt only now.
    await tab.releaseHeldResponse(heldIdx);
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return false;
      const p = Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()).find(t => t.startsWith('已保存：'));
      return !!p && p.includes('版本 ${baseline + 1}');
    })()`, { timeoutMs: 20000, label: "held receipt visible after release" });
    await sleep(600);
    const putCalls = tab.answerCapture.slice(mark).filter(e => e.method === "PUT");
    const afterReceipt = await tab.draftSnapshot();
    record({ name: "after-receipt-state", status: "info", detail: JSON.stringify({ textKeepsAppend: afterReceipt.text === textV1 + appended, savedLine: afterReceipt.savedLine }) });
    await saveDraftPanelShots(tab, "after-receipt");
    const put1 = putCalls.find(p => p.status === 200);
    const put1Request = put1 ? JSON.parse(put1.requestBody ?? "{}") : null;
    const put1Receipt = put1 ? captureData(put1) : null;

    // Next explicit save must use the server's new revision and persist the
    // full edited text.
    const puts2 = await saveDraftAndAwait(tab, { expectRevision: baseline + 2 });
    const put2 = puts2.find(p => p.status === 200);
    const put2Request = put2 ? JSON.parse(put2.requestBody ?? "{}") : null;
    const put2Receipt = put2 ? captureData(put2) : null;
    await saveDraftPanelShots(tab, "after-second-save");
    const r = await reloadDraft(tab);
    const afterRefresh = await tab.draftSnapshot();
    const dbRow = JSON.parse(await dbQuery(`SELECT COALESCE(json_agg(json_build_object('revision', d.revision, 'text', d.text)), '[]'::json)::text FROM growth_answer_drafts d WHERE d.growth_task_id = '${target.task.id}';`));

    saveJson("s3-server-truth", { baseline, textV1, appended, put1Request, put1Receipt, put2Request, put2Receipt, refresh: r.data, dbRow: dbRow[0] ?? null, uiAfterReceipt: afterReceipt, uiAfterRefresh: afterRefresh, heldEntry });

    const checks = [
      ["hold-was-response-stage-200", heldEntry.stage === "response" && heldEntry.status === 200],
      ["server-persisted-before-release", serverNow?.revision === baseline + 1 && dbNow[0]?.revision === baseline + 1],
      ["inflight-append-persisted-in-ui", afterReceipt.text === textV1 + appended],
      ["receipt-did-not-overwrite-later-typing", afterRefresh.text === textV1 + appended],
      ["dirty-shown-after-receipt", (afterReceipt.savedLine ?? "").includes("有未保存修改")],
      ["first-put-used-baseline-revision", put1Request?.expectedRevision === baseline],
      ["first-receipt-revision-baseline-plus-one", put1Receipt?.revision === baseline + 1],
      ["second-save-used-server-revision", put2Request?.expectedRevision === baseline + 1],
      ["second-receipt-persisted-appended", put2Receipt?.text === textV1 + appended && put2Receipt?.revision === baseline + 2],
      ["db-final-row-matches", dbRow.length === 1 && dbRow[0].text === textV1 + appended && dbRow[0].revision === baseline + 2],
    ];
    for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `held=${JSON.stringify(heldEntry)} srv=${serverNow?.revision} p1exp=${put1Request?.expectedRevision} p1rev=${put1Receipt?.revision} p2exp=${put2Request?.expectedRevision} p2rev=${put2Receipt?.revision} dbRev=${dbRow[0]?.revision}` });
    saveJson("s3-network-log", { network: tab.networkLog, answerDraft: tab.answerCapture, faults: tab.faultLog, held: tab.heldResponses.map(h => h.entry) });
  } finally {
    await browser.stop().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Scenario 3b: 请求阶段延迟单列覆盖 (request-stage delay, listed separately —
// covers "sending is slow"; it does NOT prove the server already persisted,
// which is what s3's response-stage hold is for).
// ---------------------------------------------------------------------------
async function scenarioRequestStageDelay(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);
    const { baseline } = await openDraftWithBaseline(tab, target.task.id);
    const stamp = new Date().toISOString().replace(/[:.]/g, "");
    const textV1 = `PRODUCT01-S3B-请求阶段延迟 ${stamp}`;
    const appended = "；请求仍在途时追加。";
    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, textV1, { label: "draft v1", expectValue: textV1 });
    tab.answerFaults.push({ kind: "delay", ms: 4500, method: "PUT", stage: "request", exactEndpoint: true });
    const mark = tab.answerCapture.length;
    await tab.click({ tag: "button", text: "保存草稿", exact: true }, { label: "save (request held)" });
    const t0 = Date.now();
    while (!(tab.faultLog.some(f => f.kind === "delay" && f.stage === "request")) && Date.now() - t0 < 5000) await sleep(100);
    record({ name: "request-delay-confirmed", status: tab.faultLog.some(f => f.kind === "delay" && f.stage === "request") ? "pass" : "fail", detail: JSON.stringify(tab.faultLog) });
    // While the REQUEST is still held, nothing has reached the server yet.
    const serverNow = await auth.getJson(`/growth-tasks/${target.task.id}/answer-draft`);
    record({ name: "not-persisted-during-request-hold", status: serverNow?.revision === baseline ? "pass" : "fail", detail: `GET rev=${serverNow?.revision} baseline=${baseline}` });
    await tab.appendText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, appended, "append while request held");
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return false;
      const p = Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()).find(t => t.startsWith('已保存：'));
      return !!p && p.includes('版本 ${baseline + 1}');
    })()`, { timeoutMs: 20000, label: "receipt after request release" });
    await sleep(600);
    const afterReceipt = await tab.draftSnapshot();
    const puts2 = await saveDraftAndAwait(tab, { expectRevision: baseline + 2 });
    const put2 = puts2.find(p => p.status === 200);
    const r = await reloadDraft(tab);
    const checks = [
      ["append-survived-request-stage-receipt", r.data?.text === textV1 + appended],
      ["second-save-revision-chain", put2 ? captureData(put2)?.revision === baseline + 2 : false],
    ];
    for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `rRev=${r.data?.revision} rTextLen=${r.data?.text?.length} wantLen=${(textV1 + appended).length}` });
    saveJson("s3b-network-log", { network: tab.networkLog, answerDraft: tab.answerCapture, faults: tab.faultLog });
  } finally {
    await browser.stop().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Scenario 5: 网络错误 (failed save keeps content; no automatic retry)
// ---------------------------------------------------------------------------
async function scenarioNetworkError(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);

    const { baseline } = await openDraftWithBaseline(tab, target.task.id);
    const stamp = new Date().toISOString().replace(/[:.]/g, "");
    const textV5 = `PRODUCT01-S5-网络失败保内容 ${stamp}`;
    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, textV5, { label: "draft text", expectValue: textV5 });

    // Clearly-marked network injection: abort the first PUT as a failure.
    tab.answerFaults.push({ kind: "fail", method: "PUT" });
    const mark = tab.answerCapture.length;
    await tab.click({ tag: "button", text: "保存草稿", exact: true }, { label: "save draft (will fail)" });
    // Wait for the error alert to appear on the page.
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && Array.from(section.querySelectorAll('[role=alert]')).some(e => (e.textContent ?? '').trim().length > 0);
    })()`, { timeoutMs: 15000, label: "failure alert visible" });
    await sleep(600);
    const failedPuts = tab.answerCapture.slice(mark).filter(e => e.method === "PUT");
    const failed = failedPuts.find(p => p.status === null || p.status >= 400);
    record({ name: "failed-put-captured", status: !!failed ? "pass" : "fail", detail: JSON.stringify(failedPuts.map(p => ({ status: p.status, bodyLen: p.requestBody?.length }))) });
    const afterFail = await tab.draftSnapshot();
    // Reference identity (reportId+requirementId+citationId) the failed save
    // carried, read back from the page after the failure.
    const failedRefs = failed?.requestBody ? citationIdentities(JSON.parse(failed.requestBody).references, target.refs) : null;
    const uiRefIds = (afterFail.checkedReferences ?? []).map(t => (t.match(/(?:基准|目标)报告 (\S+?) ·/) ?? [])[1]).filter(Boolean);
    record({ name: "after-fail-state", status: "info", detail: JSON.stringify({ textKept: afterFail.text === textV5, checkedKept: afterFail.checkedReferences.length, savedLine: afterFail.savedLine, alerts: afterFail.alerts }) });
    record({ name: "reference-identity-before-after", status: "info", detail: `failedPUT=${JSON.stringify(failedRefs)} uiChecked=${JSON.stringify(uiRefIds)}` });
    await saveDraftPanelShots(tab, "failed-save-retains");

    // Network "recovers": wait and verify NO automatic retry happened.
    await sleep(2500);
    const putCountAfterWait = tab.answerCapture.filter(e => e.method === "PUT").length;
    record({ name: "no-auto-retry", status: putCountAfterWait === failedPuts.length ? "pass" : "fail", detail: `PUT count ${putCountAfterWait} (expected ${failedPuts.length})` });

    // Only the user's own next click produces the next PUT.
    const puts2 = await saveDraftAndAwait(tab, { expectRevision: baseline + 1 });
    const ok = puts2.find(p => p.status === 200);
    const totalPuts = tab.answerCapture.filter(e => e.method === "PUT").length;
    await saveDraftPanelShots(tab, "after-retry-save");
    const r = await reloadDraft(tab);

    saveJson("s5-server-truth", { baseline, textV5, failedPut: failed ?? null, retryPut: ok ?? null, refresh: r.data, uiAfterFail: afterFail });

    const checks = [
      ["failure-alert-shown", (afterFail.alerts ?? []).length > 0],
      ["text-retained-after-failure", afterFail.text === textV5],
      ["reference-identity-retained-after-failure", Array.isArray(failedRefs) && failedRefs.length > 0 && failedRefs.every(ref => uiRefIds.includes(ref.citationId)) && uiRefIds.length === failedRefs.length],
      ["exactly-one-failed-put", failedPuts.length === 1],
      ["no-retry-without-user-click", putCountAfterWait === failedPuts.length],
      ["manual-second-click-single-put", totalPuts === 2 && !!ok],
      ["retry-saved-revision-bump", r.data?.revision === baseline + 1 && r.data?.text === textV5],
    ];
    for (const [name, ok2] of checks) record({ name, status: ok2 ? "pass" : "fail", detail: ok2 ? "" : `failed=${failedPuts.length} total=${totalPuts} rRev=${r.data?.revision} textKept=${afterFail.text === textV5} alerts=${(afterFail.alerts ?? []).length}` });
    saveJson("s5-network-log", { network: tab.networkLog, answerDraft: tab.answerCapture, faults: tab.faultLog });
  } finally {
    await browser.stop().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Scenario 4: 双窗口冲突 (two windows, same revision, 409 + explicit overwrite)
// ---------------------------------------------------------------------------
async function scenarioDualWindow409(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  // Two REAL independent windows (separate Chrome instances/profiles): tabs in
  // one browser share activation, and this app intentionally clears the draft
  // session when its tab becomes hidden (privacy behavior under test in s6).
  const browserA = new Chrome("studentA");
  const browserB = new Chrome("studentB");
  await browserA.launch();
  await browserB.launch();
  let tabA = null, tabB = null;
  try {
    tabA = await browserA.openTab();
    await tabA.enable();
    await login(tabA, CREDS.accounts.student);
    const a = await openDraftWithBaseline(tabA, target.task.id);

    // Second window of the SAME logged-in user.
    tabB = await browserB.openTab();
    await tabB.enable();
    await login(tabB, CREDS.accounts.student);
    const b = await openDraftWithBaseline(tabB, target.task.id);
    record({ name: "both-windows-baseline", status: a.baseline === b.baseline ? "pass" : "fail", detail: `A rev=${a.baseline} B rev=${b.baseline}` });

    // Window A saves first: revision N -> N+1.
    const stamp = new Date().toISOString().replace(/[:.]/g, "");
    const textA = `PRODUCT01-S4-窗口A先保存 ${stamp}`;
    const textB = `PRODUCT01-S4-窗口B基于旧版本的编辑 ${stamp}`;
    await tabA.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, textA, { label: "window A text", expectValue: textA });
    const putsA = await saveDraftAndAwait(tabA, { expectRevision: a.baseline + 1 });
    const putA = putsA.find(p => p.status === 200);
    record({ name: "window-a-saved", status: !!putA ? "pass" : "fail", detail: `PUT status=${putA?.status} rev=${captureData(putA)?.revision}` });

    // Window B still holds revision N: its save must get a real 409.
    await tabB.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, textB, { label: "window B text", expectValue: textB });
    const markB = tabB.answerCapture.length;
    await tabB.click({ tag: "button", text: "保存草稿", exact: true }, { label: "window B save (stale revision)" });
    await tabB.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && (section.textContent ?? '').includes('保存冲突');
    })()`, { timeoutMs: 15000, label: "conflict panel visible" });
    await sleep(600);
    const putB409 = tabB.answerCapture.slice(markB).filter(e => e.method === "PUT" && e.status === 409).pop();
    const putBRequest = putB409 ? JSON.parse(putB409.requestBody ?? "{}") : null;
    const putBBody = putB409?.responseBody ? JSON.parse(putB409.responseBody) : null;
    record({ name: "window-b-409", status: !!putB409 ? "pass" : "fail", detail: `PUT status=${putB409?.status} code=${putBBody?.code} expectedRevision=${putBRequest?.expectedRevision}` });
    const after409 = await tabB.draftSnapshot();
    record({ name: "after-409-state", status: "info", detail: JSON.stringify({ textKept: after409.text === textB, savedLine: after409.savedLine }) });
    await saveDraftPanelShots(tabB, "after-409");

    // Reading the server copy is comparison-only: B's edits must survive it.
    await tabB.click({ tag: "button", text: "读取服务器版本作对照" }, { label: "read server copy for comparison" });
    await tabB.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && (section.textContent ?? '').includes('服务器最新版本') && (section.textContent ?? '').includes('版本 ${a.baseline + 1}');
    })()`, { timeoutMs: 15000, label: "server copy shown for comparison" });
    await sleep(400);
    const afterCompare = await tabB.draftSnapshot();
    record({ name: "after-compare-state", status: "info", detail: JSON.stringify({ textStillB: afterCompare.text === textB, savedLine: afterCompare.savedLine }) });
    await saveDraftPanelShots(tabB, "after-compare");

    // Explicit overwrite: B saves again using the server's version number.
    await tabB.click({ tag: "button", text: "以本人编辑重新保存（使用服务器版本号）" }, { label: "explicit overwrite save" });
    await tabB.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return false;
      const p = Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()).find(t => t.startsWith('已保存：'));
      return !!p && p.includes('版本 ${a.baseline + 2}') && p.includes('与已保存内容一致');
    })()`, { timeoutMs: 20000, label: "overwrite save receipt" });
    await sleep(600);
    const putB2 = tabB.answerCapture.slice(markB).filter(e => e.method === "PUT" && e.status === 200).pop();
    const putB2Request = putB2 ? JSON.parse(putB2.requestBody ?? "{}") : null;
    const putB2Receipt = putB2 ? captureData(putB2) : null;
    await saveDraftPanelShots(tabB, "after-overwrite-save");

    const r = await reloadDraft(tabB);
    const afterRefresh = await tabB.draftSnapshot();
    const dbRow = JSON.parse(await dbQuery(`SELECT COALESCE(json_agg(json_build_object('revision', d.revision, 'text', d.text)), '[]'::json)::text FROM growth_answer_drafts d WHERE d.growth_task_id = '${target.task.id}';`));

    saveJson("s4-server-truth", { baseline: a.baseline, putA: { request: JSON.parse(putA?.requestBody ?? "{}"), receipt: captureData(putA) }, putB409: { request: putBRequest, body: putBBody }, putB2: { request: putB2Request, receipt: putB2Receipt }, refresh: r.data, dbRow: dbRow[0] ?? null });

    const checks = [
      ["windows-read-same-revision", a.baseline === b.baseline],
      ["window-a-save-ok", !!putA && captureData(putA)?.revision === a.baseline + 1],
      ["window-b-real-409", !!putB409 && putBBody?.code === 4240 && putBRequest?.expectedRevision === a.baseline],
      ["b-edits-preserved-after-409", after409.text === textB],
      ["compare-does-not-replace-edits", afterCompare.text === textB],
      ["explicit-overwrite-saves-b-text", putB2Receipt?.text === textB && putB2Receipt?.revision === a.baseline + 2],
      ["overwrite-used-server-revision", putB2Request?.expectedRevision === a.baseline + 1],
      ["final-refresh-and-db-match", r.data?.text === textB && r.data?.revision === a.baseline + 2 && dbRow[0]?.text === textB && dbRow[0]?.revision === a.baseline + 2],
    ];
    for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `aRev=${a.baseline} bRev=${b.baseline} b409=${putB409?.status}/${putBBody?.code} b2rev=${putB2Receipt?.revision} rRev=${r.data?.revision} dbRev=${dbRow[0]?.revision}` });
    saveJson("s4-network-log", { networkA: tabA.networkLog, networkB: tabB.networkLog, answerDraftB: tabB.answerCapture });
  } finally {
    await browserA.stop().catch(() => {});
    await browserB.stop().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Scenario 11: 真390px视口 (real 390px viewport, controls visible, no overflow)
// ---------------------------------------------------------------------------
async function scenarioViewport390(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  // A desktop window bumps the revision; the 390px window holds the stale
  // revision so the conflict controls are really rendered at 390px too.
  const browserDesk = new Chrome("studentDesk");
  const browser390 = new Chrome("student390", { width: 420, height: 900 });
  await browserDesk.launch();
  await browser390.launch();
  let tabDesk = null, tab390 = null;
  try {
    tabDesk = await browserDesk.openTab();
    await tabDesk.enable();
    await login(tabDesk, CREDS.accounts.student);
    const desk = await openDraftWithBaseline(tabDesk, target.task.id);

    tab390 = await browser390.openTab();
    await tab390.enable();
    await tab390.setViewport(390, 844);
    await login(tab390, CREDS.accounts.student);
    const mob = await openDraftWithBaseline(tab390, target.task.id);
    record({ name: "390-baselines", status: desk.baseline === mob.baseline ? "pass" : "fail", detail: `desk rev=${desk.baseline} 390 rev=${mob.baseline}` });

    // Desktop saves first (N -> N+1).
    const stamp = new Date().toISOString().replace(/[:.]/g, "");
    const textDesk = `PRODUCT01-S11-桌面先保存 ${stamp}`;
    const text390 = `PRODUCT01-S11-390窗口旧版本编辑 ${stamp}`;
    await tabDesk.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, textDesk, { label: "desktop text", expectValue: textDesk });
    await saveDraftAndAwait(tabDesk, { expectRevision: desk.baseline + 1 });

    // At 390px: type, save, hit the 409 conflict — all controls must stay
    // visible and the long reference paths must not overflow horizontally.
    await tab390.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, text390, { label: "390 text", expectValue: text390 });
    await tab390.click({ tag: "button", text: "保存草稿", exact: true }, { label: "390 save (stale)" });
    await tab390.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && (section.textContent ?? '').includes('保存冲突');
    })()`, { timeoutMs: 15000, label: "conflict visible at 390px" });
    await sleep(400);

    const metrics390 = await tab390.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const visible = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.x >= -1 && r.x + r.width <= window.innerWidth + 1; };
      const textarea = document.querySelector('#private-answer-text');
      const buttons = {};
      for (const b of Array.from((section ?? document).querySelectorAll('button'))) buttons[b.textContent.trim()] = visible(b);
      return {
        viewport: { w: window.innerWidth, h: window.innerHeight },
        docNoHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
        sectionNoHorizontalOverflow: !!section && section.scrollWidth <= section.clientWidth,
        longReferenceLabelsContained: !!section && Array.from(section.querySelectorAll('fieldset li label')).every(l => l.scrollWidth <= l.clientWidth + 1),
        textareaVisible: visible(textarea),
        buttons,
      };
    })()`);
    record({ name: "390-metrics", status: "info", detail: JSON.stringify(metrics390) });
    await saveDraftPanelShots(tab390, "390-conflict");

    // The conflict controls must be usable at 390px: compare then overwrite.
    await tab390.click({ tag: "button", text: "读取服务器版本作对照" }, { label: "390 compare" });
    await tab390.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && (section.textContent ?? '').includes('服务器最新版本');
    })()`, { timeoutMs: 15000, label: "server copy at 390px" });
    await tab390.click({ tag: "button", text: "以本人编辑重新保存（使用服务器版本号）" }, { label: "390 overwrite save" });
    await tab390.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return false;
      const p = Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()).find(t => t.startsWith('已保存：'));
      return !!p && p.includes('版本 ${desk.baseline + 2}') && p.includes('与已保存内容一致');
    })()`, { timeoutMs: 20000, label: "390 overwrite receipt" });
    await saveDraftPanelShots(tab390, "390-after-overwrite");

    const dbRow = JSON.parse(await dbQuery(`SELECT COALESCE(json_agg(json_build_object('revision', d.revision, 'text', d.text)), '[]'::json)::text FROM growth_answer_drafts d WHERE d.growth_task_id = '${target.task.id}';`));
    saveJson("s11-viewport-metrics", { metrics390, deskBaseline: desk.baseline, dbRow: dbRow[0] ?? null });

    const neededButtons = ["保存草稿", "重读已保存草稿", "读取服务器版本作对照", "以本人编辑重新保存（使用服务器版本号）"];
    const checks = [
      ["viewport-really-390", metrics390.viewport.w === 390],
      ["no-document-horizontal-overflow", metrics390.docNoHorizontalOverflow],
      ["no-section-horizontal-overflow", metrics390.sectionNoHorizontalOverflow],
      ["long-reference-labels-contained", metrics390.longReferenceLabelsContained],
      ["textarea-visible", metrics390.textareaVisible],
      ["save-reload-preview-controls-visible", !!metrics390.buttons["保存草稿"] && !!metrics390.buttons["重读已保存草稿"]],
      ["conflict-controls-visible", !!metrics390.buttons["读取服务器版本作对照"] && !!metrics390.buttons["以本人编辑重新保存（使用服务器版本号）"]],
      ["390-overwrite-persisted", dbRow.length === 1 && dbRow[0].text === text390 && dbRow[0].revision === desk.baseline + 2],
    ];
    for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `vp=${JSON.stringify(metrics390.viewport)} doc=${metrics390.docNoHorizontalOverflow} sec=${metrics390.sectionNoHorizontalOverflow} btn=${JSON.stringify(metrics390.buttons)} dbRev=${dbRow[0]?.revision}` });
    saveJson("s11-network-log", { network390: tab390.networkLog, answerDraft390: tab390.answerCapture });
  } finally {
    await browserDesk.stop().catch(() => {});
    await browser390.stop().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Scenario 12: 旧状态不变 (draft ops leave deliveries/replies/notifications
// and analysis/usage untouched; A/B/A2 snapshots still match the fixture)
// ---------------------------------------------------------------------------
function canonicalHash(jsonText) {
  return new Promise((resolve, reject) => {
    const child = spawn("python", ["-c",
      "import sys,json,hashlib;o=json.loads(sys.stdin.read());print(hashlib.sha256(json.dumps(o,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest())"],
      { stdio: ["pipe", "pipe", "ignore"] });
    let out = "";
    child.stdout.on("data", chunk => { out += String(chunk); });
    child.on("error", reject);
    child.on("exit", code => code === 0 ? resolve(out.trim()) : reject(new Error(`python hash exit ${code}`)));
    child.stdin.write(jsonText);
    child.stdin.end();
  });
}
async function captureInvariance(label) {
  const appRows = [];
  for (const line of (await dbQuery("SELECT id::text||'|'||status||'|'||report_snapshot::text FROM applications ORDER BY created_at;")).split("\n").filter(Boolean)) {
    const [id, status, ...rest] = line.split("|");
    appRows.push({ id, status, snapshotSha256: await canonicalHash(rest.join("|")) });
  }
  const events = await dbQuery("SELECT id::text||'|'||application_id::text||'|'||event_type FROM application_events ORDER BY created_at;");
  const notifications = await dbQuery("SELECT id::text||'|'||recipient_id::text FROM notifications ORDER BY created_at;");
  const analysisCount = await dbQuery("SELECT count(*) FROM analysis_tasks;");
  const usageCount = await dbQuery("SELECT count(*) FROM ai_usage_logs;");
  return {
    label, at: new Date().toISOString(),
    appRows, eventsRowCount: events.split("\n").filter(Boolean).length,
    notificationsRowCount: notifications.split("\n").filter(Boolean).length,
    analysisTasks: Number(analysisCount), aiUsageLogs: Number(usageCount),
  };
}
async function scenarioOldStateUnchanged(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const before = await captureInvariance("before-draft-save");
  saveJson("s12-invariance-before", before);

  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);
    const { baseline } = await openDraftWithBaseline(tab, target.task.id);
    const marker = `PRODUCT01-S12-草稿操作不改旧状态 ${new Date().toISOString().replace(/[:.]/g, "")}`;
    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, marker, { label: "draft text", expectValue: marker });
    const puts = await saveDraftAndAwait(tab, { expectRevision: baseline + 1 });
    record({ name: "s12-draft-saved", status: puts.some(p => p.status === 200) ? "pass" : "fail", detail: `rev ${baseline} -> ${baseline + 1}` });
    await saveDraftPanelShots(tab, "after-save");
  } finally {
    await browser.stop().catch(() => {});
  }

  const after = await captureInvariance("after-draft-save");
  saveJson("s12-invariance-after", after);

  const fixture = CREDS.applications ?? {};
  const fixtureMatch = ["A", "B", "A2"].every(key => {
    const expected = fixture[key];
    const row = after.appRows.find(r => r.id === expected?.id);
    return expected && row && row.snapshotSha256 === expected.snapshotSha256;
  });
  const checks = [
    ["applications-unchanged", JSON.stringify(before.appRows) === JSON.stringify(after.appRows)],
    ["application-events-unchanged", before.eventsRowCount === after.eventsRowCount],
    ["notifications-unchanged", before.notificationsRowCount === after.notificationsRowCount],
    ["analysis-count-unchanged", before.analysisTasks === after.analysisTasks],
    ["ai-usage-unchanged", before.aiUsageLogs === after.aiUsageLogs],
    ["ab-a2-snapshots-match-fixture", fixtureMatch],
  ];
  for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `before=${JSON.stringify(before)} after=${JSON.stringify(after)}` });
}

// ---------------------------------------------------------------------------
// Scenario 6: 隐私与迟到响应 (identity/hidden tabs never receive stale data)
// ---------------------------------------------------------------------------
async function scenarioIdentityLate(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const browser = new Chrome("student");
  await browser.launch();
  let tab1 = null, tab2 = null;
  let hiddenState = null, lateState = null;
  let marker = "";
  try {
    tab1 = await browser.openTab();
    await tab1.enable();
    await tab1.useResponseStageAnswerDraft();
    await login(tab1, CREDS.accounts.student);
    const { baseline } = await openDraftWithBaseline(tab1, target.task.id);
    marker = `PRODUCT01-S6-身份与迟到回执 ${new Date().toISOString().replace(/[:.]/g, "")}`;
    await tab1.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, marker, { label: "marker text", expectValue: marker });
    await saveDraftAndAwait(tab1, { expectRevision: baseline + 1 });

    // Reload with the draft GET's RESPONSE held: the server answered with the
    // marker content, but the page has not received it yet.
    tab1.answerFaults.push({ kind: "hold-response", method: "GET", stage: "response", exactEndpoint: true });
    await tab1.reload();
    await tab1.installFinder();
    await tab1.waitFor(`() => Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿'))`, { timeoutMs: 30000, label: "draft section after reload" });
    const heldIdx = await tab1.waitHeldResponse("GET");
    if (heldIdx < 0) throw new Error("draft GET response was never held");
    record({ name: "get-hold-confirmed", status: tab1.heldResponses[heldIdx].entry.status === 200 ? "pass" : "fail", detail: JSON.stringify(tab1.heldResponses[heldIdx].entry) });

    // Hide the page like a real user switching tabs: a second tab in the same
    // browser window takes activation, document becomes hidden, the draft
    // session clears itself.
    tab2 = await browser.openTab("about:blank");
    await sleep(800);
    const hiddenSnapshot = await tab1.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const textarea = section ? section.querySelector('#private-answer-text') : null;
      const p = section ? Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()) : [];
      return {
        href: location.href,
        visibility: document.visibilityState,
        sectionCount: document.querySelectorAll('section').length,
        h2Texts: Array.from(document.querySelectorAll('section h2')).map(h => (h.textContent ?? '').trim()).slice(0, 6),
        text: textarea ? textarea.value : null,
        hasSavedLine: p.some(t => t.startsWith('已保存：')),
        bodyHasMarker: (document.body.innerText ?? '').includes(${JSON.stringify(marker.slice(0, 24))}),
      };
    })()`);
    hiddenState = hiddenSnapshot;
    record({ name: "hidden-state-cleared", status: "info", detail: JSON.stringify(hiddenState) });

    // Order step: release the late receipt ONLY after the identity/visibility
    // change; a disposed session must discard it. The product unmounts the
    // whole workspace while hidden (GrowthWorkspace clears task state), so the
    // assertion is about the DOM never containing the draft content.
    await tab1.releaseHeldResponse(heldIdx);
    await sleep(1000);
    lateState = await tab1.evalJs(`(() => ({
      visibility: document.visibilityState,
      sectionCount: document.querySelectorAll('section').length,
      bodyHasMarker: (document.body.innerText ?? '').includes(${JSON.stringify(marker.slice(0, 24))}),
    }))()`);
    record({ name: "late-receipt-discarded", status: lateState && !lateState.bodyHasMarker ? "pass" : "fail", detail: JSON.stringify(lateState) });

    // The same user coming back restores the draft from the server.
    await browser.send("Target.activateTarget", { targetId: tab1.targetId });
    await tab1.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return false;
      const p = Array.from(section.querySelectorAll('p')).map(x => x.textContent.trim()).find(t => t.startsWith('已保存：'));
      return !!p && p.includes('版本 ${baseline + 1}');
    })()`, { timeoutMs: 20000, label: "own draft restored on return" });
    await sleep(500);
    const restored = await tab1.draftSnapshot();
    record({ name: "restored-from-server", status: restored.text === marker ? "pass" : "fail", detail: `textLen=${restored.text?.length} wantLen=${marker.length} savedLine=${restored.savedLine}` });
    await saveDraftPanelShots(tab1, "restored");
  } finally {
    await browser.stop().catch(() => {});
  }

  // Another real identity in its own window opens the student's task page.
  const browser2 = new Chrome("studentA2");
  await browser2.launch();
  let a2State = null;
  try {
    const tab = await browser2.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.studentA2);
    await tab.goto(`${FRONTEND}/growth/${target.task.id}`);
    await tab.installFinder();
    await sleep(1200);
    a2State = await tab.evalJs(`(() => ({
      hasDraftSection: Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿')),
      bodyHasMarker: (document.body.innerText ?? '').includes(${JSON.stringify(marker.slice(0, 24))}),
      errorText: Array.from(document.querySelectorAll('[role=alert]')).map(e => e.textContent.trim()).filter(Boolean).slice(0, 2),
    }))()`);
    record({ name: "a2-page-no-student-draft", status: a2State && !a2State.hasDraftSection && !a2State.bodyHasMarker ? "pass" : "fail", detail: JSON.stringify(a2State) });
    await saveShot(tab, "a2-task-page", false);
  } finally {
    await browser2.stop().catch(() => {});
  }

  // API cross-checks: another student gets 404, the enterprise gets 403.
  const a2Auth = await apiLogin(CREDS.accounts.studentA2);
  const a2Status = await a2Auth.status(`/growth-tasks/${target.task.id}/answer-draft`);
  const entAuth = await apiLogin(CREDS.accounts.enterprise);
  const entStatus = await entAuth.status(`/growth-tasks/${target.task.id}/answer-draft`);
  record({ name: "api-cross-identity", status: "info", detail: `studentA2 GET -> ${a2Status}; enterprise GET -> ${entStatus}` });

  saveJson("s6-summary", { heldEntry: tab1 ? tab1.heldResponses.map(h => h.entry) : [], hiddenState, lateState, restoredTextLen: marker.length, a2State, a2Status, entStatus });
  const checks = [
    // The workspace unmounts its content while hidden: no draft text, no
    // saved line, nothing belonging to the draft anywhere in the DOM.
    ["hidden-clears-draft-session", !!hiddenState && hiddenState.visibility === "hidden" && !hiddenState.hasSavedLine && (hiddenState.text === null || hiddenState.text === "") && !hiddenState.bodyHasMarker],
    ["late-receipt-not-applied-while-hidden", !!lateState && !lateState.bodyHasMarker],
    ["own-return-restores-draft", true], // recorded above as restored-from-server
    ["other-user-page-shows-no-draft", a2State && !a2State.hasDraftSection && !a2State.bodyHasMarker],
    ["other-user-api-404", a2Status === 404],
    ["enterprise-api-403", entStatus === 403],
  ];
  for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `hidden=${JSON.stringify(hiddenState)} late=${JSON.stringify(lateState)} a2=${a2Status} ent=${entStatus}` });
}

// ---------------------------------------------------------------------------
// Scenario 7: 原要求与跨岗位 (options stay bound to the task's original
// requirement; cross-job target options require the ORIGINAL requirement)
// ---------------------------------------------------------------------------
async function scenarioRequirementCrossJob(preflighted) {
  const { auth, tasks } = preflighted;
  const infos = [];
  for (const task of tasks) {
    const refs = await auth.getJson(`/growth-tasks/${task.id}/answer-draft/references`).catch(() => null);
    if (Array.isArray(refs) && refs.length) infos.push({ task, refs });
  }
  const crossJob = infos.find(i => i.task.targetReportId && i.task.targetJobId !== i.task.jobId && i.refs.every(r => r.reportKind === "base"));
  const sameJob = infos.find(i => i.task.targetReportId && i.task.targetJobId === i.task.jobId && i.refs.some(r => r.reportKind === "target"));
  if (!crossJob) throw new Error("no completed cross-job task with base-only options found");
  record({ name: "same-job-task-available", status: sameJob ? "pass" : "blocked", detail: sameJob ? `taskId=${sameJob.task.id} targetOptions=${sameJob.refs.filter(r => r.reportKind === "target").length}` : "no completed same-job task with target-report options; same-job page part cannot be verified in this run" });

  const browser = new Chrome("student");
  await browser.launch();
  const pageFacts = {};
  try {
    const tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);
    for (const [label, info] of [["crossJob", crossJob], ...(sameJob ? [["sameJob", sameJob]] : [])]) {
      await openDraftSection(tab, info.task.id);
      await sleep(400);
      pageFacts[label] = await tab.evalJs(`(() => {
        const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
        if (!section) return null;
        const legend = section.querySelector('fieldset legend');
        const labels = Array.from(section.querySelectorAll('fieldset li label')).map(l => (l.textContent ?? '').trim());
        return {
          legend: legend ? legend.textContent.trim() : null,
          baseOptions: labels.filter(t => t.includes('基准报告')).length,
          targetOptions: labels.filter(t => t.includes('目标报告')).length,
          crossJobNote: (section.textContent ?? '').includes('跨岗位说明'),
          referenceScopeNotice: (section.textContent ?? '').includes('跨岗位的新要求不能用来回答原问题'),
        };
      })()`);
      record({ name: `page-facts:${label}`, status: "info", detail: JSON.stringify({ taskId: info.task.id, ...pageFacts[label] }) });
      await saveDraftPanelShots(tab, `s7-${label}`);
    }
  } finally {
    await browser.stop().catch(() => {});
  }

  const crossJobDetail = await auth.getJson(`/growth-tasks/${crossJob.task.id}`);
  const crossOk = crossJob.refs.every(r => r.requirementId === crossJobDetail.requirementId);
  // Task with base-only options is the CROSS-JOB one here: its saved target
  // job differs and the target report lacks the original requirement, so no
  // target options may appear — a same-name skill can never be a source. The
  // task WITH target options is the same-job completed-target case.
  const checks = [
    ["crossjob-base-options-from-frozen-snapshot", crossOk && (pageFacts.crossJob?.baseOptions ?? 0) > 0],
    ["crossjob-legend-shows-original-requirement", (pageFacts.crossJob?.legend ?? "").includes(crossJob.task.requirementTitle)],
    ["crossjob-no-target-options-without-original-requirement", (pageFacts.crossJob?.targetOptions ?? 1) === 0],
    ["crossjob-scope-explanation-shown", !!pageFacts.crossJob?.referenceScopeNotice],
    ["crossjob-note-shown", !!pageFacts.crossJob?.crossJobNote],
  ];
  if (sameJob) {
    const sameJobDetail = await auth.getJson(`/growth-tasks/${sameJob.task.id}`);
    const targetRefs = sameJob.refs.filter(r => r.reportKind === "target");
    checks.push(
      ["samejob-completed-target-has-original-requirement-options", targetRefs.length > 0 && (pageFacts.sameJob?.targetOptions ?? 0) > 0],
      ["samejob-target-options-use-original-requirement", targetRefs.every(r => r.requirementId === sameJobDetail.requirementId)],
      ["samejob-legend-still-original-requirement", (pageFacts.sameJob?.legend ?? "").includes(sameJob.task.requirementTitle)],
      ["samejob-not-marked-crossjob", !pageFacts.sameJob?.crossJobNote],
    );
  } else {
    checks.push(["samejob-completed-target-page-part-not-run-this-time", false]);
  }
  saveJson("s7-options", { crossJob: { taskId: crossJob.task.id, requirementId: crossJobDetail.requirementId, refs: crossJob.refs }, ...(sameJob ? { sameJob: { taskId: sameJob.task.id, refs: sameJob.refs } } : {}), pageFacts });
  for (const [name, ok] of checks) record({ name, status: ok ? "pass" : (name.startsWith("crossjob-page-part") ? "blocked" : "fail"), detail: ok ? "" : JSON.stringify(pageFacts).slice(0, 300) });
}

// ---------------------------------------------------------------------------
// Scenario 10: 预览确认复制 (preview first; clipboard only on explicit copy,
// with a real failure+retry path; zero external sends)
// ---------------------------------------------------------------------------
async function scenarioPreviewCopy(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const baseOption = target.refs.find(r => r.reportKind === "base");
  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  // Clipboard evidence here is a PAGE-INJECTED simulated implementation
  // (counting, failable, restorable). Browser.grantPermissions is NOT used —
  // changing browser/site permission settings is outside the task boundary —
  // so real OS-clipboard acceptance stays explicitly unverified by this run.
  const installShim = async () => tab.evalJs(`(() => {
    if (!window.__e2eClipboard) {
      window.__e2eClipboard = { writes: [], mode: "record" };
      navigator.clipboard.writeText = (text) => {
        const s = window.__e2eClipboard;
        if (s.mode === "fail") return Promise.reject(new DOMException("denied", "NotAllowedError"));
        s.writes.push(String(text));
        return Promise.resolve();
      };
    }
    return true;
  })()`);
  const shimFacts = () => tab.evalJs(`(() => ({ count: window.__e2eClipboard ? window.__e2eClipboard.writes.length : -1, lastLen: window.__e2eClipboard && window.__e2eClipboard.writes.length ? window.__e2eClipboard.writes[window.__e2eClipboard.writes.length - 1].length : null }))()`);
  try {
    tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);
    const { baseline } = await openDraftWithBaseline(tab, target.task.id);
    const marker = `PRODUCT01-S10-预览确认复制 ${new Date().toISOString().replace(/[:.]/g, "")}`;
    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, marker, { label: "draft text", expectValue: marker });
    await saveDraftAndAwait(tab, { expectRevision: baseline + 1 });

    // Install the counting shim BEFORE the preview ever opens.
    await installShim();
    await tab.click({ tag: "summary", text: "预览已保存草稿" }, { label: "open preview" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const pre = section && section.querySelector('details pre');
      return !!pre && (pre.textContent ?? '').includes(${JSON.stringify(marker.slice(0, 24))});
    })()`, { timeoutMs: 15000, label: "preview document shown" });
    await sleep(400);
    const writesAtPreview = await shimFacts();
    const previewText = await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return section ? (section.querySelector('details pre')?.textContent ?? null) : null;
    })()`);
    record({ name: "preview-opened-simulated-clipboard", status: "evidence", detail: `clipboardWritesDuringPreviewOpen=${writesAtPreview.count} previewLen=${previewText?.length}（剪贴板为页面注入模拟实现，非系统剪贴板）` });
    await saveDraftPanelShots(tab, "preview-open");

    // Explicit confirmation: only this click writes the clipboard (shim).
    await tab.click({ tag: "button", text: "复制草稿（仅写入本机剪贴板）" }, { label: "confirm copy" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && (section.textContent ?? '').includes('已复制到本机剪贴板');
    })()`, { timeoutMs: 15000, label: "copy success notice" });
    await sleep(300);
    const writesAfterCopy = await shimFacts();
    const copiedText = await tab.evalJs(`window.__e2eClipboard.writes[window.__e2eClipboard.writes.length - 1]`);
    const copyMatches = typeof copiedText === "string" && copiedText === previewText;
    record({ name: "copy-success-simulated", status: copyMatches ? "pass" : "fail", detail: `writes=${writesAfterCopy.count} copiedLen=${copiedText?.length} previewLen=${previewText?.length}（模拟剪贴板写入内容比对）` });
    await saveDraftPanelShots(tab, "after-copy");

    // Failure path: switch the shim into failing mode (injected clipboard
    // fault), click copy again, content/preview must stay with a retry hint.
    await tab.evalJs(`(() => { window.__e2eClipboard.mode = "fail"; return true; })()`);
    await tab.click({ tag: "button", text: "复制草稿（仅写入本机剪贴板）" }, { label: "copy (will fail)" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && Array.from(section.querySelectorAll('[role=alert]')).some(e => (e.textContent ?? '').includes('复制失败'));
    })()`, { timeoutMs: 15000, label: "copy failure alert" });
    await sleep(300);
    const failState = await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return null;
      const pre = section.querySelector('details pre');
      const alertTexts = Array.from(section.querySelectorAll('[role=alert]')).map(e => e.textContent.trim());
      return { previewStillPresent: !!pre && (pre.textContent ?? '').includes(${JSON.stringify(marker.slice(0, 24))}), alertTexts, retryHint: alertTexts.some(t => t.includes('可重试')) };
    })()`);
    const writesAtFail = await shimFacts();
    const textKept = (await tab.draftSnapshot()).text === marker;
    record({ name: "copy-failure-state", status: "info", detail: JSON.stringify({ ...failState, textKept, writesAtFail: writesAtFail.count }) });
    await saveDraftPanelShots(tab, "copy-failed");

    // Manual retry after the implementation recovers: user clicks again.
    await tab.evalJs(`(() => { window.__e2eClipboard.mode = "record"; return true; })()`);
    await tab.click({ tag: "button", text: "复制草稿（仅写入本机剪贴板）" }, { label: "manual retry copy" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && (section.textContent ?? '').includes('已复制到本机剪贴板');
    })()`, { timeoutMs: 15000, label: "retry copy success notice" });
    await sleep(300);
    const writesAfterRetry = await shimFacts();
    const retryText = await tab.evalJs(`window.__e2eClipboard.writes[window.__e2eClipboard.writes.length - 1]`);
    record({ name: "manual-retry-copy-success", status: writesAfterRetry.count === 2 && retryText === previewText ? "pass" : "fail", detail: `writes=${writesAfterRetry.count} retryLen=${retryText?.length}` });

    // 390px viewport: the confirm-copy control must stay visible and usable.
    await tab.setViewport(390, 844);
    await sleep(400);
    const copyButton390 = await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const btn = section && Array.from(section.querySelectorAll('button')).find(b => (b.textContent ?? '').includes('复制草稿'));
      if (!btn) return null;
      const r = btn.getBoundingClientRect();
      return { visible: r.width > 0 && r.height > 0 && r.x >= -1 && r.x + r.width <= window.innerWidth + 1, viewportW: window.innerWidth, text: btn.textContent.trim() };
    })()`);
    record({ name: "copy-button-visible-at-390", status: copyButton390?.visible === true && copyButton390.viewportW === 390 ? "pass" : "fail", detail: JSON.stringify(copyButton390) });
    await saveDraftPanelShots(tab, "390-confirm-copy");
    const writesBefore390Click = (await shimFacts()).count;
    await tab.click({ tag: "button", text: "复制草稿（仅写入本机剪贴板）" }, { label: "copy at 390" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && (section.textContent ?? '').includes('已复制到本机剪贴板');
    })()`, { timeoutMs: 15000, label: "390 copy success notice" });
    const writesAfter390Click = await shimFacts();
    record({ name: "copy-usable-at-390", status: writesAfter390Click.count === writesBefore390Click + 1 ? "pass" : "fail", detail: `writes ${writesBefore390Click} -> ${writesAfter390Click.count}` });

    // All observed traffic stays on loopback: zero external sends.
    const nonLocal = tab.networkLog.filter(e => /^https?:/.test(e.url) && !/127\.0\.0\.1/.test(e.url)).map(e => e.url);

    saveJson("s10-summary", { simulatedClipboard: true, previewLen: previewText?.length, writesTimeline: { atPreview: writesAtPreview.count, afterCopy: writesAfterCopy.count, atFail: writesAtFail.count, afterRetry: writesAfterRetry.count, after390: writesAfter390Click.count }, failState, nonLocal });
    const checks = [
      ["preview-write-count-zero", writesAtPreview.count === 0],
      ["preview-contains-required-parts", !!previewText && previewText.includes(marker.slice(0, 24)) && previewText.includes(baseOption.citationId) && previewText.includes(target.task.requirementTitle.slice(0, 12))],
      ["copy-writes-only-on-explicit-confirm", writesAfterCopy.count === 1 && copyMatches],
      ["failure-keeps-content", textKept],
      ["failure-keeps-preview", !!failState?.previewStillPresent],
      ["failure-shows-retry-hint", !!failState?.retryHint],
      ["failure-adds-no-extra-writes", writesAtFail.count === 1],
      ["manual-retry-succeeds", writesAfterRetry.count === 2],
      ["copy-confirm-visible-and-usable-at-390", copyButton390?.visible === true && copyButton390.viewportW === 390 && writesAfter390Click.count === writesBefore390Click + 1],
      ["zero-external-network-sends", nonLocal.length === 0],
    ];
    for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `timeline=${JSON.stringify({ atPreview: writesAtPreview.count, afterCopy: writesAfterCopy.count, atFail: writesAtFail.count, afterRetry: writesAfterRetry.count })} preview=${previewText?.length} fail=${JSON.stringify(failState)} btn390=${JSON.stringify(copyButton390)} nonLocal=${JSON.stringify(nonLocal.slice(0, 3))}` });
    saveJson("s10-network-log", { network: tab.networkLog, answerDraft: tab.answerCapture, faults: tab.faultLog });
  } finally {
    await browser.stop().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Scenario 6b: 同浏览器身份切换竞态 (same page session: old identity's held
// receipt is released only AFTER a real logout + login as another user)
// ---------------------------------------------------------------------------
async function scenarioIdentitySwitchRace(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await tab.useResponseStageAnswerDraft();
    await login(tab, CREDS.accounts.student);
    const { baseline } = await openDraftWithBaseline(tab, target.task.id);
    const marker = `PRODUCT01-S6B-同浏览器身份切换竞态 ${new Date().toISOString().replace(/[:.]/g, "")}`;
    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, marker, { label: "marker text", expectValue: marker });
    await saveDraftAndAwait(tab, { expectRevision: baseline + 1 });

    // The page reloads; its draft GET response (old identity's receipt, with
    // the marker content) is held at the response stage.
    tab.answerFaults.push({ kind: "hold-response", method: "GET", stage: "response", exactEndpoint: true });
    await tab.reload();
    await tab.installFinder();
    await tab.waitFor(`() => Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿'))`, { timeoutMs: 30000, label: "draft section after reload" });
    const heldIdx = await tab.waitHeldResponse("GET");
    if (heldIdx < 0) throw new Error("draft GET response was never held");
    record({ name: "s6b-get-hold-confirmed", status: tab.heldResponses[heldIdx].entry.status === 200 ? "pass" : "fail", detail: JSON.stringify(tab.heldResponses[heldIdx].entry) });

    // REAL logout through the page header, then a REAL login as studentA2 in
    // the SAME tab — the identity changes while the old receipt is in flight.
    await tab.click({ tag: "button", text: "退出", exact: true }, { label: "logout" });
    await tab.waitFor(`() => location.pathname === "/" || !document.querySelector('header button')`, { timeoutMs: 15000, label: "logged out to home" });
    await sleep(600);
    await login(tab, CREDS.accounts.studentA2);
    const identity = await tab.evalJs(`(() => ({ path: location.pathname, displayName: document.querySelector('header span.max-w-28')?.textContent?.trim() ?? null, hasStudentNav: !!(document.querySelector('header a[href="/portfolio"]')) }))()`);
    record({ name: "s6b-identity-switched", status: "info", detail: JSON.stringify(identity) });
    // Identity proof: both fixture accounts share the same display name, so a
    // header name never proves who is logged in. The only trustworthy
    // in-browser evidence is the REAL current-user answer (/users/me, the
    // product's own identity endpoint) fetched by the current page session
    // same-origin with the page's own cookies. Only userId/role are recorded
    // — never tokens, cookies or emails.
    const me = await tab.evalJs(`(async () => {
      const r = await fetch('/backend/api/v1/users/me', { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      if (!r.ok) return { ok: false, status: r.status };
      const j = await r.json();
      const u = j?.data ?? {};
      return { ok: true, userId: typeof u.id === 'string' ? u.id : null, role: u.role ?? null };
    })()`, { awaitPromise: true });
    const meIsA2 = me?.ok === true && me.userId === CREDS.accounts.studentA2.userId;
    record({ name: "s6b-authme-userid-is-a2", status: meIsA2 && me.role === "student" ? "pass" : "fail", detail: `authMeUserIdMatchesA2=${meIsA2} role=${me?.role ?? "?"} (两个账号显示名相同，不以显示名作身份证明；displayed="${identity.displayName}")` });

    // Release the OLD identity's receipt only now: it must not display into
    // or overwrite the new identity's page. After the logout navigation the
    // interception is typically already dead — the receipt physically cannot
    // be delivered — and that outcome is recorded as evidence, not an error.
    const releaseOutcome = await tab.releaseHeldResponse(heldIdx);
    record({ name: "s6b-release-outcome", status: "evidence", detail: `outcome=${releaseOutcome} entry=${JSON.stringify(tab.heldResponses[heldIdx].entry)}` });
    await sleep(1500);
    const leak = await tab.evalJs(`(() => ({
      bodyHasMarker: (document.body.innerText ?? '').includes(${JSON.stringify(marker.slice(0, 24))}),
      displayName: document.querySelector('header span.max-w-28')?.textContent?.trim() ?? null,
    }))()`);
    // If the context SURVIVED (legal SPA navigation kept the interception
    // alive), the old receipt really was delivered to the page — the pass
    // condition then proves the race is safe (delivered but not displayed).
    // If the context died, delivery is impossible and that fact stands as-is.
    record({ name: "s6b-old-receipt-no-leak", status: leak && !leak.bodyHasMarker ? "pass" : "fail", detail: `released=${releaseOutcome} ${JSON.stringify(leak)}` });

    // The new identity's own growth list works, has no draft panel/preview
    // and shows no trace of the old marker.
    await tab.goto(`${FRONTEND}/growth`);
    await tab.installFinder();
    await sleep(1200);
    const growthA2 = await tab.evalJs(`(() => ({
      hasDraftSection: Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿')),
      hasPreviewSection: (document.body.innerText ?? '').includes('预览已保存草稿'),
      bodyHasMarker: (document.body.innerText ?? '').includes(${JSON.stringify(marker.slice(0, 24))}),
      emptyList: (document.body.innerText ?? '').includes('暂无补证任务'),
    }))()`);
    record({ name: "s6b-a2-growth-page", status: growthA2 && !growthA2.hasDraftSection && !growthA2.hasPreviewSection && !growthA2.bodyHasMarker ? "pass" : "fail", detail: JSON.stringify(growthA2) });
    await saveShot(tab, "a2-growth-after-release", false);
    saveJson("s6b-summary", { heldEntry: tab.heldResponses.map(h => h.entry), identity, authMe: { matchesA2: meIsA2, role: me?.role ?? null }, releaseOutcome, leak, growthA2 });
  } finally {
    await browser.stop().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Scenario 8: 引用失效 (real 409 re-selection boundary on a COMPLETED
// analysis with frozen state + clearly-marked GET degradation injection)
// ---------------------------------------------------------------------------
async function scenarioInvalidReference(preflighted) {
  const { auth, tasks } = preflighted;
  const target = await selectDraftTarget(auth, tasks);
  const taskId = target.task.id;

  // --- Part A: real re-selection request must be rejected with 409 -----
  const rowBefore = await dbQuery(`SELECT materials::text||'|'||COALESCE(target_job_id::text,'-')||'|'||COALESCE(analysis_task_id::text,'-')||'|'||status FROM evidence_growth_tasks WHERE id='${taskId}';`);
  const detail = await auth.getJson(`/growth-tasks/${taskId}`);
  const analysisStatus = await dbQuery(`SELECT status::text FROM analysis_tasks WHERE id='${detail.analysisTaskId}';`);
  record({ name: "s8-analysis-status", status: "info", detail: `analysisTask=${detail.analysisTaskId} status=${analysisStatus}` });
  // A genuine re-selection attempt carrying the task's CURRENT materials.
  const payload = {
    resumeVersionId: detail.materials.find(m => m.kind === "resume")?.id,
    projectVersionIds: detail.materials.filter(m => m.kind === "project").map(m => m.id),
    ...(detail.targetJobId ? { targetJobId: detail.targetJobId } : {}),
  };
  const attach = await auth.putStatus(`/growth-tasks/${taskId}/materials`, payload);
  const rowAfter = await dbQuery(`SELECT materials::text||'|'||COALESCE(target_job_id::text,'-')||'|'||COALESCE(analysis_task_id::text,'-')||'|'||status FROM evidence_growth_tasks WHERE id='${taskId}';`);
  const draftNow = await auth.getJson(`/growth-tasks/${taskId}/answer-draft`);
  record({ name: "s8-reselect-409", status: attach.status === 409 ? "pass" : "fail", detail: `PUT materials -> ${attach.status} code=${attach.code}` });
  record({ name: "s8-frozen-state-unchanged", status: rowBefore === rowAfter ? "pass" : "fail", detail: `taskRowEqual=${rowBefore === rowAfter} draftRev=${draftNow?.revision}` });

  // --- Page: the re-selection controls are locked in the UI -------------
  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await tab.useResponseStageAnswerDraft();
    await login(tab, CREDS.accounts.student);
    await openDraftSection(tab, taskId);
    await sleep(500);
    const uiLock = await tab.evalJs(`(() => {
      const fieldset = Array.from(document.querySelectorAll('fieldset')).find(f => (f.textContent ?? '').includes('目标岗位') && f.querySelector('summary'));
      return { found: !!fieldset, disabled: fieldset ? fieldset.disabled === true : null };
    })()`);
    record({ name: "s8-ui-reselect-locked", status: uiLock.found && uiLock.disabled === true ? "pass" : (uiLock.found ? "fail" : "blocked"), detail: JSON.stringify(uiLock) });
    await saveShot(tab, "s8-ui-locked", false);

    // Save a clean known draft so the degraded GET has a concrete victim.
    const marker = `PRODUCT01-S8-引用失效降级 ${new Date().toISOString().replace(/[:.]/g, "")}`;
    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, marker, { label: "draft text", expectValue: marker });
    await saveDraftAndAwait(tab, {});
    const serverDraft = await auth.getJson(`/growth-tasks/${taskId}/answer-draft`);
    const degradedCitation = serverDraft.references[0];
    const snippetPrefix = String(degradedCitation?.snippet ?? "").slice(0, 16);

    // --- Part B: clearly-marked GET degradation injection ---------------
    // Reload with the draft GET fulfilled from the server body with
    // references[0] degraded to available=false + snippet=null. The database
    // and the server's own GET stay untouched — proven below. Both bodies
    // (the server's original receipt and the injected one the page actually
    // received) are snapshotted and written to separate evidence files.
    const injectionReceipts = {
      serverOriginal: { captured: false, status: null, body: null },
      injected: { captured: false, status: null, body: null },
    };
    tab.answerFaults.push({
      kind: "modify-response", method: "GET", stage: "response", exactEndpoint: true,
      transform: body => {
        injectionReceipts.serverOriginal.body = JSON.parse(JSON.stringify(body));
        injectionReceipts.serverOriginal.captured = true;
        const data = body?.data;
        if (data && Array.isArray(data.references) && data.references.length) {
          data.references = data.references.map((r, i) => i === 0 ? { ...r, available: false, snippet: null } : r);
        }
        injectionReceipts.injected.body = body;
        injectionReceipts.injected.captured = true;
        return body;
      },
    });
    await tab.reload();
    await tab.installFinder();
    await tab.waitFor(`() => Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent ?? '').includes('私人回答草稿'))`, { timeoutMs: 30000, label: "draft section after injected GET" });
    await tab.waitFor(`() => !document.querySelector('#private-answer-text')?.disabled`, { timeoutMs: 15000, label: "textarea enabled after injected GET" });
    await sleep(600);
    const degraded = await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return null;
      const text = section.querySelector('#private-answer-text')?.value ?? null;
      // Informational only: the orphan block / 移除 button belong to options
      // that vanished from the list; a degraded-but-still-listed citation
      // legitimately shows neither. Assertions below never require them.
      const orphanBlock = (section.textContent ?? '').includes('已保存但当前不可选的引用');
      const removeButton = Array.from(section.querySelectorAll('button')).find(b => (b.textContent ?? '').trim() === '移除');
      const targetBox = Array.from(section.querySelectorAll('fieldset input[type=checkbox]'))
        .find(b => ((b.closest('label')?.textContent ?? '')).includes(${JSON.stringify(degradedCitation.citationId)}));
      return { text, orphanBlock, hasRemoveButton: !!removeButton, targetOptionFound: !!targetBox, targetChecked: targetBox ? targetBox.checked : null, targetLabel: targetBox ? (targetBox.closest('label')?.textContent ?? '').trim() : null };
    })()`);
    record({ name: "s8-injected-degradation", status: "evidence", detail: `fault=${JSON.stringify(tab.faultLog.filter(f => f.kind === "modify-response"))} page=${JSON.stringify(degraded)}` });
    // Server truth read WHILE the page shows the degraded body: proves the
    // injection never left the browser (identity + availability + snippet).
    const serverDuringDegradation = await auth.getJson(`/growth-tasks/${taskId}/answer-draft`);
    saveJson("s8-server-get-receipt", { note: "server original body read via Fetch.getResponseBody before transform", captured: injectionReceipts.serverOriginal.captured, body: injectionReceipts.serverOriginal.body });
    saveJson("s8-injected-get-receipt", { note: "body fulfilled to the page by the marked modify-response fault", captured: injectionReceipts.injected.captured, faultLog: tab.faultLog.filter(f => f.kind === "modify-response"), body: injectionReceipts.injected.body });
    await saveDraftPanelShots(tab, "injected-degraded");

    // Preview + copy must exclude the invalid source's original text.
    await tab.evalJs(`(() => {
      if (!window.__e2eClipboard) {
        window.__e2eClipboard = { writes: [], mode: "record" };
        navigator.clipboard.writeText = (text) => { const s = window.__e2eClipboard; if (s.mode === "fail") return Promise.reject(new DOMException("denied", "NotAllowedError")); s.writes.push(String(text)); return Promise.resolve(); };
      }
      return true;
    })()`);
    await tab.click({ tag: "summary", text: "预览已保存草稿" }, { label: "open preview (degraded)" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const pre = section && section.querySelector('details pre');
      return !!pre && (pre.textContent ?? '').length > 0;
    })()`, { timeoutMs: 15000, label: "preview shown (degraded)" });
    await sleep(400);
    const previewText = await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return section ? (section.querySelector('details pre')?.textContent ?? null) : null;
    })()`);
    await tab.click({ tag: "button", text: "复制草稿（仅写入本机剪贴板）" }, { label: "copy (degraded, simulated clipboard)" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && ((section.textContent ?? '').includes('已复制到本机剪贴板') || Array.from(section.querySelectorAll('[role=alert]')).some(e => (e.textContent ?? '').includes('复制失败')));
    })()`, { timeoutMs: 15000, label: "copy outcome (degraded)" });
    await sleep(300);
    const copiedText = await tab.evalJs(`window.__e2eClipboard ? window.__e2eClipboard.writes[window.__e2eClipboard.writes.length - 1] ?? null : null`);
    record({ name: "s8-preview-copy-exclude-invalid", status: "evidence", detail: `previewHasInvalidSection=${!!previewText && previewText.includes("已失效引用")} previewHasSnippet=${!!previewText && snippetPrefix.length > 0 && previewText.includes(snippetPrefix)} copiedEqualsPreview=${copiedText === previewText}` });
    await saveDraftPanelShots(tab, "degraded-preview-copy");

    // Explicit removal restores normal operation: the degraded citation is
    // still a listed option here (degradation keeps the identity, the orphan
    // block is only for options that vanished), so removing it is a real
    // uncheck of its checkbox followed by an explicit save.
    await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const box = section && Array.from(section.querySelectorAll('fieldset input[type=checkbox]'))
        .find(b => ((b.closest('label')?.textContent ?? '')).includes(${JSON.stringify(degradedCitation.citationId)}));
      if (!box) return false;
      box.scrollIntoView({ block: 'center' });
      window.__e2eClickEl = box;
      return true;
    })()`);
    if (!(await tab.evalJs("!!window.__e2eClickEl"))) throw new Error(`degraded citation checkbox not found: ${degradedCitation.citationId}`);
    await tab.clickStored(`(() => window.__e2eClickEl && window.__e2eClickEl.isConnected)()`, "uncheck degraded citation");
    await sleep(300);
    // The click targets an UNCHECK; Space is only the fallback when the click
    // landed without changing the state (still checked). Pressing it when the
    // uncheck already succeeded would re-check the box.
    if (await tab.evalJs("window.__e2eClickEl.checked")) {
      await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
      await tab.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
      await sleep(300);
    }
    const uncheckedOk = !(await tab.evalJs("window.__e2eClickEl.checked"));
    if (!uncheckedOk) throw new Error(`degraded citation still checked after real uncheck: ${degradedCitation.citationId}`);
    const afterRemove = await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      if (!section) return null;
      const checked = Array.from(section.querySelectorAll('fieldset input[type=checkbox]'))
        .filter(b => b.checked).map(b => (b.closest('label')?.textContent ?? '').trim());
      return { targetUnchecked: window.__e2eClickEl && window.__e2eClickEl.isConnected ? window.__e2eClickEl.checked === false : null, checkedLabels: checked, textKept: section.querySelector('#private-answer-text')?.value ?? null };
    })()`);
    const serverRev = (await auth.getJson(`/growth-tasks/${taskId}/answer-draft`)).revision;
    const puts = await saveDraftAndAwait(tab, { expectRevision: serverRev + 1 });
    await saveDraftPanelShots(tab, "after-remove-save");
    const serverAfter = await auth.getJson(`/growth-tasks/${taskId}/answer-draft`);

    // Identity-level comparison (never count-only): the target triple must be
    // gone from the saved draft, every other citation triple must survive,
    // and the body text must be untouched.
    const triple = r => `${r.reportId ?? ""}|${r.requirementId ?? ""}|${r.citationId ?? ""}`;
    const beforeTriples = (serverDraft.references ?? []).map(triple);
    const targetTriple = triple(degradedCitation);
    const afterTriples = (serverAfter.references ?? []).map(triple);
    const targetRemovedByIdentity = !afterTriples.includes(targetTriple);
    const othersKeptByIdentity = beforeTriples.filter(t => t !== targetTriple).every(t => afterTriples.includes(t)) && afterTriples.length === beforeTriples.length - 1;
    const serverDuringTriple = triple((serverDuringDegradation.references ?? [])[0] ?? {});
    const serverSnippetIntact = String((serverDuringDegradation.references ?? [])[0]?.snippet ?? "") === String(degradedCitation?.snippet ?? "");

    saveJson("s8-summary", {
      partA: { attach, rowBefore, rowAfter, analysisStatus, draftRevision: draftNow?.revision },
      partB: {
        degradedCitationId: degradedCitation?.citationId, targetTriple, faultLog: tab.faultLog, degraded,
        previewHasInvalidSection: previewText?.includes("已失效引用"), snippetExcluded: !(previewText ?? "").includes(snippetPrefix), copiedEqualsPreview: copiedText === previewText,
        afterRemove, beforeTriples, afterTriples, targetRemovedByIdentity, othersKeptByIdentity,
        serverDuringDegradation: { revision: serverDuringDegradation.revision, firstTriple: serverDuringTriple, firstAvailableFalse: (serverDuringDegradation.references ?? [])[0]?.available === false, snippetIntact: serverSnippetIntact },
      },
    });
    const checks = [
      ["reselect-rejected-real-409", attach.status === 409 && attach.code === 4099],
      ["frozen-task-row-unchanged", rowBefore === rowAfter],
      ["ui-reselect-controls-locked", uiLock.found && uiLock.disabled === true],
      ["degraded-page-keeps-text", degraded?.text === marker],
      ["degraded-citation-still-listed-option", degraded?.targetOptionFound === true],
      ["preview-marks-invalid-and-drops-snippet", !!previewText && previewText.includes("已失效引用") && !(snippetPrefix.length > 0 && previewText.includes(snippetPrefix))],
      ["copy-excludes-invalid-source", copiedText === previewText],
      ["injection-receipts-both-captured", injectionReceipts.serverOriginal.captured && injectionReceipts.injected.captured],
      ["server-truth-untouched-by-injection", serverDuringTriple === targetTriple && (serverDuringDegradation.references ?? [])[0]?.available !== false && serverSnippetIntact],
      ["remove-drops-target-triple", targetRemovedByIdentity && puts.some(p => p.status === 200)],
      ["remove-keeps-other-citations-and-text", othersKeptByIdentity && serverAfter.text === marker],
    ];
    for (const [name, ok] of checks) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `attach=${JSON.stringify(attach)} uiLock=${JSON.stringify(uiLock)} degraded=${JSON.stringify(degraded)} preview=${previewText?.slice(0, 80)} copied=${copiedText?.slice(0, 80)} afterRemove=${JSON.stringify(afterRemove)} srvRefs=${serverAfter.references.length}/${serverDraft.references.length}` });
    saveJson("s8-network-log", { network: tab.networkLog, answerDraft: tab.answerCapture, faults: tab.faultLog });
  } finally {
    await browser.stop().catch(() => {});
  }
}


// ---------------------------------------------------------------------------
// Scenario 9: 第三方参考 (material_role=reference upload → Mock report →
// dedicated task whose draft keeps the third-party identity through
// edit/save/refresh/preview/copy; then the task's own real re-selection 409
// after its analysis is bound — separate from S8's network injection)
// ---------------------------------------------------------------------------
async function scenarioThirdPartyReference(preflighted) {
  const { auth } = preflighted;
  const MATERIALS_DIR_S9 = path.join(EVIDENCE_DIR, "materials");
  const REF_ZIP = path.join(MATERIALS_DIR_S9, "reference-project.zip");
  const REF_NAME = "reference-project.zip";
  const REF_PROJECT_TITLE = "E2E第三方参考材料（合成）";
  const STATE_FILE = path.join(EVIDENCE_DIR, "s9-state.json");
  const loadS9State = () => { try { return JSON.parse(fs.readFileSync(STATE_FILE, "utf8")); } catch { return {}; } };
  const saveS9State = patch => {
    const next = { ...loadS9State(), ...patch, updatedAt: new Date().toISOString() };
    fs.writeFileSync(STATE_FILE, JSON.stringify(next, null, 2));
    return next;
  };
  if (!fs.existsSync(REF_ZIP)) throw new Error(`synthetic reference fixture missing: ${REF_ZIP}`);

  // Read-only accounting snapshot: analysis/usage/notifications row counts.
  const accounting = async label => {
    const analysis = await dbQuery("SELECT count(*) FROM analysis_tasks;");
    const usage = await dbQuery("SELECT count(*) FROM ai_usage_logs;");
    const notifications = await dbQuery("SELECT count(*) FROM notifications;");
    return { label, analysisTasks: Number(analysis), aiUsageLogs: Number(usage), notifications: Number(notifications) };
  };
  const beforeAny = await accounting("before");
  record({ name: "s9-accounting-before", status: "info", detail: JSON.stringify(beforeAny) });

  const browser = new Chrome("student");
  await browser.launch();
  let tab = null;
  try {
    tab = await browser.openTab();
    await tab.enable();
    await login(tab, CREDS.accounts.student);

    // --- Part A: upload the marked reference material through the real UI --
    await tab.goto(`${FRONTEND}/portfolio`);
    await tab.installFinder();
    await tab.waitFor(`() => document.querySelector('#project-file') !== null`, { timeoutMs: 30000, label: "project upload form" });
    const alreadyParsed = await tab.evalJs(`Array.from(document.querySelectorAll('article')).some(a => a.textContent.includes(${JSON.stringify(REF_NAME)}) && a.textContent.includes('预览解析内容'))`);
    if (alreadyParsed) {
      record({ name: "s9-upload-skipped", status: "info", detail: "reference material card already parsed from an earlier s9 run" });
    } else {
      await tab.fillText({ tag: "input", attr: "placeholder", attrValue: "如：校园二手交易平台" }, REF_PROJECT_TITLE, { label: "reference project name", expectValue: REF_PROJECT_TITLE });
      await tab.fillText({ tag: "textarea", attr: "placeholder", attrValue: "你负责了什么，解决了什么问题" }, "合成第三方参考：仅用于检索与学习建议验证，不计入本人贡献（S9专用，全部内容合成编写）。", { label: "reference project description" });
      await tab.setFileInput("#project-file", REF_ZIP);
      // Check the reference role radio with a real click; Space is only the
      // fallback when the click landed without changing the state.
      await tab.evalJs(`(() => {
        const radio = document.querySelector('input[name="material-role"][value="reference"]');
        if (!radio) return false;
        radio.scrollIntoView({ block: 'center' });
        window.__e2eClickEl = radio;
        return true;
      })()`);
      if (!(await tab.evalJs("!!window.__e2eClickEl"))) throw new Error("material-role reference radio not found");
      await tab.clickStored(`(() => window.__e2eClickEl && window.__e2eClickEl.isConnected)()`, "material-role reference radio");
      await sleep(300);
      if (!(await tab.evalJs("window.__e2eClickEl.checked"))) {
        await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
        await tab.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
        await sleep(300);
      }
      const roleChecked = await tab.evalJs("window.__e2eClickEl.checked");
      record({ name: "s9-material-role-reference-checked", status: roleChecked === true ? "pass" : "fail", detail: `radio checked=${roleChecked}` });
      await saveShot(tab, "s9-reference-form", false);
      await tab.click({ tag: "button", text: "创建项目并开始扫描" }, { label: "create reference project" });
      await tab.waitFor(`() => Array.from(document.querySelectorAll('article')).some(a => a.textContent.includes(${JSON.stringify(REF_NAME)}) && a.textContent.includes('预览解析内容'))`, { timeoutMs: 180000, pollMs: 1000, label: "reference parse complete" });
    }
    const cardText = await tab.evalJs(`Array.from(document.querySelectorAll('article')).filter(a => a.textContent.includes(${JSON.stringify(REF_NAME)})).map(a => a.innerText.replace(/\\n+/g, ' | ')).join(' ;; ')`);
    record({ name: "s9-card-shows-reference-role", status: cardText.includes("第三方参考") ? "pass" : "fail", detail: cardText.slice(0, 300) });
    await saveShot(tab, "s9-reference-card", false);
    // Upload itself runs a parse analysis (portfolio upload creates its own
    // AnalysisTask): snapshot right after the upload so the match report's
    // delta below is measured against the correct stage baseline.
    const uploadAnalysisHref = await tab.evalJs(`(() => {
      const card = Array.from(document.querySelectorAll('article')).find(a => a.textContent.includes(${JSON.stringify(REF_NAME)}));
      const link = card && Array.from(card.querySelectorAll('a')).find(a => /^\\/tasks\\//.test(a.getAttribute('href') ?? ''));
      return link ? link.getAttribute('href') : null;
    })()`);
    const afterUpload = await accounting("after-upload");
    record({ name: "s9-upload-accounting", status: "info", detail: `uploadAnalysis=${uploadAnalysisHref ?? "n/a"} ${JSON.stringify(afterUpload)} (delta vs before: analysis +${afterUpload.analysisTasks - beforeAny.analysisTasks})` });

    // --- Part A2: Mock match report on job B including the reference material
    const jobs = (await auth.getJson("/jobs")).items ?? [];
    const jobB = jobs.find(j => (j.title ?? "").includes("E2E 岗位B") && j.status === "published");
    if (!jobB) throw new Error("published E2E job B not found for the match report");
    record({ name: "s9-job-b", status: "info", detail: `jobId=${jobB.id} title=${jobB.title}` });

    const state9 = loadS9State();
    let s9ReportId = null, s9AnalysisId = null, reportReused = false;
    if (state9.s9ReportId) {
      const stillThere = await auth.getJson(`/match-reports/${state9.s9ReportId}`).then(() => true).catch(() => false);
      if (stillThere) {
        s9ReportId = state9.s9ReportId;
        s9AnalysisId = state9.s9AnalysisId ?? null;
        reportReused = true;
        record({ name: "s9-report-reused", status: "info", detail: `report ${s9ReportId} from s9-state (earlier run; no new analysis expected)` });
      }
    }
    if (!s9ReportId) {
      await tab.goto(`${FRONTEND}/jobs/${jobB.id}`);
      await tab.installFinder();
      await tab.waitFor(`() => document.body.innerText.includes('用我的材料分析岗位匹配')`, { timeoutMs: 30000, label: "job match form" });
      // Resume: the existing personal resume version by original filename.
      await tab.clickStored(`(() => {
        const summary = Array.from(document.querySelectorAll('summary')).find(s => s.textContent.includes('选择简历版本') || s.textContent.includes('更换简历版本'));
        if (!summary) return false;
        const details = summary.closest('details'); if (!details || details.open === false) details.open = true;
        const radio = Array.from(details.querySelectorAll('input[type=radio]')).find(r => (r.getAttribute('aria-label') || '').includes('resume-v2.txt'));
        if (!radio) return false;
        radio.scrollIntoView({ block: 'center' }); window.__e2eClickEl = radio; return true;
      })()`, "resume radio resume-v2.txt");
      await sleep(250);
      // Project: open the picker programmatically (a real click on its
      // <summary> would toggle the just-opened <details> closed again), then
      // really click the reference version's checkbox.
      const pickerOpened = await tab.evalJs(`(() => {
        const summary = Array.from(document.querySelectorAll('summary')).find(s => s.textContent.includes('选择或更换项目版本'));
        if (!summary) return false;
        const details = summary.closest('details'); if (!details) return false;
        if (details.open === false) details.open = true;
        details.scrollIntoView({ block: 'center' });
        return true;
      })()`);
      if (!pickerOpened) throw new Error("project picker summary/details not found");
      await sleep(250);
      await tab.evalJs(`(() => {
        const summaries = Array.from(document.querySelectorAll('summary')).filter(s => s.textContent.includes('个版本'));
        for (const s of summaries) { const d = s.closest('details'); if (d) d.open = true; }
        return summaries.length;
      })()`);
      await sleep(200);
      await tab.clickStored(`(() => {
        const box = Array.from(document.querySelectorAll('input[type=checkbox]')).find(b => (b.closest('label')?.textContent || '').includes(${JSON.stringify(REF_NAME)}) && (b.closest('label')?.textContent || '').includes('第'));
        if (!box) return false;
        box.scrollIntoView({ block: 'center' }); window.__e2eClickEl = box; return true;
      })()`, `reference project checkbox ${REF_NAME}`);
      await sleep(250);
      if (!(await tab.evalJs("window.__e2eClickEl.checked"))) {
        await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
        await tab.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
        await sleep(250);
      }
      record({ name: "s9-reference-selected-in-match-form", status: (await tab.evalJs("window.__e2eClickEl.checked")) === true ? "pass" : "fail", detail: REF_NAME });
      await tab.waitFor(`() => Array.from(document.querySelectorAll('ul[aria-label="已选项目版本"] li')).some(li => li.textContent.includes(${JSON.stringify(REF_NAME)}))`, { timeoutMs: 15000, label: "reference version listed as selected" });
      await tab.clickStored(`(() => {
        const box = Array.from(document.querySelectorAll('input[type=checkbox]')).find(b => (b.closest('label')?.textContent || '').includes('同意将脱敏后的必要片段发送给外部 AI'));
        if (!box) return false;
        box.scrollIntoView({ block: 'center' }); window.__e2eClickEl = box; return true;
      })()`, "external ai consent");
      await sleep(200);
      if (!(await tab.evalJs("window.__e2eClickEl.checked"))) {
        await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
        await tab.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
        await sleep(200);
      }
      await saveShot(tab, "s9-match-form-filled", false);
      await tab.click({ tag: "button", text: "生成我的匹配报告" }, { label: "create s9 match report" });
      await tab.waitFor(`() => location.pathname.startsWith('/tasks/')`, { timeoutMs: 20000, label: "s9 analysis task page" });
      await sleep(1000);
      s9AnalysisId = await tab.evalJs("location.pathname.split('/')[2]");
      await tab.waitFor(`() => document.body.innerText.includes('处理完成') || document.body.innerText.includes('处理失败')`, { timeoutMs: 240000, pollMs: 2000, label: "s9 analysis settle (Mock)" });
      const taskBody = await tab.bodyText();
      if (!taskBody.includes("处理完成")) throw new Error(`s9 analysis failed: ${taskBody.slice(0, 300)}`);
      await tab.click({ tag: "a", text: "查看匹配报告" }, { label: "open s9 report" });
      await tab.waitFor(`() => /^\\/reports\\/[0-9a-f-]{36}$/.test(location.pathname)`, { timeoutMs: 20000, label: "s9 report page" });
      await sleep(1200);
      s9ReportId = await tab.evalJs("location.pathname.split('/')[2]");
      record({ name: "s9-report-generated", status: "pass", detail: `report=${s9ReportId} analysisTask=${s9AnalysisId} (Mock, 新报告生成单独记账)` });
      saveS9State({ jobIdB: jobB.id, s9AnalysisId, s9ReportId, refProjectTitle: REF_PROJECT_TITLE, refFile: REF_NAME });
    }
    // On the reuse path the tab is still on /portfolio: navigate to the real
    // report page so the evidence shot and the task-start click happen there.
    if (!/\/reports\//.test(await tab.evalJs("location.pathname"))) {
      await tab.goto(`${FRONTEND}/reports/${s9ReportId}`);
      await tab.installFinder();
      await tab.waitFor(`() => document.querySelectorAll('article[id^="requirement-"]').length > 0`, { timeoutMs: 30000, label: "s9 report items (reused)" });
      await sleep(600);
    }
    await saveShot(tab, "s9-report-page", false);
    const afterReport = await accounting("after-report");
    const reportDelta = afterReport.analysisTasks - afterUpload.analysisTasks;
    record({
      name: "s9-report-accounting",
      status: reportDelta === (reportReused ? 0 : 1) ? "pass" : "fail",
      detail: `afterUpload=${JSON.stringify(afterUpload)} afterReport=${JSON.stringify(afterReport)} 报告阶段分析delta=+${reportDelta}（${reportReused ? "复用已有报告，预期+0" : "新报告，预期+1"}；usage delta=+${afterReport.aiUsageLogs - afterUpload.aiUsageLogs}，notifications delta=+${afterReport.notifications - afterUpload.notifications}）`,
    });

    // --- Part B: dedicated task from the s9 report + draft keeps identity --
    await tab.clickStored(`(() => {
      const article = document.querySelector('article[id^="requirement-"]');
      if (!article) return false;
      const btn = Array.from(article.querySelectorAll('button')).find(b => b.textContent.includes('从这条缺口创建或打开补证任务'));
      if (!btn) return false;
      btn.scrollIntoView({ block: 'center' }); window.__e2eClickEl = btn; return true;
    })()`, "s9 task start button");
    await tab.waitFor(`() => document.body.innerText.includes('具体交付物') || document.body.innerText.includes('打开这条缺口已有补证任务')`, { timeoutMs: 15000, label: "s9 task start form" });
    let s9TaskId = null;
    if ((await tab.bodyText()).includes("打开这条缺口已有补证任务")) {
      await tab.click({ tag: "a", text: "打开这条缺口已有补证任务 →" }, { label: "open existing s9 task" });
      await tab.waitFor(`() => location.pathname.startsWith('/growth/')`, { timeoutMs: 20000, label: "redirect to existing s9 task" });
      await sleep(1200);
      await tab.installFinder();
      s9TaskId = await tab.evalJs("location.pathname.split('/')[2]");
      record({ name: "s9-task-existing-opened", status: "info", detail: `task ${s9TaskId} (dedup: same report+requirement returns the original task)` });
    }
    if (!s9TaskId) {
      // Fresh creation: the three plan textareas (deliverable rows=3, then
      // steps/checks rows=4), same structure the student runner drives.
      await tab.clickFocusStored(`(() => { const t = Array.from(document.querySelectorAll('form textarea')).find(x => x.rows === 3); if (!t) return false; window.__e2eClickEl = t; t.scrollIntoView({ block: 'center' }); return true; })()`, "s9 deliverable");
      await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
      await tab.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
      await tab.send("Input.insertText", { text: "合成检索示例梳理：fetch_category_totals 的输入输出与边界（第三方参考，仅供学习，不作为本人实现）。" });
      await sleep(150);
      await tab.clickFocusStored(`(() => { const all = Array.from(document.querySelectorAll('form textarea')).filter(x => x.rows === 4); if (!all.length) return false; window.__e2eClickEl = all[0]; all[0].scrollIntoView({ block: 'center' }); return true; })()`, "s9 steps");
      await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
      await tab.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
      await tab.send("Input.insertText", { text: "1. 阅读第三方参考片段并总结汇总逻辑；2. 对照本人材料说明差异（仅为学习路径，非本人贡献）。" });
      await sleep(150);
      await tab.clickFocusStored(`(() => { const all = Array.from(document.querySelectorAll('form textarea')).filter(x => x.rows === 4); if (all.length < 2) return false; window.__e2eClickEl = all[1]; all[1].scrollIntoView({ block: 'center' }); return true; })()`, "s9 checks");
      await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
      await tab.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
      await tab.send("Input.insertText", { text: "核对草稿与预览始终标注第三方参考身份；本人贡献文字保持原样。" });
      await sleep(150);
      await saveShot(tab, "s9-task-form-filled", false);
      await tab.click({ tag: "button", text: "保存并进入补证" }, { label: "save s9 task" });
      await tab.waitFor(`() => location.pathname.startsWith('/growth/')`, { timeoutMs: 20000, label: "redirect to s9 growth task" });
      await sleep(1000);
      await tab.installFinder();
      s9TaskId = await tab.evalJs("location.pathname.split('/')[2]");
      record({ name: "s9-task-created", status: "pass", detail: `task ${s9TaskId} from report ${s9ReportId} (专用任务)` });
    }
    saveS9State({ s9TaskId });

    // Draft: server-side options must carry provenance=reference for the
    // reference material's citations; the page labels must say 第三方参考.
    const options = await auth.getJson(`/growth-tasks/${s9TaskId}/answer-draft/references`);
    const refOptions = (Array.isArray(options) ? options : []).filter(o => o.provenance === "reference");
    record({ name: "s9-reference-options-with-provenance", status: refOptions.length > 0 ? "pass" : "fail", detail: `total=${Array.isArray(options) ? options.length : "n/a"} reference=${refOptions.length} first=${JSON.stringify(refOptions[0] ?? null).slice(0, 220)}` });
    if (!refOptions.length) throw new Error("no provenance=reference citation options on the s9 task");
    const refOption = refOptions[0];

    await openDraftSection(tab, s9TaskId);
    const marker = `PRODUCT01-S9-第三方参考草稿 ${new Date().toISOString().replace(/[:.]/g, "")}`;
    await tab.fillText({ tag: "textarea", attr: "id", attrValue: "private-answer-text" }, marker, { label: "s9 draft text", expectValue: marker });
    await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const box = section && Array.from(section.querySelectorAll('fieldset input[type=checkbox]'))
        .find(b => ((b.closest('label')?.textContent ?? '')).includes(${JSON.stringify(refOption.citationId)}) && ((b.closest('label')?.textContent ?? '')).includes('第三方参考'));
      if (!box) return false;
      box.scrollIntoView({ block: 'center' });
      window.__e2eClickEl = box;
      return true;
    })()`);
    if (!(await tab.evalJs("!!window.__e2eClickEl"))) throw new Error(`reference citation checkbox not found: ${refOption.citationId}`);
    // The visible label carries citationId + the third-party marker (reportId
    // /requirementId are not rendered), so the UI-level match is by label;
    // the FULL identity triple is asserted against the server draft below
    // (draft-saves-reference-triple), which is the authoritative check.
    const optionLabel = await tab.evalJs("(window.__e2eClickEl.closest('label')?.textContent ?? '').trim()");
    record({ name: "s9-option-label-marks-third-party", status: optionLabel.includes("第三方参考") ? "pass" : "fail", detail: optionLabel.slice(0, 200) });
    await tab.clickStored(`(() => window.__e2eClickEl && window.__e2eClickEl.isConnected)()`, "check reference citation");
    await sleep(300);
    if (!(await tab.evalJs("window.__e2eClickEl.checked"))) {
      await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
      await tab.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
      await sleep(300);
    }
    record({ name: "s9-reference-checkbox-checked", status: (await tab.evalJs("window.__e2eClickEl.checked")) === true ? "pass" : "fail", detail: refOption.citationId });

    const putsB = await saveDraftAndAwait(tab, {});
    const serverDraftB = await auth.getJson(`/growth-tasks/${s9TaskId}/answer-draft`);
    const savedRef = (serverDraftB.references ?? []).find(r => r.citationId === refOption.citationId) ?? null;
    const tripleS9 = r => `${r.reportId ?? ""}|${r.requirementId ?? ""}|${r.citationId ?? ""}`;
    const snippetPrefixS9 = String(savedRef?.snippet ?? "").slice(0, 16);

    // Real refresh, then reread from page + server.
    const reloaded = await reloadDraft(tab);
    const refreshed = await tab.draftSnapshot();
    const refreshedServer = await auth.getJson(`/growth-tasks/${s9TaskId}/answer-draft`);
    const refreshedRef = (refreshedServer.references ?? []).find(r => r.citationId === refOption.citationId) ?? null;

    // Preview + simulated clipboard: third-party identity text and the
    // snippet must survive; the copy equals the preview (simulated writes
    // only — never claimed to be the system clipboard).
    await tab.evalJs(`(() => {
      if (!window.__e2eClipboard) {
        window.__e2eClipboard = { writes: [], mode: "record" };
        navigator.clipboard.writeText = (text) => { const s = window.__e2eClipboard; if (s.mode === "fail") return Promise.reject(new DOMException("denied", "NotAllowedError")); s.writes.push(String(text)); return Promise.resolve(); };
      }
      return true;
    })()`);
    await tab.click({ tag: "summary", text: "预览已保存草稿" }, { label: "open preview (s9)" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      const pre = section && section.querySelector('details pre');
      return !!pre && (pre.textContent ?? '').length > 0;
    })()`, { timeoutMs: 15000, label: "preview shown (s9)" });
    await sleep(400);
    const previewTextS9 = await tab.evalJs(`(() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return section ? (section.querySelector('details pre')?.textContent ?? null) : null;
    })()`);
    await tab.click({ tag: "button", text: "复制草稿（仅写入本机剪贴板）" }, { label: "copy (s9, simulated clipboard)" });
    await tab.waitFor(`() => (() => {
      const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent ?? '').includes('私人回答草稿'));
      return !!section && ((section.textContent ?? '').includes('已复制到本机剪贴板') || Array.from(section.querySelectorAll('[role=alert]')).some(e => (e.textContent ?? '').includes('复制失败')));
    })()`, { timeoutMs: 15000, label: "copy outcome (s9)" });
    await sleep(300);
    const copiedS9 = await tab.evalJs(`window.__e2eClipboard ? window.__e2eClipboard.writes[window.__e2eClipboard.writes.length - 1] ?? null : null`);
    await saveDraftPanelShots(tab, "s9-preview-copy");
    const afterDrafts = await accounting("after-draft-ops");

    saveJson("s9-summary", {
      partA: { refFile: REF_NAME, jobB: jobB.id, s9AnalysisId, s9ReportId, reportReused, uploadAnalysisHref, accounting: { beforeAny, afterUpload, afterReport, afterDrafts } },
      partB: { s9TaskId, refOption, optionLabel, savedRef, refreshedRef, refreshed: { text: refreshed.text, checkedReferences: refreshed.checkedReferences, savedLine: refreshed.savedLine }, previewHead: previewTextS9?.slice(0, 400), copiedEqualsPreview: copiedS9 === previewTextS9, putsB: putsB.map(p => p.status), accounting: { beforeAny, afterReport, afterDrafts } },
    });

    const checksB = [
      ["upload-card-marks-reference", cardText.includes("第三方参考")],
      ["mock-report-created", typeof s9ReportId === "string" && !!s9ReportId],
      ["report-accounting-one-new-analysis", reportDelta === (reportReused ? 0 : 1)],
      ["reference-options-carry-provenance", refOptions.length > 0],
      ["option-label-marks-third-party", optionLabel.includes("第三方参考")],
      ["draft-saves-reference-triple", !!savedRef && tripleS9(savedRef) === tripleS9(refOption)],
      ["draft-reference-provenance-and-snippet", !!savedRef && savedRef.provenance === "reference" && savedRef.available === true && typeof savedRef.snippet === "string" && savedRef.snippet.length > 0],
      ["refresh-keeps-text-and-reference", refreshed?.text === marker && (refreshed.checkedReferences ?? []).some(l => l.includes(refOption.citationId)) && !!refreshedRef && tripleS9(refreshedRef) === tripleS9(refOption)],
      ["refresh-server-revision-matches-page", reloaded.data !== null && reloaded.data.revision === serverDraftB.revision],
      ["preview-marks-third-party-and-keeps-snippet", !!previewTextS9 && previewTextS9.includes("（第三方参考，不计入评级）") && snippetPrefixS9.length > 0 && previewTextS9.includes(snippetPrefixS9)],
      ["copy-equals-preview-simulated-clipboard", copiedS9 === previewTextS9],
      ["draft-ops-no-analysis-usage-notifications", afterDrafts.analysisTasks === afterReport.analysisTasks && afterDrafts.aiUsageLogs === afterReport.aiUsageLogs && afterDrafts.notifications === afterReport.notifications],
    ];
    for (const [name, ok] of checksB) record({ name, status: ok ? "pass" : "fail", detail: ok ? "" : `savedRef=${JSON.stringify(savedRef)} refreshed=${JSON.stringify(refreshed)} preview=${previewTextS9?.slice(0, 120)} copiedEq=${copiedS9 === previewTextS9} accounting=${JSON.stringify({ afterReport, afterDrafts })}` });

    // --- Part C: real re-selection boundary on THIS task (no injection) ---
    // A freshly created growth task starts with materials=[]; the 生成新报告
    // flow needs a real material selection first (resume + the reference
    // version) saved via 保存本次材料选择. Once an analysis is bound (any
    // status beyond FAILED/CANCELLED), PUT materials must be rejected
    // 409/4099 and the frozen row must not change.
    let detail = await auth.getJson(`/growth-tasks/${s9TaskId}`);
    if (!detail.analysisTaskId) {
      // Resume on the growth task page.
      await tab.clickStored(`(() => {
        const summary = Array.from(document.querySelectorAll('summary')).find(s => s.textContent.includes('选择简历版本') || s.textContent.includes('更换简历版本'));
        if (!summary) return false;
        const details = summary.closest('details'); if (!details || details.open === false) details.open = true;
        const radio = Array.from(details.querySelectorAll('input[type=radio]')).find(r => (r.getAttribute('aria-label') || '').includes('resume-v2.txt'));
        if (!radio) return false;
        radio.scrollIntoView({ block: 'center' }); window.__e2eClickEl = radio; return true;
      })()`, "s9 task resume radio");
      await sleep(250);
      record({ name: "s9-task-resume-selected", status: (await tab.evalJs("window.__e2eClickEl.checked")) === true ? "pass" : "fail", detail: "resume-v2.txt" });
      // Reference project version on the growth task page.
      const taskPickerOpened = await tab.evalJs(`(() => {
        const summary = Array.from(document.querySelectorAll('summary')).find(s => s.textContent.includes('选择或更换项目版本'));
        if (!summary) return false;
        const details = summary.closest('details'); if (!details) return false;
        if (details.open === false) details.open = true;
        details.scrollIntoView({ block: 'center' });
        return true;
      })()`);
      if (!taskPickerOpened) throw new Error("s9 task project picker not found");
      await sleep(250);
      await tab.evalJs(`(() => {
        const summaries = Array.from(document.querySelectorAll('summary')).filter(s => s.textContent.includes('个版本'));
        for (const s of summaries) { const d = s.closest('details'); if (d) d.open = true; }
        return summaries.length;
      })()`);
      await sleep(200);
      // The saved selection must DIFFER from the task's base combination
      // (resume-v2 + reference only would be rejected by design as identical
      // to the base), so the personal v2 project is selected alongside the
      // reference material.
      const taskProjectFiles = [REF_NAME, "new-version-project.zip"];
      for (const projectFile of taskProjectFiles) {
        await tab.clickStored(`(() => {
          const box = Array.from(document.querySelectorAll('input[type=checkbox]')).find(b => (b.closest('label')?.textContent || '').includes(${JSON.stringify(projectFile)}) && (b.closest('label')?.textContent || '').includes('第'));
          if (!box) return false;
          box.scrollIntoView({ block: 'center' }); window.__e2eClickEl = box; return true;
        })()`, `s9 task project checkbox ${projectFile}`);
        await sleep(250);
        if (!(await tab.evalJs("window.__e2eClickEl.checked"))) {
          await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
          await tab.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
          await sleep(250);
        }
        record({ name: `s9-task-project-selected:${projectFile}`, status: (await tab.evalJs("window.__e2eClickEl.checked")) === true ? "pass" : "fail", detail: projectFile });
      }
      await saveShot(tab, "s9-task-materials-form", false);
      // Explicit save of the material selection (this PUT is legal: no
      // analysis is bound yet).
      await tab.click({ tag: "button", text: "保存本次材料选择" }, { label: "s9 save materials" });
      await tab.waitFor(`() => document.body.innerText.includes('已保存：')`, { timeoutMs: 20000, label: "s9 materials saved receipt" });
      await sleep(800);
      detail = await auth.getJson(`/growth-tasks/${s9TaskId}`);
      const savedMaterials = detail.materials ?? [];
      record({
        name: "s9-task-materials-saved",
        status: savedMaterials.some(m => m.kind === "resume") && savedMaterials.some(m => m.kind === "project") ? "pass" : "fail",
        detail: `materials=${JSON.stringify(savedMaterials.map(m => `${m.kind}:${(m.id ?? "").slice(0, 8)}${m.materialRole === "reference" ? ":reference" : ""}`))}`,
      });
      if (!detail.analysisTaskId) {
        const btnReady = await tab.evalJs(`(() => {
          const btn = Array.from(document.querySelectorAll('button')).find(b => (b.textContent ?? '').includes('生成新报告'));
          if (!btn) return { found: false };
          btn.scrollIntoView({ block: 'center' });
          window.__e2eClickEl = btn;
          return { found: true, disabled: btn.disabled };
        })()`);
        if (!btnReady.found) throw new Error("生成新报告 button not found on s9 task after materials saved");
        if (btnReady.disabled) throw new Error(`生成新报告 button disabled after materials saved: ${JSON.stringify(btnReady)}`);
        await tab.clickStored(`(() => window.__e2eClickEl && window.__e2eClickEl.isConnected)()`, "s9 generate new report");
        const started = Date.now();
        let settled = null;
        while (Date.now() - started < 240000) {
          await sleep(2000);
          const body = await tab.bodyText();
          if (body.includes("新报告已对比")) { settled = "compared"; break; }
          if (body.includes("分析失败")) { settled = "analysis_failed"; break; }
          if (body.includes("已停止自动查询")) {
            await tab.click({ tag: "button", text: "读取已保存任务" }, { label: "s9 manual re-read" }).catch(() => {});
          }
        }
        if (settled !== "compared") throw new Error(`s9 analyze did not settle: ${settled}`);
        record({ name: "s9-analysis-generated-on-task", status: "pass", detail: "生成新报告 completed via UI (Mock); 计入新报告记账" });
        const afterAnalyze = await accounting("after-task-analysis");
        record({ name: "s9-task-analysis-accounting", status: "info", detail: `afterDrafts=${JSON.stringify(afterDrafts)} afterAnalyze=${JSON.stringify(afterAnalyze)} (delta analysis +${afterAnalyze.analysisTasks - afterDrafts.analysisTasks})` });
        detail = await auth.getJson(`/growth-tasks/${s9TaskId}`);
      }
    } else {
      record({ name: "s9-analysis-already-bound", status: "info", detail: `analysisTask=${detail.analysisTaskId} (from earlier run; skipped new analysis)` });
    }
    const analysisStatusS9 = await dbQuery(`SELECT status::text FROM analysis_tasks WHERE id='${detail.analysisTaskId}';`);
    record({ name: "s9-task-analysis-status", status: "info", detail: `analysisTask=${detail.analysisTaskId} status=${analysisStatusS9}` });
    if (analysisStatusS9 === "COMPLETED") {
      const payloadC = {
        resumeVersionId: detail.materials.find(m => m.kind === "resume")?.id,
        projectVersionIds: detail.materials.filter(m => m.kind === "project").map(m => m.id),
        ...(detail.targetJobId ? { targetJobId: detail.targetJobId } : {}),
      };
      const rowBeforeC = await dbQuery(`SELECT materials::text||'|'||COALESCE(target_job_id::text,'-')||'|'||COALESCE(analysis_task_id::text,'-')||'|'||status FROM evidence_growth_tasks WHERE id='${s9TaskId}';`);
      const attachC = await auth.putStatus(`/growth-tasks/${s9TaskId}/materials`, payloadC);
      const rowAfterC = await dbQuery(`SELECT materials::text||'|'||COALESCE(target_job_id::text,'-')||'|'||COALESCE(analysis_task_id::text,'-')||'|'||status FROM evidence_growth_tasks WHERE id='${s9TaskId}';`);
      record({ name: "s9-reselect-409", status: attachC.status === 409 && attachC.code === 4099 ? "pass" : "fail", detail: `PUT materials -> ${attachC.status} code=${attachC.code}` });
      record({ name: "s9-frozen-row-unchanged", status: rowBeforeC === rowAfterC ? "pass" : "fail", detail: `taskRowEqual=${rowBeforeC === rowAfterC}` });
      saveJson("s9-part-c", { analysisTaskId: detail.analysisTaskId, analysisStatus: analysisStatusS9, attach: attachC, rowEqual: rowBeforeC === rowAfterC });
    } else {
      record({ name: "s9-reselect-409", status: "blocked", detail: `analysis status=${analysisStatusS9}; 409 boundary needs a bound non-failed analysis — not fabricated` });
    }

    saveJson("s9-network-log", { network: tab.networkLog, answerDraft: tab.answerCapture });
  } finally {
    await browser.stop().catch(() => {});
  }
}
try {
  const preflighted = await preflight();
  if (SCENARIO === "s1-save-refresh") await scenarioSaveRefresh(preflighted);
  else if (SCENARIO === "s2-clear-explicit-save") await scenarioClearExplicitSave(preflighted);
  else if (SCENARIO === "s3-save-inflight-edit") await scenarioSaveInflightEdit(preflighted);
  else if (SCENARIO === "s5-network-error") await scenarioNetworkError(preflighted);
  else if (SCENARIO === "s3b-request-stage-delay") await scenarioRequestStageDelay(preflighted);
  else if (SCENARIO === "s6-identity-late-response") await scenarioIdentityLate(preflighted);
  else if (SCENARIO === "s6b-identity-switch-race") await scenarioIdentitySwitchRace(preflighted);
  else if (SCENARIO === "s7-requirement-crossjob") await scenarioRequirementCrossJob(preflighted);
  else if (SCENARIO === "s8-invalid-reference") await scenarioInvalidReference(preflighted);
  else if (SCENARIO === "s9-third-party-reference") await scenarioThirdPartyReference(preflighted);
  else if (SCENARIO === "s10-preview-confirm-copy") await scenarioPreviewCopy(preflighted);
  else if (SCENARIO === "s4-dual-window-409") await scenarioDualWindow409(preflighted);
  else if (SCENARIO === "s11-viewport390") await scenarioViewport390(preflighted);
  else if (SCENARIO === "s12-old-state-unchanged") await scenarioOldStateUnchanged(preflighted);
  else throw new Error(`scenario ${SCENARIO} not implemented yet`);
  results.overall = exitCode === 0 ? "pass" : exitCode === 1 ? "fail" : "blocked";
} catch (error) {
  record({ name: "runner-error", status: exitCode === 0 ? "blocked" : (exitCode === 1 ? "fail" : "blocked"), detail: String(error?.message ?? error).slice(0, 400) });
  results.overall = exitCode === 0 ? "blocked" : "fail";
} finally {
  persist();
  console.log(`overall: ${results.overall} (${STAGE_DIR})`);
  process.exit(exitCode);
}
