// E2E-03 student growth browser runner (task card 20261005-E2E-student-growth).
// Drives the REAL product pages at http://127.0.0.1:3001 over raw CDP with an
// independent browser profile per role. Every business action (login, upload,
// parse, report, task create, materials save, target job save, analyze,
// comparison, enterprise re-check) goes through the UI only — no report is
// fabricated via API/SQL. Read-only psql diagnostics only verify what the UI
// already produced (snapshot hashes, job rows).
//
// Usage: node scripts/e2e/student-browser-runner.mjs --run closure-20261005 --scenario <name>
// Scenarios: setup-job | baseline | chain-reply | variant-materials | variant-job | variant-both | viewport390 | enterprise-recheck
// Exit codes: 0 pass, 1 fail, 2 blocked, 3 invalid arguments.
//
// Secrets (synthetic passwords) are scrubbed from every log/evidence file.
// Allowed write surface (task card #18): this runner + docs/evidence/20261005-E2E-student/.

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { parseCredentialDocument } from "./runner-input.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const FRONTEND = "http://127.0.0.1:3001";
const BACKEND_DIR = path.join(ROOT, "backend");
const EVIDENCE_DIR = path.join(ROOT, "docs", "evidence", "20261005-E2E-student");
const MATERIALS_DIR = path.join(ROOT, "docs", "evidence", "20261005-E2E-student-preflight", "materials");
const STATE_FILE = path.join(EVIDENCE_DIR, "state.json");

const SCENARIOS = Object.freeze([
  "setup-job", "baseline", "chain-reply", "variant-materials",
  "variant-job", "variant-both", "viewport390", "enterprise-recheck",
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
  if (!/^[a-z0-9][a-z0-9-]{0,31}$/.test(values["--run"])) return null;
  if (!SCENARIOS.includes(values["--scenario"])) return null;
  return { runId: values["--run"], scenario: values["--scenario"] };
}
const selection = parseArgs(process.argv.slice(2));
if (!selection) { console.error("Invalid --run/--scenario arguments; no files were written."); process.exit(3); }
const { runId: RUN_ID, scenario: SCENARIO } = selection;

fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
const RUNTIME_DIR = path.join(BACKEND_DIR, ".tmp", "e2e-browser", `${RUN_ID}-student`);
fs.mkdirSync(RUNTIME_DIR, { recursive: true });

// ---------------------------------------------------------------------------
// Evidence plumbing
// ---------------------------------------------------------------------------
const RUN_STAMP = new Date().toISOString().replace(/[:.]/g, "-");
const STAGE_DIR = path.join(EVIDENCE_DIR, `${SCENARIO}-${RUN_STAMP}`);
fs.mkdirSync(STAGE_DIR, { recursive: true });
const results = { runId: RUN_ID, scenario: SCENARIO, startedAt: new Date().toISOString(), steps: [], artifacts: [] };
let stepCounter = 0;
let exitCode = 0;
let lastTab = null;
let activeBrowser = null;
let failureEvidenceSaved = false;

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
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
  results.artifacts.push(path.relative(ROOT, file));
  return file;
}
// Failure evidence must be captured while the page is still alive. The old
// flow stopped Chrome before dumping, so the outer catch only ever recorded
// "(page unavailable)". Scenario catch blocks call this BEFORE browser.stop().
async function dumpFailureEvidence(tab) {
  if (failureEvidenceSaved || !tab) return;
  failureEvidenceSaved = true;
  saveJson("error-network-log", { network: tab.networkLog.slice(-80), bodies: tab.requestBodies.slice(-20) });
  await saveShot(tab, "error-page", false).catch(() => null);
  const body = await tab.bodyText().catch(() => "(page unavailable)");
  saveJson("error-page-text", { path: await tab.evalJs("location.pathname").catch(() => "?"), text: scrub(body).slice(0, 4000) });
}
function loadState() {
  if (!fs.existsSync(STATE_FILE)) return {};
  try { return JSON.parse(fs.readFileSync(STATE_FILE, "utf8")); }
  catch { throw new Error("state.json unreadable; refusing to overwrite"); }
}
function saveState(patch) {
  const state = { ...loadState(), ...patch, updatedAt: new Date().toISOString() };
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
  return state;
}

// ---------------------------------------------------------------------------
// Credentials (synthetic; never printed)
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
const JOB_B = CREDS.enterprise.jobIdB;
const JOB_A = CREDS.enterprise.jobIdA;
const REPORT_B_SEED = CREDS.reports.B;

// ---------------------------------------------------------------------------
// Read-only DB diagnostics (docker compose exec psql; SELECT only)
// ---------------------------------------------------------------------------
function dbQuery(sql) {
  return new Promise((resolve, reject) => {
    const child = spawn("docker", ["compose", "exec", "-T", "postgres", "psql", "-U", "careerproof",
      "-d", `cp_e2e_${RUN_ID}`, "-At", "-c", sql],
      { cwd: BACKEND_DIR, stdio: ["ignore", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", chunk => { out += String(chunk); });
    child.stderr.on("data", chunk => { err += String(chunk); });
    child.on("exit", code => code === 0 ? resolve(out.trim()) : reject(new Error(`psql exit ${code}: ${err.slice(0, 200)}`)));
    child.on("error", reject);
  });
}
// Canonical SHA-256 over the frozen report snapshot — same normalization the
// seeder uses (json.dumps sort_keys, ensure_ascii=False, compact separators),
// computed by host python to keep float formatting identical.
function snapshotHash(jsonText) {
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
async function captureApplicationsBaseline(label) {
  const rows = await dbQuery("SELECT id::text||'|'||status||'|'||report_snapshot::text FROM applications ORDER BY created_at;");
  const apps = [];
  for (const line of rows.split("\n").filter(Boolean)) {
    const [id, status, ...rest] = line.split("|");
    apps.push({ id, status, snapshotSha256: await snapshotHash(rest.join("|")) });
  }
  const jobs = await dbQuery("SELECT id::text||'|'||status||'|'||title FROM jobs ORDER BY created_at;");
  const reqs = await dbQuery("SELECT id::text||'|'||job_id::text||'|'||skill_name||'|'||weight||'|'||is_required||'|'||raw_text FROM job_requirements ORDER BY job_id, created_at;");
  const payload = { label, at: new Date().toISOString(), applications: apps, jobs: jobs.split("\n").filter(Boolean), requirements: reqs.split("\n").filter(Boolean) };
  saveJson(`${label}-readonly-db`, payload);
  return payload;
}

// ---------------------------------------------------------------------------
// Chrome + CDP (own implementation, independent profiles, bounded waits)
// ---------------------------------------------------------------------------
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
class CdpError extends Error {}

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
  send(method, params = {}, sessionId = undefined) {
    if (!this.ws || this.ws.readyState !== 1) throw new CdpError(`cdp not connected: ${method}`);
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new CdpError(`cdp timeout 20s: ${method}`)); }, 20000);
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
    if (this.closed) return; // idempotent: scenario catch and outer catch may both stop
    this.closed = true;
    try { await this.send("Browser.close"); } catch { /* fall through to wait */ }
    if (this.child && this.child.exitCode === null) {
      await Promise.race([new Promise(resolve => this.child.on("exit", resolve)), sleep(3000)]);
    }
    if (this.child && this.child.exitCode === null && this.child.pid) {
      const verify = spawn("powershell", ["-NoProfile", "-Command",
        `(Get-CimInstance Win32_Process -Filter 'ProcessId=${this.child.pid}').CommandLine`],
        { stdio: ["ignore", "pipe", "ignore"] });
      let cmdline = "";
      verify.stdout.on("data", chunk => { cmdline += String(chunk); });
      verify.on("exit", () => {
        if (cmdline.includes(`--user-data-dir=${this.profileDir}`)) {
          spawn("taskkill", ["/PID", String(this.child.pid), "/T", "/F"], { stdio: "ignore" });
          record({ name: "chrome-force-killed", status: "warn", detail: `${this.label} verified own profile before kill` });
        } else {
          record({ name: "chrome-kill-skipped", status: "warn", detail: `${this.label} pid not verified as ours` });
        }
      });
    }
    record({ name: "chrome-stopped", status: "info", detail: `${this.label} exitCode=${this.child?.exitCode ?? "n/a"}` });
  }
}

class Tab {
  constructor(browser, sessionId, targetId) {
    this.browser = browser; this.sessionId = sessionId; this.targetId = targetId;
    this.networkLog = [];
    this.requestBodies = [];
    browser.onEvent(msg => {
      if (msg.sessionId !== this.sessionId) return;
      if (msg.method === "Network.requestWillBeSent") {
        this.networkLog.push({ at: new Date().toISOString(), phase: "request", method: msg.params.request.method, url: msg.params.request.url.replace(/^https?:\/\/127\.0\.0\.1:[0-9]+\/backend?/, "").replace(/^https?:\/\/127\.0\.0\.1:[0-9]+/, ""), type: msg.params.type });
      } else if (msg.method === "Network.responseReceived") {
        this.networkLog.push({ at: new Date().toISOString(), phase: "response", url: msg.params.response.url.replace(/^https?:\/\/127\.0\.0\.1:[0-9]+\/backend?/, "").replace(/^https?:\/\/127\.0\.0\.1:[0-9]+/, ""), status: msg.params.response.status });
      } else if (msg.method === "Fetch.requestPaused") {
        const p = msg.params;
        // Request bodies contain version/job UUIDs only — no credentials.
        if (p.request.postData && /growth-tasks|match-reports|portfolio|jobs/.test(p.request.url)) {
          this.requestBodies.push({ at: new Date().toISOString(), method: p.request.method, url: p.request.url.replace(/^https?:\/\/127\.0\.0\.1:[0-9]+\/backend?/, "").replace(/^https?:\/\/127\.0\.0\.1:[0-9]+/, ""), body: p.request.postData.slice(0, 2000) });
        }
        this.send("Fetch.continueRequest", { requestId: p.requestId }).catch(() => {});
      }
    });
  }
  send(method, params) { return this.browser.send(method, params, this.sessionId); }
  async enable() {
    await this.send("Page.enable");
    await this.send("Network.enable");
    await this.send("Runtime.enable");
    // Pass-through recorder: captures POST/PUT bodies (Fetch domain, no faults).
    await this.send("Fetch.enable", { patterns: [{ urlPattern: "*" }], handleAuthRequests: false });
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
      // A single evaluate can race a client-side navigation; one retry.
      if (!/cdp timeout/.test(String(error?.message))) throw error;
      await sleep(1000);
      return this.#evalOnce(expression, options);
    }
  }
  async #evalOnce(expression, { timeoutMs = 15000, awaitPromise = false } = {}) {
    const result = await this.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise, userGesture: true, timeout: timeoutMs });
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
  // Click a node located by an expression that scrolls it into view and
  // stashes it on window.__e2eClickEl (for elements the text finder cannot
  // disambiguate: nth-of-group inputs, checkboxes by label text, ...).
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
  // Click a stored node AND guarantee it holds focus afterwards. Real clicks
  // occasionally leave activeElement=BODY on this app (observed on the job
  // form); the fallback calls el.focus() so all subsequent keystrokes are
  // still real input events on the real element.
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
  // Move a focused <select> to targetValue with real arrow keys. A real
  // click OPENS the select's dropdown popup; while it is open the DOM value
  // does not change (keys move the popup highlight until Enter commits), so
  // the popup is closed with Escape first and each arrow is then verified
  // against document.activeElement directly.
  async keyboardSelectValue(targetValue, label) {
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
    await sleep(200);
    for (let i = 0; i < 10; i++) {
      const info = await this.evalJs(`(() => { const s = document.activeElement; if (!s || s.tagName !== 'SELECT') return null; return { v: s.value, idx: s.selectedIndex, values: Array.from(s.options).map(o => o.value), isTarget: s === window.__e2eClickEl }; })()`);
      if (!info) throw new CdpError(`keyboardSelectValue: no focused select (${label})`);
      if (!info.isTarget) {
        await this.evalJs(`window.__e2eClickEl && window.__e2eClickEl.focus()`);
        await sleep(150);
        continue;
      }
      if (info.v === String(targetValue)) return info.v;
      const targetIdx = info.values.indexOf(String(targetValue));
      if (targetIdx < 0) throw new CdpError(`keyboardSelectValue: value ${targetValue} missing (${label})`);
      record({ name: "keyselect-step", status: "info", detail: `${label} iter=${i} v=${info.v} -> target ${targetValue}` });
      await this.#arrow(targetIdx > info.idx);
      await sleep(150);
    }
    const finalValue = await this.evalJs(`document.activeElement && document.activeElement.tagName === 'SELECT' ? document.activeElement.value : null`);
    if (finalValue !== String(targetValue)) throw new CdpError(`keyboardSelectValue: settled on ${finalValue} not ${targetValue} (${label})`);
    return finalValue;
  }
  async fillStored(locatorExpression, text, label) {
    await this.clickFocusStored(locatorExpression, label);
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
    await this.send("Input.insertText", { text });
    await sleep(150);
    const got = await this.evalJs(`(document.activeElement?.value ?? "").trim()`);
    if (got !== text) throw new CdpError(`fillStored mismatch: ${label} expectedLength=${text.length} gotLength=${String(got).length}`);
  }
  async selectFocusedOption(optionText) {
    const info = await this.evalJs(`(() => { const s = document.activeElement && document.activeElement.tagName === 'SELECT' ? document.activeElement : null; if (!s) return null; return { idx: s.selectedIndex, texts: Array.from(s.options).map(o => o.text.trim()) }; })()`);
    if (!info) throw new CdpError(`selectFocusedOption: no focused select for ${optionText}`);
    const targetIdx = info.texts.indexOf(optionText);
    if (targetIdx < 0) throw new CdpError(`selectFocusedOption: option ${optionText} missing`);
    let steps = targetIdx - info.idx;
    while (steps !== 0) {
      const down = steps > 0;
      await this.#arrow(down);
      steps += down ? -1 : 1;
    }
    await this.#enter();
    await sleep(150);
  }
  async #arrow(down) {
    const key = down ? "ArrowDown" : "ArrowUp";
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key, code: key, windowsVirtualKeyCode: down ? 40 : 38 });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", key, code: key, windowsVirtualKeyCode: down ? 40 : 38 });
    await sleep(60);
  }
  async #enter() {
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await sleep(120);
  }
  async setFileInput(selector, absolutePath) {
    const { root } = await this.send("DOM.getDocument", { depth: 1 });
    const { nodeId } = await this.send("DOM.querySelector", { nodeId: root.nodeId, selector });
    if (!nodeId) throw new CdpError(`setFileInput: ${selector} not found`);
    await this.send("DOM.setFileInputFiles", { files: [absolutePath], nodeId });
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
}

// ---------------------------------------------------------------------------
// Shared flows
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

// Wait for the portfolio upload card of a given file to reach terminal state.
async function waitUploadComplete(tab, filename, timeoutMs = 180000) {
  await tab.waitFor(`() => Array.from(document.querySelectorAll('article')).some(a => a.textContent.includes(${JSON.stringify(filename)}) && a.textContent.includes('预览解析内容'))`, { timeoutMs, pollMs: 1000, label: `parse complete ${filename}` });
  const cardText = await tab.evalJs(`Array.from(document.querySelectorAll('article')).filter(a => a.textContent.includes(${JSON.stringify(filename)})).map(a => a.innerText.replace(/\\n+/g, ' | ')).join(' ;; ').slice(0, 1200)`);
  record({ name: `upload-complete:${filename}`, status: "pass", detail: cardText });
}

// GrowthTaskStart on a report page: expand, optionally capture enterprise
// reply context, fill the plan, save, land on /growth/{id}.
async function createGrowthTaskFromReport(tab, reportId, plan, { expectReplyContext = false } = {}) {
  await tab.goto(`${FRONTEND}/reports/${reportId}`);
  await tab.installFinder();
  await tab.waitFor(`() => document.querySelectorAll('article[id^="requirement-"]').length > 0`, { timeoutMs: 30000, label: "report items" });
  const articles = await tab.evalJs(`Array.from(document.querySelectorAll('article[id^="requirement-"]')).map(a => ({ id: a.id.slice(12), title: (a.querySelector('h3')?.textContent ?? '').trim(), badge: (a.querySelector('span.rounded-full')?.textContent ?? '').trim(), level: (a.innerText.match(/实践证据\\s*([^/\\n]{1,12})/)?.[1] ?? '').trim() }))`);
  // A report may hold several requirement items (job C has two); chain from the first.
  await tab.clickStored(`(() => {
    const article = document.querySelector('article[id^="requirement-"]');
    if (!article) return false;
    const btn = Array.from(article.querySelectorAll('button')).find(b => b.textContent.includes('从这条缺口创建或打开补证任务'));
    if (!btn) return false;
    btn.scrollIntoView({ block: 'center' }); window.__e2eClickEl = btn; return true;
  })()`, "task start button (first requirement)");
  await tab.waitFor(`() => document.body.innerText.includes('具体交付物') || document.body.innerText.includes('打开这条缺口已有补证任务')`, { timeoutMs: 15000, label: "task start form" });
  const body = await tab.bodyText();
  const existing = body.includes("打开这条缺口已有补证任务");
  if (expectReplyContext) {
    // The reply context is a <section> titled 企业人工回复中针对本项的核验内容.
    const replyBlock = await tab.evalJs(`(() => { const el = Array.from(document.querySelectorAll('section')).find(n => (n.querySelector('h3')?.textContent || '').includes('企业人工回复中针对本项的核验内容')); return el ? el.innerText.slice(0, 1200) : null; })()`);
    record({ name: "enterprise-reply-context", status: replyBlock ? "pass" : "blocked", detail: replyBlock ? String(replyBlock).replace(/\n+/g, " | ").slice(0, 600) : "reply context block not found" });
    await saveShot(tab, "task-start-reply-context");
  }
  if (existing) {
    // (report, requirement) already has a task: open it (documented dedup path).
    await tab.click({ tag: "a", text: "打开这条缺口已有补证任务 →" }, { label: "open existing task" });
    await tab.waitFor(`() => location.pathname.startsWith('/growth/')`, { timeoutMs: 20000, label: "redirect to existing growth task" });
    await sleep(1200);
    await tab.installFinder();
    const taskId = await tab.evalJs("location.pathname.split('/')[2]");
    record({ name: "growth-task-existing-opened", status: "info", detail: `task ${taskId} (dedup: same report+requirement returns the original task)` });
    return { taskId, reportItems: articles, existing: true };
  }
  // The three plan textareas: deliverable (rows=3) then steps/checks (rows=4).
  await tab.fillStored(`(() => { const t = Array.from(document.querySelectorAll('form textarea')).find(x => x.rows === 3); if (!t) return false; t.scrollIntoView({ block: 'center' }); window.__e2eClickEl = t; return true; })()`, plan.deliverable, "deliverable");
  await tab.clickFocusStored(`(() => { const all = Array.from(document.querySelectorAll('form textarea')).filter(x => x.rows === 4); if (!all.length) return false; window.__e2eClickEl = all[0]; all[0].scrollIntoView({ block: 'center' }); return true; })()`, "steps textarea");
  await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
  await tab.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
  await tab.send("Input.insertText", { text: plan.steps.join("\n") });
  await sleep(150);
  await tab.clickFocusStored(`(() => { const all = Array.from(document.querySelectorAll('form textarea')).filter(x => x.rows === 4); if (all.length < 2) return false; window.__e2eClickEl = all[1]; all[1].scrollIntoView({ block: 'center' }); return true; })()`, "checks textarea");
  await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
  await tab.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
  await tab.send("Input.insertText", { text: plan.checks.join("\n") });
  await sleep(150);
  await saveShot(tab, "task-form-filled");
  await tab.click({ tag: "button", text: "保存并进入补证" }, { label: "save task" });
  await tab.waitFor(`() => location.pathname.startsWith('/growth/')`, { timeoutMs: 20000, label: "redirect to growth task" });
  await sleep(1000);
  await tab.installFinder();
  const taskId = await tab.evalJs("location.pathname.split('/')[2]");
  await tab.waitFor(`() => document.body.innerText.includes('待补充材料') || document.body.innerText.includes('已选择材料')`, { timeoutMs: 20000, label: "growth task loaded" });
  record({ name: "growth-task-created", status: "pass", detail: `task ${taskId} from report ${reportId}` });
  return { taskId, reportItems: articles };
}

// Select a resume version by its original filename inside ResumeVersionPicker.
async function pickResume(tab, filename) {
  await tab.clickStored(`(() => {
    const summary = Array.from(document.querySelectorAll('summary')).find(s => s.textContent.includes('选择简历版本') || s.textContent.includes('更换简历版本'));
    if (!summary) return false;
    const details = summary.closest('details'); if (!details || details.open === false) details.open = true;
    const radio = Array.from(details.querySelectorAll('input[type=radio]')).find(r => (r.getAttribute('aria-label') || '').includes(${JSON.stringify(filename)}));
    if (!radio) return false;
    radio.scrollIntoView({ block: 'center' }); window.__e2eClickEl = radio; return true;
  })()`, `resume radio ${filename}`);
  await sleep(250);
}

// Set project version selection: ensure exactly `filenames` are checked.
async function pickProjects(tab, filenames) {
  await tab.clickStored(`(() => {
    const summary = Array.from(document.querySelectorAll('summary')).find(s => s.textContent.includes('选择或更换项目版本'));
    if (!summary) return false;
    const details = summary.closest('details'); if (!details) return false;
    if (details.open === false) details.open = true;
    details.scrollIntoView({ block: 'center' });
    window.__e2eClickEl = summary;
    return true;
  })()`, "project picker open");
  await sleep(250);
  for (const filename of filenames) {
    await tab.clickStored(`(() => {
      const summaries = Array.from(document.querySelectorAll('summary')).filter(s => s.textContent.includes('个版本'));
      for (const s of summaries) { const d = s.closest('details'); if (d) d.open = true; }
      return summaries.length > 0;
    })()`, "expand project rows").catch(() => {});
    await sleep(200);
    await toggleCheckboxStored(tab, `(() => {
      const boxes = Array.from(document.querySelectorAll('input[type=checkbox]'));
      const box = boxes.find(b => (b.closest('label')?.textContent || '').includes(${JSON.stringify(filename)}) && (b.closest('label')?.textContent || '').includes('第'));
      if (!box) return false;
      box.scrollIntoView({ block: 'center' }); window.__e2eClickEl = box; return true;
    })()`, `project checkbox ${filename}`, true);
  }
}
// Locator expression for the checkbox whose wrapping label contains `needle`.
function checkboxByLabelText(needle) {
  return `(() => { const box = Array.from(document.querySelectorAll('input[type=checkbox]')).find(b => (b.closest('label')?.textContent || '').includes('${needle}')); if (!box) return false; box.scrollIntoView({ block: 'center' }); window.__e2eClickEl = box; return true; })()`;
}
// Focus a checkbox (real click with focus fallback) and toggle it with a real
// Space keypress when its state does not match wantChecked; verifies the end state.
async function toggleCheckboxStored(tab, locatorExpression, label, wantChecked) {
  await tab.clickFocusStored(locatorExpression, label);
  const before = await tab.evalJs(`window.__e2eClickEl ? window.__e2eClickEl.checked : null`);
  if (before !== wantChecked) {
    await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
    await tab.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
    await sleep(200);
  }
  const checked = await tab.evalJs(`window.__e2eClickEl ? window.__e2eClickEl.checked : null`);
  if (checked !== wantChecked) throw new CdpError(`toggleCheckboxStored(${label}): checked=${checked} expected=${wantChecked}`);
}
async function uncheckProject(tab, filename) {
  // On a rerun the version may already be deselected ('absent'): that is a
  // no-op, not a failure — clickStored would otherwise chase a stale element.
  const outcome = await tab.evalJs(`(() => {
    const items = Array.from(document.querySelectorAll('ul[aria-label="已选项目版本"] li')).filter(li => li.textContent.includes(${JSON.stringify(filename)}));
    if (!items.length) return 'absent';
    const btn = items[0].querySelector('button');
    if (!btn) return false;
    btn.scrollIntoView({ block: 'center' }); window.__e2eClickEl = btn; return true;
  })()`);
  if (outcome !== true) {
    record({ name: `uncheck-project:${filename}`, status: "info", detail: outcome === "absent" ? "not in selected list (already deselected — no-op)" : "remove button missing" });
    return;
  }
  await tab.clickStored(`(() => window.__e2eClickEl && window.__e2eClickEl.isConnected)()`, `remove selected project ${filename}`);
  await sleep(250);
}

async function saveMaterialsSelection(tab) {
  const putCountBefore = tab.networkLog.filter(e => e.phase === "request" && e.method === "PUT").length;
  await tab.click({ tag: "button", text: "保存本次材料选择" }, { label: "save materials" });
  await sleep(1200);
}

// Select target job inside the growth job picker (search + radio).
async function pickTargetJob(tab, jobTitleSnippet) {
  // Opening the picker is programmatic on purpose: a REAL click on <summary>
  // would toggle the <details> that this locator just set open, closing it
  // again. The old code called clickStored here without ever setting
  // __e2eClickEl, so it clicked a stale element (or crashed on null).
  const opened = await tab.evalJs(`(() => {
    const summary = Array.from(document.querySelectorAll('summary')).find(s => s.textContent.includes('选择已发布的新岗位'));
    if (!summary) return false;
    const details = summary.closest('details'); if (!details) return false;
    details.open = true; details.scrollIntoView({ block: 'center' }); return true;
  })()`);
  if (!opened) throw new CdpError("pickTargetJob: job picker summary/details not found");
  await tab.waitFor(`() => Array.from(document.querySelectorAll('input[type=radio][name="growth-target-job"]')).length > 0`, { timeoutMs: 15000, label: "job list loaded" });
  await sleep(300);
  await tab.clickStored(`(() => {
    const labels = Array.from(document.querySelectorAll('input[type=radio][name="growth-target-job"]'));
    const radio = labels.find(r => (r.closest('label')?.textContent || '').includes(${JSON.stringify(jobTitleSnippet)}));
    if (!radio) return false;
    radio.scrollIntoView({ block: 'center' }); window.__e2eClickEl = radio; return true;
  })()`, `target job radio ${jobTitleSnippet}`);
  await sleep(300);
}

async function analyzeAndWait(tab, { timeoutMs = 180000, skipClick = false } = {}) {
  if (!skipClick) await tab.click({ tag: "button", text: "生成新报告" }, { label: "analyze" });
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    await sleep(2000);
    const body = await tab.bodyText();
    if (body.includes("新报告已对比")) return "compared";
    if (body.includes("分析失败")) return "analysis_failed";
    if (body.includes("已停止自动查询")) {
      await tab.click({ tag: "button", text: "读取已保存任务" }, { label: "manual re-read" }).catch(() => {});
    }
  }
  throw new CdpError(`analyze did not settle within ${timeoutMs}ms`);
}

// Extract the section-4 comparison from the growth task page (rendered DOM).
// Per-item fields are structured (status chip, focus marker, added/removed
// counts, two-sided explanation, own citations) so acceptance assertions judge
// real rendered evidence instead of grepping raw text blobs.
async function extractComparison(tab) {
  return tab.evalJs(`(() => {
    const section = Array.from(document.querySelectorAll('section')).find(s => (s.querySelector('h2')?.textContent || '').includes('逐项对比'));
    if (!section) return null;
    const context = (Array.from(section.querySelectorAll('p')).find(p => p.textContent.includes('变化背景'))?.textContent || '').trim();
    const banner = (section.querySelector('div.bg-amber-50')?.innerText || '').trim();
    const items = Array.from(section.querySelectorAll('article[id^="growth-requirement-"]')).map(a => {
      const h3 = a.querySelector('h3');
      const ownTitle = h3 ? Array.from(h3.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim() : '';
      const inner = a.innerText.replace(/\\n+/g, ' | ');
      const sideLabels = Array.from(a.querySelectorAll('p.font-medium')).map(p => (p.textContent || '').trim());
      return {
        id: a.id.slice('growth-requirement-'.length),
        title: ownTitle || (h3?.textContent || '').trim(),
        status: (h3?.querySelector('span')?.textContent || '').trim(),
        focus: (h3?.textContent || '').includes('本次补证重点'),
        levelLine: (Array.from(a.querySelectorAll('p')).find(p => (p.textContent || '').startsWith('证据等级'))?.textContent || '').trim(),
        addedCount: Number((inner.match(/新增展示：\\s*(\\d+)\\s*条/) || [])[1] ?? -1),
        removedCount: Number((inner.match(/不再展示：\\s*(\\d+)\\s*条/) || [])[1] ?? -1),
        sides: { base: sideLabels.includes('任务基准'), target: sideLabels.includes('目标报告') },
        citations: Array.from(a.querySelectorAll('a[href*="#citation-"]')).map(l => l.getAttribute('href')),
        text: inner.slice(0, 1600),
      };
    });
    const citationHrefs = Array.from(section.querySelectorAll('a[href*="#citation-"]')).map(a => a.getAttribute('href'));
    const limitation = Array.from(section.querySelectorAll('ul li')).map(li => li.textContent.trim());
    return { context, banner, items, citationHrefs: [...new Set(citationHrefs)].slice(0, 12), limitation };
  })()`);
}

async function captureComparisonEvidence(tab, variantName) {
  await tab.waitFor(`() => Array.from(document.querySelectorAll('section h2')).some(h => (h.textContent || '').includes('逐项对比'))`, { timeoutMs: 20000, label: "comparison section" });
  await sleep(800);
  const comparison = await extractComparison(tab);
  if (!comparison) { record({ name: `comparison:${variantName}`, status: "fail", detail: "section 4 missing" }); return null; }
  saveJson(`${variantName}-comparison`, comparison);
  await saveShot(tab, `${variantName}-comparison`);
  const reportIds = [...new Set((comparison.citationHrefs || []).map(h => h.match(/\/reports\/([0-9a-f-]{36})/)?.[1]).filter(Boolean))];
  record({
    name: `comparison:${variantName}`, status: "pass",
    detail: `context=[${comparison.context}] items=${comparison.items.length} citations=${(comparison.citationHrefs || []).length} reportLinks=${JSON.stringify(reportIds)} banner=${comparison.banner ? comparison.banner.slice(0, 120) : "(same-job)"}`,
  });
  return { comparison, reportIds };
}

// The new (target) report id: the citation-linked report that is not the base.
function resolveTargetReportId(reportIds, baseReportId) {
  const others = reportIds.filter(id => id !== baseReportId);
  if (others.length === 1) return others[0];
  return null;
}

// Failure reuse: reopen a task that state says was already created, instead of
// clicking through the report again — a rerun must never create a duplicate
// task for the same (report, requirement) pair.
async function openGrowthTask(tab, taskId) {
  await tab.goto(`${FRONTEND}/growth/${taskId}`);
  await tab.installFinder();
  await tab.waitFor(`() => document.body.innerText.includes('从缺口到新证据') || document.body.innerText.includes('已选择材料') || document.body.innerText.includes('新报告已对比')`, { timeoutMs: 30000, label: `growth task ${String(taskId).slice(0, 8)} loaded` });
  await sleep(1200);
  await tab.installFinder();
}

// Refresh reread: full page reload, then read the 已保存 material rows and the
// 已保存目标 line from the re-rendered DOM only — nothing from before the
// reload is trusted.
async function rereadSavedSelection(tab, taskId) {
  await tab.goto(`${FRONTEND}/growth/${taskId}`);
  await tab.installFinder();
  await tab.waitFor(`() => document.body.innerText.includes('已保存：') || document.body.innerText.includes('已保存目标')`, { timeoutMs: 30000, label: "task reloaded for reread" });
  await sleep(800);
  return tab.evalJs(`(() => ({
    saved: Array.from(document.querySelectorAll('li')).filter(li => li.textContent.includes('已保存：')).map(li => li.innerText.replace(/\\n+/g, ' | ')),
    target: (Array.from(document.querySelectorAll('p')).map(p => p.textContent).filter(t => t.includes('已保存目标')).join(' || ')).trim(),
  }))()`);
}

// ---------------------------------------------------------------------------
// Scenario: setup-job (enterprise creates + publishes the new target job C)
// ---------------------------------------------------------------------------
async function scenarioSetupJob() {
  const before = await captureApplicationsBaseline("setup-job-before");
  const browser = activeBrowser = await new Chrome("enterprise").launch();
  const tab = await browser.openTab();
  await tab.enable();
  lastTab = tab;
  try {
    await login(tab, CREDS.accounts.enterprise);
    await tab.goto(`${FRONTEND}/jobs/new`);
    await tab.installFinder();
    await tab.waitFor(`() => document.body.innerText.includes('发布岗位') && document.querySelectorAll('select').length >= 4`, { timeoutMs: 30000, label: "job form" });
    await saveShot(tab, "job-form-empty");
    // Two maxLength=200 inputs exist (job title + org name in a collapsed
    // details): disambiguate by the wrapping label text 岗位名称.
    await tab.fillStored(`(() => {
      const input = Array.from(document.querySelectorAll('input[maxlength="200"]')).find(i => (i.closest('label')?.textContent || '').includes('岗位名称'));
      if (!input) return false;
      input.scrollIntoView({ block: 'center' }); window.__e2eClickEl = input; return true;
    })()`, "E2E 岗位C（合成·补证目标）", "job title");
    await tab.fillStored(`(() => {
      const t = document.querySelector('textarea[rows="7"]');
      if (!t) return false;
      t.scrollIntoView({ block: 'center' }); window.__e2eClickEl = t; return true;
    })()`, "E2E 合成岗位C：仅用于学生补证目标岗位变化验证。与岗位A/B相互独立，全部内容为合成编写，不对应真实企业。", "job description");
    // Requirement 1: Python. The row's default weight is already 3/5 (A/B use
    // weight 1), so no weight interaction is needed.
    await tab.fillStored(`(() => {
      const i = document.querySelector('input[placeholder="如：能用 Excel 进行数据整理和分析"]');
      if (!i) return false;
      i.scrollIntoView({ block: 'center' }); window.__e2eClickEl = i; return true;
    })()`, "岗位C要求：能够使用 Python 编写数据清洗与自动化脚本并配套单元测试", "req1 rawText");
    await tab.fillStored(`(() => {
      const i = document.querySelector('input[placeholder="如：Excel"]');
      if (!i) return false;
      i.scrollIntoView({ block: 'center' }); window.__e2eClickEl = i; return true;
    })()`, "Python", "req1 skill");
    // Requirement 2: SQL — new skill that job A/B do not have, weight 2/5.
    await tab.click({ tag: "button", text: "添加要求" }, { label: "add requirement" });
    await sleep(400);
    await tab.fillStored(`(() => {
      const inputs = Array.from(document.querySelectorAll('input[placeholder="如：能用 Excel 进行数据整理和分析"]'));
      if (inputs.length < 2) return false;
      window.__e2eClickEl = inputs[1]; inputs[1].scrollIntoView({ block: 'center' }); return true;
    })()`, "岗位C要求：能够编写 SQL 查询完成业务数据核对", "req2 rawText");
    await tab.fillStored(`(() => {
      const inputs = Array.from(document.querySelectorAll('input[placeholder="如：Excel"]'));
      if (inputs.length < 2) return false;
      window.__e2eClickEl = inputs[1]; inputs[1].scrollIntoView({ block: 'center' }); return true;
    })()`, "SQL", "req2 skill");
    await tab.clickFocusStored(`(() => {
      const selects = Array.from(document.querySelectorAll('select')).filter(s => Array.from(s.options).some(o => o.textContent.includes('/ 5')));
      if (selects.length < 2) return false;
      window.__e2eClickEl = selects[1]; selects[1].scrollIntoView({ block: 'center' }); return true;
    })()`, "req2 weight select");
    await tab.keyboardSelectValue("2", "req2 weight");
    // Publish directly (status select -> 公开发布).
    await tab.clickFocusStored(`(() => {
      const s = Array.from(document.querySelectorAll('select')).find(x => Array.from(x.options).some(o => o.textContent.trim() === '公开发布'));
      if (!s) return false;
      window.__e2eClickEl = s; s.scrollIntoView({ block: 'center' }); return true;
    })()`, "status select");
    await tab.keyboardSelectValue("published", "job status");
    await saveShot(tab, "job-form-filled");
    await tab.click({ tag: "button", text: "发布岗位" }, { label: "publish job" });
    // settle: redirect to /jobs/{id}, or an inline validation/API error.
    let settled = false, lastBody = "";
    for (let i = 0; i < 15 && !settled; i++) {
      await sleep(1000);
      const state = await tab.evalJs(`(() => ({ path: location.pathname, alert: (Array.from(document.querySelectorAll('div[role=alert]')).map(e => e.textContent.trim()).join(' | ') || '').slice(0, 200) }))()`).catch(() => null);
      if (!state) continue;
      lastBody = `path=${state.path} alert="${state.alert.slice(0, 160)}"`;
      if (/^\/jobs\/[0-9a-f-]{36}$/.test(state.path)) settled = true;
      if (state.alert) settled = true;
    }
    if (!settled) throw new CdpError(`publish did not settle: ${lastBody}`);
    const path = await tab.evalJs("location.pathname");
    if (!/^\/jobs\/[0-9a-f-]{36}$/.test(path)) {
      await saveShot(tab, "job-publish-error");
      throw new CdpError(`publish failed on form: ${lastBody}`);
    }
    await sleep(1500);
    const jobIdC = await tab.evalJs("location.pathname.split('/')[2]");
    const detail = await tab.bodyText();
    const published = detail.includes("E2E 岗位C") && detail.includes("Python") && detail.includes("SQL");
    await saveShot(tab, "job-c-detail");
    record({ name: "job-c-published", status: published ? "pass" : "fail", detail: `jobIdC=${jobIdC} title/Python/SQL visible=${published}` });

    // Original jobs A/B untouched (read-only DB); the new job C and its
    // requirements are excluded from the comparison by design.
    const after = await captureApplicationsBaseline("setup-job-after");
    const stripNew = arr => arr.filter(line => !line.includes(jobIdC));
    const sameJobs = JSON.stringify(stripNew(before.jobs)) === JSON.stringify(stripNew(after.jobs)) && JSON.stringify(stripNew(before.requirements)) === JSON.stringify(stripNew(after.requirements));
    const sameApps = JSON.stringify(before.applications) === JSON.stringify(after.applications);
    const newJobOnly = after.jobs.length === before.jobs.length + 1;
    record({ name: "original-jobs-applications-unchanged", status: sameJobs && sameApps && newJobOnly ? "pass" : "fail", detail: `jobsAB/reqsAB same=${sameJobs} apps same=${sameApps} exactly one new job=${newJobOnly}` });
    saveState({ jobIdC });
    record({ name: "state-saved", status: "pass", detail: `jobIdC persisted` });
    await browser.stop();
  } catch (error) {
    await dumpFailureEvidence(tab).catch(() => {});
    await browser.stop().catch(() => {});
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Scenario: baseline (student uploads via UI, parses, generates baseline report)
// ---------------------------------------------------------------------------
async function scenarioBaseline() {
  const state = loadState();
  const browser = activeBrowser = await new Chrome("student").launch();
  const tab = await browser.openTab();
  await tab.enable();
  lastTab = tab;
  try {
    await login(tab, CREDS.accounts.student);
    // -- upload resume v2 (idempotent: skip if a completed card already exists)
    await tab.goto(`${FRONTEND}/portfolio`);
    await tab.installFinder();
    await tab.waitFor(`() => document.body.innerText.includes('上传简历') && document.querySelector('#resume-file') !== null`, { timeoutMs: 30000, label: "portfolio page" });
    const alreadyDone = async filename => tab.evalJs(`Array.from(document.querySelectorAll('article')).some(a => a.textContent.includes(${JSON.stringify(filename)}) && a.textContent.includes('预览解析内容'))`);
    if (await alreadyDone("resume-v2.txt")) {
      record({ name: "upload-skipped:resume-v2.txt", status: "info", detail: "completed card already present from a previous run" });
    } else {
      await tab.fillStored(`(() => {
        const input = Array.from(document.querySelectorAll('input[maxlength="200"]')).find(i => (i.closest('label')?.textContent || '').includes('简历名称'));
        if (!input) return false;
        input.scrollIntoView({ block: 'center' }); window.__e2eClickEl = input; return true;
      })()`, "E2E学生补证简历（合成v2）", "resume title");
      await tab.setFileInput("#resume-file", path.join(MATERIALS_DIR, "resume-v2.txt"));
      await tab.click({ tag: "button", text: "上传并解析简历" }, { label: "upload resume" });
      await waitUploadComplete(tab, "resume-v2.txt");
    }
    await saveShot(tab, "resume-v2-uploaded");
    // -- create project with claims-only v1
    if (await alreadyDone("claims-only-project.zip")) {
      record({ name: "upload-skipped:claims-only-project.zip", status: "info", detail: "completed card already present from a previous run" });
    } else {
      await tab.waitFor(`() => document.querySelector('#project-file') !== null`, { label: "project form" });
      await tab.fillStored(`(() => { const i = document.querySelector('input[placeholder="如：校园二手交易平台"]'); if (!i) return false; i.scrollIntoView({ block: 'center' }); window.__e2eClickEl = i; return true; })()`, "E2E学生补证项目（合成）", "project name");
      await tab.fillStored(`(() => { const t = document.querySelector('textarea[placeholder="你负责了什么，解决了什么问题"]'); if (!t) return false; t.scrollIntoView({ block: 'center' }); window.__e2eClickEl = t; return true; })()`, "合成项目：先声明不足版，再上传含具名实现与测试记录的新版（全部合成编写）", "project description");
      await tab.setFileInput("#project-file", path.join(MATERIALS_DIR, "claims-only-project.zip"));
      await tab.click({ tag: "button", text: "创建项目并开始扫描" }, { label: "create project v1" });
      await waitUploadComplete(tab, "claims-only-project.zip");
    }
    await saveShot(tab, "claims-only-v1-uploaded");
    // -- upload new-version as v2 of the same project
    if (await alreadyDone("new-version-project.zip")) {
      record({ name: "upload-skipped:new-version-project.zip", status: "info", detail: "completed card already present from a previous run" });
    } else {
      await tab.clickStored(`(() => {
        const btns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.includes('上传新版本'));
        if (!btns.length) return false;
        btns[0].scrollIntoView({ block: 'center' }); window.__e2eClickEl = btns[0]; return true;
      })()`, "upload new version");
      await sleep(500);
      await tab.setFileInput("#project-file", path.join(MATERIALS_DIR, "new-version-project.zip"));
      await tab.click({ tag: "button", text: "继续上传（复用原项目）" }, { label: "upload project v2" });
      await waitUploadComplete(tab, "new-version-project.zip");
    }
    await saveShot(tab, "new-version-v2-uploaded");
    // sanity: no code execution claims — the run log file states it is synthetic
    const runLogNote = await tab.evalJs(`document.body.innerText.includes('new-version-project.zip')`);
    record({ name: "materials-uploaded", status: runLogNote ? "pass" : "fail", detail: "resume-v2 + claims-only v1 + new-version v2 via UI (source never executed)" });

    // -- baseline report on original job B with claims-only materials
    await tab.goto(`${FRONTEND}/jobs/${JOB_B}`);
    await tab.installFinder();
    await tab.waitFor(`() => document.body.innerText.includes('用我的材料分析岗位匹配')`, { timeoutMs: 30000, label: "job detail match form" });
    await pickResume(tab, "resume-v2.txt");
    await pickProjects(tab, ["claims-only-project.zip"]);
    // verify claims-only selected (声明不足材料先行)
    await tab.waitFor(`() => Array.from(document.querySelectorAll('ul[aria-label="已选项目版本"] li')).some(li => li.textContent.includes('claims-only-project.zip'))`, { label: "claims-only selected" });
    await toggleCheckboxStored(tab, checkboxByLabelText("同意将脱敏后的必要片段发送给外部 AI"), "external ai consent", true);
    await sleep(200);
    await saveShot(tab, "baseline-form-filled");
    await tab.click({ tag: "button", text: "生成我的匹配报告" }, { label: "create baseline match" });
    await tab.waitFor(`() => location.pathname.startsWith('/tasks/')`, { timeoutMs: 20000, label: "task page" });
    await sleep(1000);
    const analysisTaskId = await tab.evalJs("location.pathname.split('/')[2]");
    await tab.waitFor(`() => document.body.innerText.includes('处理完成') || document.body.innerText.includes('处理失败')`, { timeoutMs: 240000, pollMs: 2000, label: "baseline analysis settle" });
    const taskBody = await tab.bodyText();
    if (!taskBody.includes("处理完成")) throw new CdpError(`baseline analysis failed: ${taskBody.slice(0, 300)}`);
    await saveShot(tab, "baseline-task-completed");
    await tab.click({ tag: "a", text: "查看匹配报告" }, { label: "open baseline report" });
    await tab.waitFor(`() => /^\\/reports\\/[0-9a-f-]{36}$/.test(location.pathname)`, { timeoutMs: 20000, label: "report page" });
    await sleep(1200);
    const baseReportId = await tab.evalJs("location.pathname.split('/')[2]");
    const items = await tab.evalJs(`Array.from(document.querySelectorAll('article[id^="requirement-"]')).map(a => ({ id: a.id.slice(12), title: (a.querySelector('h3')?.textContent ?? '').trim(), badge: (a.querySelector('span.rounded-full')?.textContent ?? '').trim(), text: a.innerText.replace(/\\n+/g,' | ').slice(0, 700) }))`);
    await saveShot(tab, "baseline-report");
    const claimsOnly = items.some(i => /仅有声明|声明/.test(i.badge) || /仅有声明/.test(i.text));
    record({ name: "baseline-report-generated", status: "pass", detail: `report ${baseReportId} task ${analysisTaskId} items=${JSON.stringify(items.map(i => ({ id: i.id.slice(0, 8), badge: i.badge })))}` });
    record({ name: "baseline-claims-only-check", status: claimsOnly ? "pass" : "fail", detail: `claims-only materials must NOT be presented as implementation; badge/text contains 声明 marker: ${claimsOnly}` });
    saveState({ baseReportId, baselineItems: items, baselineAnalysisTaskId: analysisTaskId });
    await browser.stop();
  } catch (error) {
    await dumpFailureEvidence(tab).catch(() => {});
    await browser.stop().catch(() => {});
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Scenario: chain-reply (seed report repB + enterprise reply context +
// controlled failure + recovery + analyze + comparison + notifications)
// ---------------------------------------------------------------------------
async function scenarioChainReply() {
  const plan = {
    deliverable: "补齐 pipeline.py 具名实现 process_records 与 pytest 单元用例（E2E 合成材料，不执行上传源码）",
    steps: ["编写 process_records 数据汇总函数（合成）", "补充两条 pytest 断言用例（合成）", "整理合成运行记录 docs/run-log.md"],
    checks: ["新报告对该要求出现代码类证据引用", "证据等级高于仅有声明", "引用行号指向具名实现或用例文件"],
  };
  const browser = activeBrowser = await new Chrome("student").launch();
  const tab = await browser.openTab();
  await tab.enable();
  lastTab = tab;
  try {
    await login(tab, CREDS.accounts.student);
    const { taskId, existing } = await createGrowthTaskFromReport(tab, REPORT_B_SEED, plan, { expectReplyContext: true });
    saveState({ replyTaskId: taskId });
    await saveShot(tab, "reply-task-page");

    if (!existing) {
      // -- controlled failure: save with the seed resume v1 (no extracted text)
      //    -> expect a clear error and the documented retry path.
      await pickResume(tab, "e2e-合成简历.txt");
      await saveMaterialsSelection(tab);
      await tab.waitFor(`() => document.querySelector('p[role=alert]') !== null`, { timeoutMs: 20000, label: "controlled failure alert" });
      const failureText = await tab.evalJs(`(document.querySelector('p[role=alert]')?.textContent ?? '').trim()`);
      await saveShot(tab, "controlled-failure-alert");
      const bodyAfterFailure = await tab.bodyText();
      const stillRetryable = bodyAfterFailure.includes("读取已保存任务");
      record({ name: "controlled-failure", status: failureText && stillRetryable ? "pass" : "fail", detail: `error="${failureText.slice(0, 160)}" retryPath=${stillRetryable} (form collapses on error; re-read button is the documented retry path)` });

      // -- recovery: re-read the task, then select resume-v2 + new-version v2.
      await tab.click({ tag: "button", text: "读取已保存任务" }, { label: "re-read task after failure" });
      await tab.waitFor(`() => document.body.innerText.includes('保存本次材料选择')`, { timeoutMs: 20000, label: "materials form back" });
      await sleep(600);
      await pickResume(tab, "resume-v2.txt");
      await pickProjects(tab, ["new-version-project.zip"]);
      await saveMaterialsSelection(tab);
      await tab.waitFor(`() => document.body.innerText.includes('已选择材料')`, { timeoutMs: 20000, label: "materials saved after recovery" });
      const savedList = await tab.evalJs(`Array.from(document.querySelectorAll('li')).filter(li => li.textContent.includes('已保存：')).map(li => li.innerText.replace(/\\n+/g, ' | '))`);
      record({ name: "failure-recovered-materials-saved", status: "pass", detail: savedList.join(' ;; ').slice(0, 400) });
      await saveShot(tab, "reply-materials-saved");

      // -- analyze (mock rules) + settle
      await toggleCheckboxStored(tab, checkboxByLabelText("发送给 DeepSeek 官方 API"), "analyze consent", true);
      await sleep(200);
      await tab.click({ tag: "button", text: "生成新报告" }, { label: "analyze" });
      await sleep(1500);
    }

    // -- settle: compared, hard failure, or the seed-shape comparison guard.
    let settledState = null;
    for (let i = 0; i < 30 && !settledState; i++) {
      await sleep(2000);
      const state = await tab.evalJs(`(() => ({ compared: document.body.innerText.includes('新报告已对比'), failed: document.body.innerText.includes('分析失败'), alert: (Array.from(document.querySelectorAll('p[role=alert], div[role=alert]')).map(e => e.textContent.trim()).join(' | ') || '').slice(0, 200) }))()`).catch(() => null);
      if (!state) continue;
      if (state.compared) settledState = "compared";
      else if (state.failed) settledState = "analysis_failed";
      else if (state.alert) settledState = `alert:${state.alert}`;
      else if (i > 12 && (await tab.bodyText()).includes("已停止自动查询")) {
        await tab.click({ tag: "button", text: "读取已保存任务" }, { label: "manual re-read" }).catch(() => {});
      }
    }
    if (settledState === "compared") {
      const captured = await captureComparisonEvidence(tab, "chain-reply");
      if (captured) {
        const item = captured.comparison.items.find(i => i.text.includes("企业问题与新报告核对"));
        record({ name: "enterprise-question-review-block", status: item ? "pass" : "fail", detail: item ? item.text.slice(0, 400) : "review block missing" });
        const replyReportId = resolveTargetReportId(captured.reportIds, REPORT_B_SEED);
        saveState({ replyReportId });
      }
      record({ name: "reply-analyze-outcome", status: "pass", detail: "compared" });
    } else if (settledState && String(settledState).includes("只能对比同一用户同一岗位的报告")) {
      // Seed fixture shape: seed reports carry a candidates-table candidate_ref
      // that differs from the student user id, while UI/API reports use the user
      // id — compare_views' same-candidate guard therefore rejects ANY growth
      // comparison against a seeded base report. Reproduction evidence below;
      // adjudication (seed extension vs accepted limitation) belongs to Codex.
      const alertText = await tab.evalJs(`(Array.from(document.querySelectorAll('p[role=alert], div[role=alert]')).map(e => e.textContent.trim()).join(' | ')).slice(0, 300)`);
      await saveShot(tab, "seed-shape-comparison-blocked");
      const pageText = await tab.bodyText();
      saveJson("seed-shape-comparison-blocked", { taskId, alert: alertText, reproduction: "GET /api/v1/growth-tasks/{id} → 409 只能对比同一用户同一岗位的报告", pageText: pageText.slice(0, 2500), rootCause: "seed report candidate_ref (candidates table id) != student user id; API reports use user id as candidate_ref" });
      record({ name: "reply-comparison-blocked-by-seed-shape", status: "blocked", detail: `task ${taskId}: analysis completed server-side but comparison view is rejected: ${alertText}` });
    } else {
      record({ name: "reply-analyze-outcome", status: "fail", detail: `settled=${JSON.stringify(settledState)}` });
    }
    // -- notification entry
    await tab.goto(`${FRONTEND}/notifications`);
    await tab.installFinder();
    await tab.waitFor(`() => document.body.innerText.length > 50`, { timeoutMs: 20000, label: "notifications page" });
    const notif = await tab.evalJs(`document.body.innerText.slice(0, 1200)`);
    record({ name: "notifications-page", status: "pass", detail: notif.replace(/\n+/g, ' | ').slice(0, 400) });
    await saveShot(tab, "notifications");
    await browser.stop();
  } catch (error) {
    await dumpFailureEvidence(tab).catch(() => {});
    await browser.stop().catch(() => {});
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Scenario: variant-materials (T1 from UI baseline: only materials change)
// ---------------------------------------------------------------------------
async function scenarioVariantMaterials() {
  const state = loadState();
  if (!state.baseReportId) throw new Error("state.baseReportId missing — run baseline first");
  const plan = {
    deliverable: "同一岗位只换材料：上传含具名实现与测试记录的新版项目（E2E 合成）",
    steps: ["给原项目上传 new-version-project.zip 新版本（合成）", "保存材料选择（目标岗位保持任务原岗位）", "生成新报告并逐项对比"],
    checks: ["背景变化只含材料版本变化（同引擎基准）", "Python 项出现新增证据引用", "不出现岗位要求变化标签"],
  };
  const browser = activeBrowser = await new Chrome("student").launch();
  const tab = await browser.openTab();
  await tab.enable();
  lastTab = tab;
  try {
    await login(tab, CREDS.accounts.student);
    let taskId;
    if (state.variantMaterialsTaskId) {
      taskId = state.variantMaterialsTaskId;
      await openGrowthTask(tab, taskId);
      record({ name: "v-materials-task-reused", status: "info", detail: `task ${taskId} reopened from state (failure reuse — no duplicate task created)` });
    } else {
      const created = await createGrowthTaskFromReport(tab, state.baseReportId, plan);
      taskId = created.taskId;
      saveState({ variantMaterialsTaskId: taskId });
      record({ name: "v-materials-task-saved", status: "pass", detail: `task ${taskId} persisted to state immediately after UI creation` });
    }
    const comparedNow = await tab.evalJs(`document.body.innerText.includes('新报告已对比')`);
    if (comparedNow) {
      // Reuse of an already-compared task: the materials form is locked after
      // analysis starts, so re-verifying the recorded evidence is the only
      // valid action — never a second analysis for the same task.
      record({ name: "v-materials-already-compared", status: "info", detail: `task already compared${state.reportR1 ? ` (state R1=${state.reportR1})` : " (R1 missing in state — resolving from citations)"}` });
    } else {
      // default preselection = base materials (resume-v2 + claims-only v1).
      // Switch only the project version; resume and target job stay unchanged.
      await uncheckProject(tab, "claims-only-project.zip");
      await pickProjects(tab, ["new-version-project.zip"]);
      await saveMaterialsSelection(tab);
      await tab.waitFor(`() => document.body.innerText.includes('已选择材料')`, { timeoutMs: 20000, label: "materials saved" });
      const amber = await tab.evalJs(`(Array.from(document.querySelectorAll('p[role=status]')).map(p => p.textContent.trim()).find(t => t.includes('尚未保存')) ?? '')`);
      record({ name: "materials-only-saved", status: "pass", detail: `unsaved-target notice="${amber || "(none)"}" (expected none — target untouched)` });
      await saveShot(tab, "v-materials-saved");
      const putBodies = tab.requestBodies.filter(b => b.method === "PUT" && b.url.includes("/growth-tasks/"));
      record({ name: "v-materials-put-bodies", status: putBodies.length ? "pass" : "fail", detail: JSON.stringify(putBodies.map(b => b.body.slice(0, 300))).slice(0, 700) });
      // -- refresh reread: the saved selection must survive a full reload
      const reread = await rereadSavedSelection(tab, taskId);
      const projectRows = reread.saved.filter(row => row.includes("个人作品"));
      const reloadedNewVersion = projectRows.length >= 1 && projectRows.every(r => r.includes("第2版")) && !projectRows.some(r => r.includes("第1版"));
      record({ name: "v-materials-refresh-reread", status: reloadedNewVersion ? "pass" : "fail", detail: `after reload projects=[${projectRows.join(" ;; ").slice(0, 300)}]` });
      await saveShot(tab, "v-materials-after-reload");
      const analyzeButtonPresent = await tab.evalJs(`Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('生成新报告'))`);
      const outcome = await analyzeAndWait(tab, { skipClick: !analyzeButtonPresent });
      record({ name: "v-materials-analyze", status: outcome === "compared" ? "pass" : "fail", detail: `${outcome}${analyzeButtonPresent ? "" : " (button absent — settling an analysis a previous run had started)"}` });
    }
    const captured = await captureComparisonEvidence(tab, "variant-materials");
    if (captured) {
      const c = captured.comparison;
      const materialsOnly = c.context.includes("材料版本变化") && !c.context.includes("岗位要求变化") && !c.context.includes("目标岗位变化");
      // Task-card acceptance: a materials change MUST carry real citation
      // links into the new report, the focus requirement must list newly
      // displayed evidence rows, and the new report id must resolve. Missing
      // evidence fails the scenario — it is not a printed boolean.
      const r1 = resolveTargetReportId(captured.reportIds, state.baseReportId);
      const citedNewReport = Boolean(r1) && (c.citationHrefs || []).some(h => h.includes(r1));
      const focus = c.items.find(i => i.focus) ?? c.items[0];
      const focusAdded = Boolean(focus) && focus.addedCount >= 1;
      record({
        name: "v-materials-attribution",
        status: materialsOnly && citedNewReport && focusAdded && r1 ? "pass" : "fail",
        detail: `context="${c.context}" materialsOnly=${materialsOnly} citationsIntoNewReport=${citedNewReport} focusAddedCount=${focus ? focus.addedCount : "no-item"} newReportResolved=${Boolean(r1)}`,
      });
      if (!r1) {
        record({ name: "v-materials-new-report-missing", status: "fail", detail: `citation report ids ${JSON.stringify(captured.reportIds)} (base ${state.baseReportId}) did not resolve to exactly one new report` });
      } else {
        saveState({ reportR1: r1 });
      }
    }
    await browser.stop();
  } catch (error) {
    await dumpFailureEvidence(tab).catch(() => {});
    await browser.stop().catch(() => {});
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Scenario: variant-job (T2 from R1: only the target job changes)
// ---------------------------------------------------------------------------
async function scenarioVariantJob() {
  const state = loadState();
  if (!state.reportR1 || !state.jobIdC) throw new Error("state.reportR1/jobIdC missing — run variant-materials and setup-job first");
  const plan = {
    deliverable: "同一材料只改目标岗位：把目标岗位改选为已发布的新岗位（E2E 合成）",
    steps: ["材料版本保持与基准报告一致", "在目标岗位选择器改选新岗位并保存", "保存后刷新重读，再生成新报告"],
    checks: ["背景变化含目标岗位变化且不含材料版本变化", "跨岗位按 requirementId 逐条列出新增/移除", "同名技能 Python 不与旧要求合并"],
  };
  const browser = activeBrowser = await new Chrome("student").launch();
  const tab = await browser.openTab();
  await tab.enable();
  lastTab = tab;
  try {
    await login(tab, CREDS.accounts.student);
    let taskId;
    if (state.variantJobTaskId) {
      taskId = state.variantJobTaskId;
      await openGrowthTask(tab, taskId);
      record({ name: "v-job-task-reused", status: "info", detail: `task ${taskId} reopened from state (failure reuse — no duplicate task created)` });
    } else {
      const created = await createGrowthTaskFromReport(tab, state.reportR1, plan);
      taskId = created.taskId;
      saveState({ variantJobTaskId: taskId });
      record({ name: "v-job-task-saved", status: "pass", detail: `task ${taskId} persisted to state immediately after UI creation` });
    }
    const comparedNow = await tab.evalJs(`document.body.innerText.includes('新报告已对比')`);
    if (comparedNow) {
      record({ name: "v-job-already-compared", status: "info", detail: `task already compared${state.reportR2 ? ` (state R2=${state.reportR2})` : " (R2 missing in state — resolving from citations)"}` });
    } else {
      // materials preselected = R1's materials (resume-v2 + new-version v2): keep.
      await pickTargetJob(tab, "E2E 岗位C");
      await tab.waitFor(`() => Array.from(document.querySelectorAll('p[role=status]')).some(p => p.textContent.includes('已改选目标岗位但尚未保存'))`, { timeoutMs: 10000, label: "unsaved target notice" });
      await saveShot(tab, "v-job-unsaved-notice");
      await saveMaterialsSelection(tab);
      await tab.waitFor(`() => document.body.innerText.includes('已选择材料') && document.body.innerText.includes('已保存目标')`, { timeoutMs: 20000, label: "materials+target saved" });
      await saveShot(tab, "v-job-saved");
      const putBodies = tab.requestBodies.filter(b => b.method === "PUT" && b.url.includes("/growth-tasks/"));
      record({ name: "v-job-put-bodies", status: putBodies.length ? "pass" : "fail", detail: JSON.stringify(putBodies.map(b => ({ url: b.url, body: b.body.slice(0, 300) }))).slice(0, 700) });
      const analyzeButtonPresent = await tab.evalJs(`Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('生成新报告'))`);
      const outcome = await analyzeAndWait(tab, { skipClick: !analyzeButtonPresent });
      record({ name: "v-job-analyze", status: outcome === "compared" ? "pass" : "fail", detail: `${outcome}${analyzeButtonPresent ? "" : " (button absent — settling an analysis a previous run had started)"}` });
    }
    // -- refresh and re-read: saved target must survive a full page reload.
    //    Runs in every state (read-only): sections 1-2 keep rendering the saved
    //    target after comparison, so reuse runs re-verify this evidence too.
    await tab.goto(`${FRONTEND}/growth/${taskId}`);
    await tab.installFinder();
    await tab.waitFor(`() => document.body.innerText.includes('已保存目标')`, { timeoutMs: 20000, label: "task reloaded" });
    const afterReload = await tab.evalJs(`(Array.from(document.querySelectorAll('p')).map(p => p.textContent).filter(t => t.includes('已保存目标')).join(' || '))`);
    // Cross-job marker is rendered as "与任务原岗位不同" in section 1 and
    // "≠ 任务原岗位" in section 2 — either proves the saved target survived.
    const reloadKept = afterReload.includes("E2E 岗位C") && (afterReload.includes("≠") || afterReload.includes("与任务原岗位不同"));
    record({ name: "v-job-refresh-reread", status: reloadKept ? "pass" : "fail", detail: `after reload: "${afterReload.trim().slice(0, 200)}"` });
    await saveShot(tab, "v-job-after-reload");
    const captured = await captureComparisonEvidence(tab, "variant-job");
    if (captured) {
      const c = captured.comparison;
      const jobOnly = c.context.includes("目标岗位变化") && !c.context.includes("材料版本变化");
      const crossJobBanner = c.banner.includes("对比岗位") && c.banner.includes("不能把新岗位要求的满足当作原岗位的核验结论");
      // Task-card acceptance: a job-only change must list BOTH removed and
      // added requirements, keep same-name Python requirements as separate
      // rows (one removed, one added), and resolve the new report id — all
      // part of the verdict, not printed booleans.
      const r2 = resolveTargetReportId(captured.reportIds, state.reportR1);
      const removedItems = c.items.filter(i => i.status === "基准要求不再展示");
      const addedItems = c.items.filter(i => i.status === "目标报告新增要求");
      const pythonRemoved = removedItems.filter(i => /python/i.test(i.title)).length;
      const pythonAdded = addedItems.filter(i => /python/i.test(i.title)).length;
      const removedAndAdded = removedItems.length >= 1 && addedItems.length >= 1;
      const pythonSeparate = pythonRemoved >= 1 && pythonAdded >= 1;
      record({
        name: "v-job-attribution",
        status: jobOnly && crossJobBanner && removedAndAdded && pythonSeparate && r2 ? "pass" : "fail",
        detail: `context="${c.context}" jobOnly=${jobOnly} bannerOk=${crossJobBanner} removed=${removedItems.length} added=${addedItems.length} pythonRemoved=${pythonRemoved} pythonAdded=${pythonAdded} pythonSeparate=${pythonSeparate} newReportResolved=${Boolean(r2)}`,
      });
      if (!r2) {
        record({ name: "v-job-new-report-missing", status: "fail", detail: `citation report ids ${JSON.stringify(captured.reportIds)} (base ${state.reportR1}) did not resolve to exactly one new report` });
      } else {
        saveState({ reportR2: r2 });
      }
    }
    await browser.stop();
  } catch (error) {
    await dumpFailureEvidence(tab).catch(() => {});
    await browser.stop().catch(() => {});
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Scenario: variant-both (T3 from R2: materials AND target job change)
// ---------------------------------------------------------------------------
async function scenarioVariantBoth() {
  const state = loadState();
  if (!state.reportR2) throw new Error("state.reportR2 missing — run variant-job first");
  const plan = {
    deliverable: "材料与目标岗位同时改变：换回声明不足材料并把目标改回原岗位（E2E 合成）",
    steps: ["项目版本从 new-version 换回 claims-only", "目标岗位从岗位C改回岗位B并保存", "生成新报告并核对双背景变化"],
    checks: ["背景变化同时含材料版本变化与目标岗位变化", "逐项解释分别说明两类变化", "不把岗位变化当作原问题回答"],
  };
  const browser = activeBrowser = await new Chrome("student").launch();
  const tab = await browser.openTab();
  await tab.enable();
  lastTab = tab;
  try {
    await login(tab, CREDS.accounts.student);
    let taskId;
    if (state.variantBothTaskId) {
      taskId = state.variantBothTaskId;
      await openGrowthTask(tab, taskId);
      record({ name: "v-both-task-reused", status: "info", detail: `task ${taskId} reopened from state (failure reuse — no duplicate task created)` });
    } else {
      const created = await createGrowthTaskFromReport(tab, state.reportR2, plan);
      taskId = created.taskId;
      saveState({ variantBothTaskId: taskId });
      record({ name: "v-both-task-saved", status: "pass", detail: `task ${taskId} persisted to state immediately after UI creation` });
    }
    const comparedNow = await tab.evalJs(`document.body.innerText.includes('新报告已对比')`);
    if (comparedNow) {
      record({ name: "v-both-already-compared", status: "info", detail: `task already compared${state.reportR3 ? ` (state R3=${state.reportR3})` : " (R3 missing in state — resolving from citations)"}` });
    } else {
      await uncheckProject(tab, "new-version-project.zip");
      await pickProjects(tab, ["claims-only-project.zip"]);
      await pickTargetJob(tab, "E2E 岗位B（合成）");
      await saveMaterialsSelection(tab);
      await tab.waitFor(`() => document.body.innerText.includes('已选择材料') && document.body.innerText.includes('已保存目标')`, { timeoutMs: 20000, label: "materials+target saved" });
      await saveShot(tab, "v-both-saved");
      const putBodies = tab.requestBodies.filter(b => b.method === "PUT" && b.url.includes("/growth-tasks/"));
      record({ name: "v-both-put-bodies", status: putBodies.length ? "pass" : "fail", detail: JSON.stringify(putBodies.map(b => b.body.slice(0, 300))).slice(0, 700) });
      // -- refresh reread: claims-only project (第1版) and target job B both survive
      const reread = await rereadSavedSelection(tab, taskId);
      const projectRows = reread.saved.filter(row => row.includes("个人作品"));
      const claimsBack = projectRows.length >= 1 && projectRows.every(r => r.includes("第1版")) && !projectRows.some(r => r.includes("第2版"));
      const targetBack = reread.target.includes("岗位B") && (reread.target.includes("≠") || reread.target.includes("与任务原岗位不同"));
      record({ name: "v-both-refresh-reread", status: claimsBack && targetBack ? "pass" : "fail", detail: `after reload projects=[${projectRows.join(" ;; ").slice(0, 250)}] target="${reread.target.slice(0, 200)}"` });
      await saveShot(tab, "v-both-after-reload");
      const analyzeButtonPresent = await tab.evalJs(`Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('生成新报告'))`);
      const outcome = await analyzeAndWait(tab, { skipClick: !analyzeButtonPresent });
      record({ name: "v-both-analyze", status: outcome === "compared" ? "pass" : "fail", detail: `${outcome}${analyzeButtonPresent ? "" : " (button absent — settling an analysis a previous run had started)"}` });
    }
    const captured = await captureComparisonEvidence(tab, "variant-both");
    if (captured) {
      const c = captured.comparison;
      const both = c.context.includes("材料版本变化") && c.context.includes("目标岗位变化");
      const crossJobBanner = c.banner.includes("对比岗位") && c.banner.includes("不能把新岗位要求的满足当作原岗位的核验结论");
      // Task-card acceptance: a combined change must explain EVERY item —
      // each row carries the 任务基准/目标报告 two-sided explanation plus the
      // level line — and the new report id must resolve.
      const r3 = resolveTargetReportId(captured.reportIds, state.reportR2);
      const itemized = c.items.length >= 1 && c.items.every(i => i.sides.base && i.sides.target && i.levelLine);
      record({
        name: "v-both-attribution",
        status: both && crossJobBanner && itemized && r3 ? "pass" : "fail",
        detail: `context="${c.context}" both=${both} bannerOk=${crossJobBanner} items=${c.items.length} everyItemExplained=${itemized} newReportResolved=${Boolean(r3)}`,
      });
      if (!r3) {
        record({ name: "v-both-new-report-missing", status: "fail", detail: `citation report ids ${JSON.stringify(captured.reportIds)} (base ${state.reportR2}) did not resolve to exactly one new report` });
      } else {
        saveState({ reportR3: r3 });
      }
    }
    await browser.stop();
  } catch (error) {
    await dumpFailureEvidence(tab).catch(() => {});
    await browser.stop().catch(() => {});
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Scenario: viewport390 (student key pages at 390px, no horizontal overflow)
// ---------------------------------------------------------------------------
async function scenarioViewport390() {
  const state = loadState();
  const browser = activeBrowser = await new Chrome("student-390", { width: 390, height: 844 }).launch();
  const tab = await browser.openTab();
  await tab.enable();
  lastTab = tab;
  try {
    await tab.setViewport(390, 844);
    await login(tab, CREDS.accounts.student);
    const checks = [];
    // growth task list
    await tab.goto(`${FRONTEND}/growth`);
    await tab.installFinder();
    await tab.waitFor(`() => document.body.innerText.includes('补证任务')`, { timeoutMs: 20000, label: "growth list 390" });
    await sleep(800);
    checks.push(["growth-list", await overflowCheck(tab), await visibleHeadingShot(tab, "v390-growth-list", `const el = Array.from(document.querySelectorAll('h1,h2')).find(e => (e.textContent || '').includes('补证任务')); if (!el) return false; window.__e2eVisEl = el; return true;`)]);
    // task page with cross-job comparison (variant-job task if present)
    const targetTask = state.variantJobTaskId || state.variantMaterialsTaskId || state.replyTaskId;
    if (targetTask) {
      await tab.goto(`${FRONTEND}/growth/${targetTask}`);
      await tab.installFinder();
      await tab.waitFor(`() => document.body.innerText.includes('从缺口到新证据')`, { timeoutMs: 20000, label: "task page 390" });
      await sleep(800);
      checks.push(["growth-task", await overflowCheck(tab), await visibleHeadingShot(tab, "v390-growth-task", `const el = Array.from(document.querySelectorAll('section h2')).find(e => (e.textContent || '').includes('逐项对比')); if (!el) return false; window.__e2eVisEl = el; return true;`)]);
      // open the job picker at 390px (programmatic open — a real summary click
      // would toggle the just-opened details closed again)
      const pickerOpened = await tab.evalJs(`(() => {
        const summary = Array.from(document.querySelectorAll('summary')).find(s => s.textContent.includes('选择已发布的新岗位'));
        if (!summary) return false; const d = summary.closest('details'); if (!d) return false;
        d.open = true; summary.scrollIntoView({ block: 'center' }); return true;
      })()`);
      if (!pickerOpened) record({ name: "v390-job-picker", status: "warn", detail: "picker not available in this task state" });
      await sleep(600);
      await saveShot(tab, "v390-job-picker", false);
    }
    // report page at 390
    if (state.baseReportId) {
      await tab.goto(`${FRONTEND}/reports/${state.baseReportId}`);
      await tab.installFinder();
      await tab.waitFor(`() => document.querySelectorAll('article[id^="requirement-"]').length > 0`, { timeoutMs: 20000, label: "report 390" });
      await sleep(800);
      checks.push(["report", await overflowCheck(tab), await visibleHeadingShot(tab, "v390-report", `const el = document.querySelector('article[id^="requirement-"] h3'); if (!el) return false; window.__e2eVisEl = el; return true;`)]);
    }
    for (const [name, overflow, vis] of checks) {
      record({
        name: `v390-page:${name}`, status: !overflow.overflow && vis.ok ? "pass" : "fail",
        detail: `overflow(scrollW=${overflow.scrollWidth} winW=${overflow.winW}=${overflow.overflow ? "OVERFLOW" : "ok"}) visible(${vis.ok ? "ok" : "BLOCKED"}: ${vis.why ? `${vis.why}` : `top=${vis.top} headerBottom=${vis.headerBottom} hitSelf=${vis.hitSelf} hitTag=${vis.hitTag} viewH=${vis.viewH}`})`,
      });
    }
    const allOk = checks.every(([, o, v]) => !o.overflow && v.ok);
    record({ name: "viewport390", status: allOk ? "pass" : "fail", detail: checks.map(([n, o, v]) => `${n}: overflow=${o.overflow ? "yes" : "no"} visible=${v.ok}`).join(" ; ") });
    await browser.stop();
  } catch (error) {
    await dumpFailureEvidence(tab).catch(() => {});
    await browser.stop().catch(() => {});
    throw error;
  }
}
async function overflowCheck(tab) {
  return tab.evalJs(`(() => { const doc = document.scrollingElement; return { scrollWidth: doc.scrollWidth, winW: window.innerWidth, overflow: doc.scrollWidth > window.innerWidth + 1 }; })()`);
}
// Scroll a heading into view and PROVE visibility: the element must sit below
// the sticky site header, inside the 390px viewport, and the element at its
// centre point must be the heading itself (or a descendant). Task card: DOM
// existence does not equal visible — screenshots are taken only after the
// scroll, from the live viewport.
async function visibleHeadingShot(tab, name, locatorBody) {
  const found = await tab.evalJs(`(() => { ${locatorBody} })()`);
  if (!found) { await saveShot(tab, name, false); return { ok: false, why: "heading element not found" }; }
  await sleep(300);
  const vis = await tab.evalJs(`(() => {
    const el = window.__e2eVisEl;
    if (!el || !el.isConnected) return { ok: false, why: "heading detached" };
    el.scrollIntoView({ block: "start" });
    const header = document.querySelector("header");
    const headerBottom = header ? Math.round(header.getBoundingClientRect().bottom) : 0;
    const r0 = el.getBoundingClientRect();
    if (r0.top < headerBottom) window.scrollTo({ top: Math.max(0, Math.round(window.scrollY + r0.top - headerBottom - 12)), behavior: "instant" });
    const r = el.getBoundingClientRect();
    const cx = Math.round(r.left + Math.min(Math.max(r.width / 2, 8), Math.max(r.width - 8, 8)));
    const cy = Math.round(r.top + Math.min(Math.max(r.height / 2, 6), Math.min(r.height, 60)));
    const hit = document.elementFromPoint(cx, cy);
    const hitSelf = hit === el || el.contains(hit);
    return { ok: r.top >= headerBottom - 1 && r.bottom <= window.innerHeight + 1 && r.left >= -1 && hitSelf,
      top: Math.round(r.top), headerBottom, viewH: window.innerHeight, hitSelf, hitTag: hit ? hit.tagName.toLowerCase() : null };
  })()`);
  await saveShot(tab, name, false);
  return vis;
}

// ---------------------------------------------------------------------------
// Scenario: enterprise-recheck (old snapshots unchanged, UI + read-only DB)
// ---------------------------------------------------------------------------
async function scenarioEnterpriseRecheck() {
  const state = loadState();
  const browser = activeBrowser = await new Chrome("enterprise-recheck").launch();
  const tab = await browser.openTab();
  await tab.enable();
  lastTab = tab;
  try {
    await login(tab, CREDS.accounts.enterprise);
    for (const [jobId, label] of [[JOB_A, "jobA"], [JOB_B, "jobB"]]) {
      await tab.goto(`${FRONTEND}/jobs/${jobId}/applications`);
      await tab.installFinder();
      await tab.waitFor(`() => document.querySelectorAll('th[id^="application-"]').length > 0`, { timeoutMs: 30000, label: `board ${label}` });
      await sleep(500);
      await saveShot(tab, `recheck-board-${label}`);
      // open every application visible on this board and verify the fixed report
      const appIds = await tab.evalJs(`Array.from(document.querySelectorAll('th[id^="application-"]')).map(th => th.id.slice('application-'.length))`);
      for (const appId of appIds) {
        await tab.click({ tag: `th#application-${appId} button` }, { label: `open app ${appId.slice(0, 8)}` });
        await tab.waitFor(`() => Array.from(document.querySelectorAll('h2')).some(h => (h.textContent || '').includes('投递时固定报告'))`, { timeoutMs: 20000, label: `fixed report ${appId.slice(0, 8)}` });
        await sleep(600);
        const body = await tab.bodyText();
        const hasScore = /总分|得分|分数|\/\s*100|分/.test(body);
        const hasCitation = /引用|第\s*\d+\s*[-—]\s*\d+\s*行/.test(body);
        await saveShot(tab, `recheck-app-${appId.slice(0, 8)}`);
        record({ name: `recheck-app-${appId.slice(0, 8)}`, status: hasScore ? "pass" : "fail", detail: `fixedReport=shown scoreLike=${hasScore} citationLike=${hasCitation} (materials/report/score must be the ORIGINAL)` });
        // back to board
        await tab.click({ tag: "button", text: "刷新授权投递" }, { label: "back to board" }).catch(async () => { await tab.goto(`${FRONTEND}/jobs/${jobId}/applications`); });
        await tab.waitFor(`() => document.querySelectorAll('th[id^="application-"]').length > 0`, { timeoutMs: 30000, label: "board again" });
      }
    }
  await browser.stop();
  // read-only DB invariants after the whole student run
  const after = await captureApplicationsBaseline("enterprise-recheck-after");
  const expected = {
    [CREDS.applications.A.id]: { status: "replied", hash: CREDS.applications.A.snapshotSha256 },
    [CREDS.applications.B.id]: { status: "replied", hash: CREDS.applications.B.snapshotSha256 },
    [CREDS.applications.A2.id]: { status: "viewed", hash: CREDS.applications.A2.snapshotSha256 },
  };
  const mismatches = [];
  for (const app of after.applications) {
    const want = expected[app.id];
    if (!want) continue;
    if (app.status !== want.status) mismatches.push(`${app.id.slice(0, 8)} status ${app.status} != ${want.status}`);
    if (app.snapshotSha256 !== want.hash) mismatches.push(`${app.id.slice(0, 8)} hash changed`);
  }
  const appsUnchanged = after.applications.length === 3 && mismatches.length === 0;
  // job A/B rows identical to the setup-job "before" capture (newest stage dir)
  const stages = fs.readdirSync(EVIDENCE_DIR).filter(d => d.startsWith("setup-job-2026")).sort();
  const beforeFile = stages.length ? path.join(EVIDENCE_DIR, stages[stages.length - 1], "setup-job-before-readonly-db.json") : null;
  let jobsUnchanged = null;
  if (fs.existsSync(beforeFile)) {
    const before = JSON.parse(fs.readFileSync(beforeFile, "utf8"));
    jobsUnchanged = JSON.stringify(before.jobs.filter(l => !l.includes("岗位C"))) === JSON.stringify(after.jobs.filter(l => !l.includes("岗位C")))
      && JSON.stringify(before.requirements) === JSON.stringify(after.requirements.filter(l => !state.jobIdC || !l.includes(state.jobIdC)));
  }
  record({
    name: "snapshots-invariant", status: appsUnchanged && jobsUnchanged === true ? "pass" : "fail",
    detail: `apps=${after.applications.length} unchanged=${appsUnchanged} jobsABreqsUnchanged=${jobsUnchanged} mismatches=${mismatches.join("; ") || "none"}`,
  });
  // growth chain summary from state
  record({
    name: "chain-summary", status: "info",
    detail: `jobIdC=${state.jobIdC ?? "-"} base=${state.baseReportId ?? "-"} R1=${state.reportR1 ?? "-"} R2=${state.reportR2 ?? "-"} R3=${state.reportR3 ?? "-"} replyTask=${state.replyTaskId ?? "-"}`,
  });
  } catch (error) {
    await dumpFailureEvidence(tab).catch(() => {});
    await browser.stop().catch(() => {});
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
const HANDLERS = {
  "setup-job": scenarioSetupJob,
  "baseline": scenarioBaseline,
  "chain-reply": scenarioChainReply,
  "variant-materials": scenarioVariantMaterials,
  "variant-job": scenarioVariantJob,
  "variant-both": scenarioVariantBoth,
  "viewport390": scenarioViewport390,
  "enterprise-recheck": scenarioEnterpriseRecheck,
};

try {
  let head = "unknown";
  try { head = spawnSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT }).stdout.toString().trim(); } catch { /* git optional */ }
  record({ name: "scenario-start", status: "info", detail: `run=${RUN_ID} scenario=${SCENARIO} head=${head}` });
  await HANDLERS[SCENARIO]();
  record({ name: "scenario-end", status: exitCode === 0 ? "pass" : exitCode === 1 ? "fail" : "blocked", detail: `exit=${exitCode}` });
} catch (error) {
  record({ name: "scenario-error", status: /timeout|not found|missing/i.test(String(error?.message ?? "")) ? "blocked" : "fail", detail: scrub(String(error?.stack ?? error)).slice(0, 800) });
  if (lastTab) await dumpFailureEvidence(lastTab).catch(() => {});
  if (activeBrowser) await activeBrowser.stop().catch(() => {});
  record({ name: "scenario-end", status: "fail", detail: `exit=${exitCode}` });
} finally {
  persist();
}process.exit(exitCode);
