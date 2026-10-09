// E2E-02 enterprise browser runner (task card 20261004-E2E-enterprise-browser).
// Local test browser driven over raw CDP: independent profile per instance,
// dynamic debug port (--remote-debugging-port=0), every wait bounded by a
// timeout, faults injected via the Fetch domain (request delay / failure).
// Zero npm dependencies: Node >= 22 built-in WebSocket only.
// Secrets (synthetic passwords / tokens / cookie values) are never logged,
// screenshotted, or written to evidence.
//
// Usage: node scripts/e2e/enterprise-browser-runner.mjs --run closure-20261005 --scenario <name>
// Arguments are validated by runner-input.mjs (Codex guardrails — keep them).
// New-build retest evidence lives in docs/evidence/20261005-E2E-enterprise-retest/.
// Scenarios: skeleton | reply-failure | notification-filter | late-response | download-withdraw | withdraw-verify | viewport390

import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { parseRunnerArgs, parseCredentialDocument, withdrawnNotificationStatus,
  prepareEvidenceRecord, withdrawnOpenCardsStatus } from "./runner-input.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const FRONTEND = "http://127.0.0.1:3001";
const API_PATH_PREFIX = "/backend/api/v1";

let selection;
try { selection = parseRunnerArgs(process.argv.slice(2)); }
catch { console.error("Invalid --run/--scenario arguments; no files were written."); process.exit(2); }
const { runId: RUN_ID, scenario: SCENARIO } = selection;
const RUNTIME_DIR = path.join(ROOT, "backend", ".tmp", "e2e-browser", RUN_ID);
const EVIDENCE_DIR = path.join(ROOT, "docs", "evidence", selection.evidenceSubdir ?? "20261005-E2E-enterprise-retest");

fs.mkdirSync(RUNTIME_DIR, { recursive: true });
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

// ---------------------------------------------------------------------------
// Evidence plumbing
// ---------------------------------------------------------------------------
const RUN_STAMP = new Date().toISOString().replace(/[:.]/g, "-");
const STAGE_DIR = path.join(EVIDENCE_DIR, `${SCENARIO}-${RUN_STAMP}`);
fs.mkdirSync(STAGE_DIR, { recursive: true });
const results = { runId: RUN_ID, scenario: SCENARIO, startedAt: new Date().toISOString(), steps: [], artifacts: [] };
let stepCounter = 0;

// Exact secret strings (synthetic passwords) that must never reach console,
// results.json or any evidence file, even inside unexpected exception text.
const SCRUB = [];
function scrub(text) {
  let value = String(text);
  for (const secret of SCRUB) if (secret) value = value.split(secret).join("<redacted>");
  return value;
}

function record(step) {
  stepCounter += 1;
  const { entry, line } = prepareEvidenceRecord(step, stepCounter, SCRUB, new Date().toISOString());
  results.steps.push(entry);
  console.log(line);
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

// ---------------------------------------------------------------------------
// Chrome instance + CDP connection
// ---------------------------------------------------------------------------
class CdpError extends Error {}

class ChromeInstance {
  constructor(label, { width = 1440, height = 900 } = {}) {
    this.label = label;
    this.profileDir = path.join(RUNTIME_DIR, `profile-${label}`);
    this.downloadDir = path.join(RUNTIME_DIR, `downloads-${label}`);
    fs.mkdirSync(this.profileDir, { recursive: true });
    fs.mkdirSync(this.downloadDir, { recursive: true });
    this.width = width;
    this.height = height;
    this.child = null;
    this.ws = null;
    this.port = null;
    this.nextId = 1;
    this.pending = new Map();
    this.eventHandlers = [];
    this.closed = false;
    // Browser.downloadWillBegin/Progress are BROWSER-level events with no
    // sessionId; collect them here so every tab sees them.
    this.downloadEvents = [];
    this.eventHandlers.push(msg => {
      if (msg.method === "Browser.downloadWillBegin") {
        this.downloadEvents.push({ at: new Date().toISOString(), state: "begin", guid: msg.params.guid, filename: msg.params.suggestedFilename });
      } else if (msg.method === "Browser.downloadProgress") {
        this.downloadEvents.push({ at: new Date().toISOString(), state: msg.params.state, guid: msg.params.guid, filePath: msg.params.filePath ?? null });
      }
    });
  }

  async launch() {
    // A leftover DevToolsActivePort from a previous (killed) run would make
    // us latch onto a dead browser's port; always wait for a fresh one.
    const portFile = path.join(this.profileDir, "DevToolsActivePort");
    if (fs.existsSync(portFile)) fs.rmSync(portFile);
    this.child = spawn(CHROME, [
      "--headless=new",
      "--remote-debugging-port=0",
      `--user-data-dir=${this.profileDir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
      "--disable-sync",
      "--disable-gpu",
      "--disable-search-engine-choice-screen",
      "--no-default-browser-check",
      "--remote-allow-origins=*",
      `--window-size=${this.width},${this.height}`,
      "about:blank",
    ], { stdio: "ignore" });
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      if (fs.existsSync(portFile)) {
        const lines = fs.readFileSync(portFile, "utf8").split("\n").map(s => s.trim()).filter(Boolean);
        if (lines.length >= 1) { this.port = Number(lines[0]); break; }
      }
      await sleep(200);
    }
    if (!this.port) throw new CdpError(`chrome DevToolsActivePort did not appear within 20s (${this.label})`);
    await this.connect(`ws://127.0.0.1:${this.port}${lines_path(portFile)}`);
    await this.send("Browser.setDownloadBehavior", {
      behavior: "allow", downloadPath: this.downloadDir, eventsEnabled: true,
    });
    record({ name: "chrome-launched", status: "info", detail: `${this.label} dynamic port ${this.port} profile=${path.basename(this.profileDir)}` });
    return this;
  }

  async connect(url) {
    const deadline = Date.now() + 10000;
    while (true) {
      try { await this.tryConnect(url); break; }
      catch (error) {
        if (Date.now() > deadline) throw error;
        await sleep(250);
      }
    }
  }

  tryConnect(url) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.addEventListener("open", () => resolve());
      ws.addEventListener("error", () => reject(new CdpError(`websocket connect failed: ${url}`)));
      ws.addEventListener("message", event => {
        let msg;
        try { msg = JSON.parse(String(event.data)); } catch { return; }
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
      });
      ws.addEventListener("close", () => {
        if (!this.closed) for (const entry of this.pending.values()) entry.reject(new CdpError("cdp connection closed"));
      });
    });
  }

  send(method, params = {}, sessionId = undefined) {
    if (!this.ws || this.ws.readyState !== 1) throw new CdpError(`cdp not connected: ${method}`);
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new CdpError(`cdp timeout after 15000ms: ${method}`));
      }, 15000);
      this.pending.set(id, { resolve: v => { clearTimeout(timer); resolve(v); }, reject: e => { clearTimeout(timer); reject(e); }, method });
      this.ws.send(JSON.stringify(payload));
    });
  }

  // Attach to a page target with a flat session.
  async openTab(initialUrl = "about:blank") {
    const { targetId } = await this.send("Target.createTarget", { url: initialUrl });
    const { sessionId } = await this.send("Target.attachToTarget", { targetId, flatten: true });
    return new Tab(this, sessionId, targetId, this.downloadDir);
  }

  onEvent(handler) { this.eventHandlers.push(handler); }

  // Force-kill fallback: only when the child has NOT already exited AND the
  // PID's command line still contains this instance's own --user-data-dir.
  // A reused PID would carry a different command line and is left alone.
  pidStillOurs() {
    return new Promise(resolve => {
      let settled = false;
      const done = value => { if (!settled) { settled = true; resolve(value); } };
      const probe = spawn("powershell", ["-NoProfile", "-Command",
        `(Get-CimInstance Win32_Process -Filter 'ProcessId=${this.child.pid}').CommandLine`],
        { stdio: ["ignore", "pipe", "ignore"] });
      let out = "";
      probe.stdout.on("data", chunk => { out += String(chunk); });
      probe.on("exit", () => done(out.includes(`--user-data-dir=${this.profileDir}`)));
      probe.on("error", () => done(false));
      setTimeout(() => done(false), 8000).unref();
    });
  }

  async stop() {
    this.closed = true;
    try { await this.send("Browser.close"); } catch { /* graceful close failed; verify before any force kill */ }
    if (this.child && this.child.exitCode === null) {
      await Promise.race([new Promise(resolve => this.child.on("exit", resolve)), sleep(3000)]);
    }
    if (this.child && this.child.exitCode === null && this.child.pid && (await this.pidStillOurs())) {
      await new Promise(resolve => {
        const killer = spawn("taskkill", ["/PID", String(this.child.pid), "/T", "/F"], { stdio: "ignore" });
        killer.on("exit", resolve);
        killer.on("error", resolve);
      });
      record({ name: "chrome-force-killed", status: "warn", detail: `${this.label}: pid ${this.child.pid} verified via own --user-data-dir before kill` });
    } else if (this.child && this.child.exitCode === null) {
      record({ name: "chrome-kill-skipped", status: "warn", detail: `${this.label}: pid not verified as ours; left untouched` });
    }
    record({ name: "chrome-stopped", status: "info", detail: `${this.label} exitCode=${this.child?.exitCode ?? "n/a"}` });
  }
}

// DevToolsActivePort line 2 is the browser ws path; read it safely.
function lines_path(portFile) {
  const lines = fs.readFileSync(portFile, "utf8").split("\n").map(s => s.trim()).filter(Boolean);
  return lines[1] ?? "/devtools/browser";
}

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

// ---------------------------------------------------------------------------
// Tab helpers: bounded waits, real input events, screenshots, network log
// ---------------------------------------------------------------------------
class Tab {
  constructor(browser, sessionId, targetId, downloadDir) {
    this.browser = browser;
    this.sessionId = sessionId;
    this.targetId = targetId;
    this.downloadDir = downloadDir;
    this.networkLog = [];
    browser.onEvent(msg => {
      if (msg.sessionId !== this.sessionId) return;
      if (msg.method === "Network.requestWillBeSent") {
        this.networkLog.push({
          at: new Date().toISOString(), phase: "request",
          url: msg.params.request.url.replace(API_PATH_PREFIX, ""),
          method: msg.params.request.method, type: msg.params.type,
        });
      } else if (msg.method === "Network.responseReceived") {
        this.networkLog.push({
          at: new Date().toISOString(), phase: "response",
          url: msg.params.response.url.replace(API_PATH_PREFIX, ""),
          status: msg.params.response.status,
        });
      }
    });
  }

  // Download events live on the browser instance (browser-level CDP events).
  get downloadEvents() { return this.browser.downloadEvents; }

  send(method, params) { return this.browser.send(method, params, this.sessionId); }

  async enable() {
    await this.send("Page.enable");
    await this.send("Network.enable");
    await this.send("Runtime.enable");
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
        if (msg.sessionId === this.sessionId && msg.method === method) {
          cleanup();
          resolve(msg.params);
        }
      };
      const timer = setTimeout(() => { cleanup(); reject(new CdpError(`event timeout ${timeoutMs}ms: ${method}`)); }, timeoutMs);
      const cleanup = () => { clearTimeout(timer); this.browser.eventHandlers = this.browser.eventHandlers.filter(h => h !== handler); };
      this.browser.onEvent(handler);
    });
  }

  async evalJs(expression, { timeoutMs = 10000, awaitPromise = false } = {}) {
    const result = await this.send("Runtime.evaluate", {
      expression, returnByValue: true, awaitPromise, userGesture: true,
      timeout: timeoutMs,
    });
    if (result.exceptionDetails) {
      const text = result.exceptionDetails.exception?.description ?? result.exceptionDetails.text;
      throw new CdpError(`evaluate failed: ${String(text).slice(0, 300)}`);
    }
    return result.result?.value;
  }

  // Poll a page condition until truthy or timeout. Runs entirely page-side.
  async waitFor(pageExpression, { timeoutMs = 20000, pollMs = 150, label = "condition" } = {}) {
    const wrapped = `(async () => {
      const t0 = Date.now();
      while (Date.now() - t0 < ${timeoutMs}) {
        try { const v = Boolean(eval((${JSON.stringify(pageExpression)}))()); if (v) return { ok: true }; } catch {}
        await new Promise(r => setTimeout(r, ${pollMs}));
      }
      return { ok: false };
    })()`;
    const outcome = await this.evalJs(wrapped, { timeoutMs: timeoutMs + 5000, awaitPromise: true });
    if (!outcome?.ok) throw new CdpError(`waitFor timeout after ${timeoutMs}ms: ${label}`);
    return true;
  }

  // Install a page-side finder. Returns candidate elements with rects; the
  // model locates by visible text/aria — never through React internals.
  static FINDER = `(() => {
    window.__e2eFind = (opts) => {
      const { tag, text, exact, attr, attrValue, index } = opts;
      const wanted = (text ?? "").trim();
      const nodes = Array.from(document.querySelectorAll(tag ?? "button,a,th,td,h1,h2,h3,h4,p,li,label,span,select,option,input,textarea,summary,blockquote,[role=button],[role=status],[role=alert]"));
      const matches = [];
      for (const el of nodes) {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") continue;
      const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(" ").trim();
      const full = (el.textContent ?? "").trim();
      // Password fields: read nothing out of them (value attribute included).
      const secret = el.tagName === "INPUT" && el.type === "password";
      const hay = secret ? [] : [own, full, el.getAttribute("aria-label") ?? "", el.getAttribute("placeholder") ?? "", el.getAttribute("value") ?? ""];
        // Empty wanted text matches any element of the selector (hay may be
        // empty for password fields, so this cannot live inside the loop).
        let hit = !wanted;
        for (const candidate of hay) {
          if (exact ? candidate === wanted : candidate.includes(wanted)) { hit = true; break; }
        }
        if (attr && el.getAttribute(attr) !== (attrValue ?? true)) hit = false;
        if (!hit) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;
        matches.push({
          tag: el.tagName.toLowerCase(), text: secret ? "(password field)" : full.slice(0, 120),
          x: Math.round(rect.x + rect.width / 2), y: Math.round(rect.y + rect.height / 2),
          disabled: el.disabled === true || el.getAttribute("aria-disabled") === "true",
          readOnly: el.readOnly === true, top: Math.round(rect.top), h: Math.round(rect.height),
        });
        if (matches.length > 40) break;
      }
      return matches;
    };
    window.__e2eScrollTo = (x, y) => window.scrollTo({ top: y, behavior: "instant" });
    return true;
  })()`;

  async installFinder() {
    await this.evalJs(Tab.FINDER);
  }

  async find(opts) {
    return this.evalJs(`window.__e2eFind(${JSON.stringify(opts)})`);
  }

  async findUnique(opts, label) {
    const matches = await this.find(opts);
    if (matches.length !== 1) {
      throw new CdpError(`findUnique(${label ?? opts.text ?? ""}): ${matches.length} matches: ${JSON.stringify(matches.slice(0, 3))}`);
    }
    return matches[0];
  }

  // el.top from find() is viewport-relative; center the element in the
  // viewport (absolute document coordinates) and return fresh match data so
  // clicks never land on the viewport edge (elementFromPoint null).
  async recentreAndFind(el) {
    const scrollY = await this.evalJs("Math.round(window.scrollY)");
    const absoluteTop = scrollY + el.top;
    await this.evalJs(`window.__e2eScrollTo(0, ${Math.max(0, absoluteTop - Math.floor(this.browser.height / 2))})`);
    await sleep(180);
    const queries = el.text ? [{ tag: el.tag, text: el.text, exact: true }, { tag: el.tag, text: el.text }] : [{ tag: el.tag }];
    for (const query of queries) {
      const matches = await this.find(query);
      if (!matches.length) continue;
      let best = matches[0], bestDelta = Math.abs(best.x - el.x) + Math.abs(best.h - el.h);
      for (const match of matches) {
        const delta = Math.abs(match.x - el.x) + Math.abs(match.h - el.h);
        if (delta < bestDelta) { best = match; bestDelta = delta; }
      }
      return best;
    }
    return el;
  }

  // Real mouse click at element center via Input.dispatchMouseEvent.
  async click(optsOrEl, { label } = {}) {
    const el = optsOrEl.x !== undefined ? optsOrEl : await this.findUnique(optsOrEl, label);
    const target = await this.recentreAndFind(el);
    for (const type of ["mousePressed", "mouseReleased"]) {
      await this.send("Input.dispatchMouseEvent", {
        type, x: target.x, y: target.y, button: "left", clickCount: 1, buttons: type === "mousePressed" ? 1 : 0,
      });
    }
    await sleep(150);
    return target;
  }

  // Click, select-all, then IME-level text insertion (real input events fire;
  // React onChange observes them — no direct state writes).
  async fillText(opts, text, { label, expectValue } = {}) {
    const el = await this.click(opts, { label });
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
    await this.send("Input.insertText", { text });
    await sleep(120);
    if (expectValue !== undefined) {
      const got = await this.evalJs(`(document.activeElement?.value ?? "").trim()`);
      // Never echo field contents (the password field uses this path):
      // report label + match result + lengths only.
      if (got !== expectValue) throw new CdpError(`fillText mismatch: label=${label ?? "(unlabelled)"} match=false expectedLength=${expectValue.length} gotLength=${got.length}`);
    }
    return el;
  }

  async pressKey(key, { code, windowsVirtualKeyCode, modifiers = 0 } = {}) {
    await this.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key, code, windowsVirtualKeyCode, modifiers });
    await this.send("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode, modifiers });
    await sleep(120);
  }

  // Native select via keyboard on the focused control (real user path).
  async selectFocusedOption(optionText) {
    const info = await this.evalJs(`(() => { const s = document.activeElement && document.activeElement.tagName === 'SELECT' ? document.activeElement : null; if (!s) return null; return { idx: s.selectedIndex, texts: Array.from(s.options).map(o => o.text.trim()) }; })()`);
    if (!info) throw new CdpError(`selectFocusedOption: no focused select for ${optionText}`);
    const targetIdx = info.texts.indexOf(optionText);
    if (targetIdx < 0) throw new CdpError(`selectFocusedOption: option ${optionText} missing`);
    let steps = targetIdx - info.idx;
    while (steps !== 0) {
      const down = steps > 0;
      await this.pressKey(down ? "ArrowDown" : "ArrowUp", { code: down ? "ArrowDown" : "ArrowUp", windowsVirtualKeyCode: down ? 40 : 38 });
      steps += down ? -1 : 1;
    }
    await this.pressKey("Enter", { code: "Enter", windowsVirtualKeyCode: 13 });
    await sleep(150);
  }

  async selectOption(selectOpts, optionText, { label } = {}) {
    await this.click(selectOpts, { label });
    await this.selectFocusedOption(optionText);
  }

  // Focus + operate the (unique) select that contains the given option text.
  async selectOptionIn(matchingOptionText, optionText) {
    await this.clickStored(`(() => {
      const s = Array.from(document.querySelectorAll('select')).find(x => Array.from(x.options).some(o => o.text.trim() === ${JSON.stringify(matchingOptionText)}));
      if (!s) return false;
      s.scrollIntoView({ block: 'center' });
      window.__e2eClickEl = s;
      return true;
    })()`, `select with option ${matchingOptionText}`);
    await this.selectFocusedOption(optionText);
  }

  // Click a button that FINDER cannot disambiguate (e.g. several identical
  // buttons, one per notification). The locator expression must scroll the
  // element into view, stash it on window.__e2eClickEl and return true when
  // found; a second eval then reads fresh coordinates for a real mouse click.
  async clickStored(locatorExpression, label) {
    const found = await this.evalJs(locatorExpression);
    if (!found) throw new CdpError(`clickStored: target not found (${label})`);
    await sleep(250);
    const point = await this.evalJs(`(() => {
      const el = window.__e2eClickEl;
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const x = Math.round(r.x + r.width / 2), y = Math.round(r.y + r.height / 2);
      const hit = document.elementFromPoint(x, y);
      return { x, y, w: Math.round(r.width), h: Math.round(r.height), hit: hit ? hit.tagName + ':' + String(hit.className).slice(0, 60) : null, hitIsEl: hit === el || el.contains(hit), connected: el.isConnected };
    })()`);
    if (!point || point.x <= 0 || point.y <= 0) throw new CdpError(`clickStored: no rect for ${label}: ${JSON.stringify(point)}`);
    if (!point.hitIsEl) record({ name: "clickstored-overlay", status: "warn", detail: `${label}: elementFromPoint=${point.hit} connected=${point.connected}` });
    for (const type of ["mousePressed", "mouseReleased"]) {
      await this.send("Input.dispatchMouseEvent", {
        type, x: point.x, y: point.y, button: "left", clickCount: 1, buttons: type === "mousePressed" ? 1 : 0,
      });
    }
    await sleep(150);
    return point;
  }

  async screenshot(filePath, fullPage = true) {
    const params = { format: "png" };
    if (fullPage) {
      const metrics = await this.send("Page.getLayoutMetrics");
      const content = metrics.cssContentSize ?? metrics.contentSize;
      if (content && content.height > 0) {
        params.clip = { x: 0, y: 0, width: Math.min(content.width, 4000), height: Math.min(content.height, 12000), scale: 1 };
      }
    }
    const { data } = await this.send("Page.captureScreenshot", params);
    fs.writeFileSync(filePath, Buffer.from(data, "base64"));
    return filePath;
  }

  async bodyText() {
    return this.evalJs(`document.body.innerText`);
  }

  async apiRequests() { return this.networkLog.filter(e => e.url.startsWith("/api/") || e.url.includes("/api/v1")); }
}

// Fetch-domain fault injector bound to one tab.
class Injector {
  constructor(tab) { this.tab = tab; this.paused = new Map(); this.log = []; this.active = false; }
  async enable(patterns) {
    // Field init must precede Fetch.enable: paused events can arrive the
    // moment the domain turns on.
    this.held = [];
    this.dropped = [];
    this.holdPredicate = null;
    this.dropPredicate = null;
    this.tab.browser.onEvent(msg => {
      if (msg.sessionId !== this.tab.sessionId || msg.method !== "Fetch.requestPaused") return;
      this.log.push({ at: new Date().toISOString(), url: msg.params.request.url.replace(API_PATH_PREFIX, ""), method: msg.params.request.method, stage: msg.params.responseStatusCode != null ? "response" : "request", status: msg.params.responseStatusCode });
      if (!this.paused.has(msg.params.requestId)) this.paused.set(msg.params.requestId, msg.params);
      if (this.holdPredicate && this.holdPredicate(msg.params)) {
        this.held.push(msg.params);
        this.holdPredicate = null;
        this.holdWaiter?.();
        return; // hold: do not continue
      }
      if (this.dropPredicate && this.dropPredicate(msg.params)) {
        this.tab.send("Fetch.failRequest", { requestId: msg.params.requestId, errorReason: this.dropReason ?? "Failed" }).catch(() => {});
        this.dropped.push(msg.params);
        this.dropPredicate = null;
        return;
      }
      // Everything else passes through untouched.
      this.tab.send("Fetch.continueRequest", { requestId: msg.params.requestId }).catch(() => {});
    });
    await this.tab.send("Fetch.enable", { patterns, handleAuthRequests: false });
    this.active = true;
  }
  holdOnce(predicate) { this.holdPredicate = predicate; this.held = []; return new Promise(resolve => { this.holdWaiter = resolve; }); }
  dropOnce(predicate, reason = "Failed") { this.dropPredicate = predicate; this.dropReason = reason; this.dropped = []; }
  async releaseHeld() {
    const outcomes = [];
    for (const params of this.held) {
      const shortUrl = params.request.url.replace(API_PATH_PREFIX, "");
      try {
        await this.tab.send("Fetch.continueRequest", { requestId: params.requestId });
        outcomes.push({ url: shortUrl, result: "continued" });
      } catch (error) {
        // A navigation that destroyed the issuing page also aborts a paused
        // request; the dead interception itself proves the response died with
        // the old page and can never reach the new one.
        outcomes.push({ url: shortUrl, result: "already-cancelled", error: scrub(error?.message ?? String(error)).slice(0, 140) });
      }
      this.log.push({ at: new Date().toISOString(), url: shortUrl, method: params.request.method, stage: "released" });
    }
    this.held = [];
    return outcomes;
  }
}

// ---------------------------------------------------------------------------
// Credentials (synthetic, from backend/.tmp/e2e/<run>.json — never printed)
// ---------------------------------------------------------------------------
function loadCredentials() {
  const file = path.join(ROOT, "backend", ".tmp", "e2e", `${RUN_ID}.json`);
  if (!file.startsWith(path.join(ROOT, "backend", ".tmp"))) throw new CdpError(`credential path escaped isolated root`);
  const raw = parseCredentialDocument(fs.readFileSync(file, "utf8"));
  if (raw.runId !== RUN_ID) throw new CdpError(`credential file runId mismatch`);
  for (const account of Object.values(raw.accounts ?? {})) {
    if (typeof account?.password === "string" && account.password) SCRUB.push(account.password);
  }
  return raw;
}

// ---------------------------------------------------------------------------
// Shared flows
// ---------------------------------------------------------------------------
async function login(tab, account) {
  await tab.goto(`${FRONTEND}/login`);
  await tab.installFinder();
  await tab.waitFor(`() => document.querySelector('input[type=email]') && document.querySelector('input[type=password]')`, { label: "login form" });
  await saveShot(tab, "login-page-empty"); // shot before typing: no credentials anywhere
  await tab.fillText({ tag: "input[type=email]" }, account.email, { label: "email", expectValue: account.email });
  await tab.fillText({ tag: "input[type=password]" }, account.password, { label: "password", expectValue: account.password });
  await tab.click({ tag: "button[type=submit]" }, { label: "login submit" });
  await tab.waitFor(`() => !location.pathname.startsWith("/login")`, { timeoutMs: 20000, label: "redirect after login" });
  await sleep(600);
  record({ name: "login-ok", status: "pass", detail: `landed on ${await tab.evalJs("location.pathname")}` });
  return tab;
}

async function openBoard(tab, jobId) {
  await tab.goto(`${FRONTEND}/jobs/${jobId}/applications`);
  await tab.installFinder();
  await tab.waitFor(`() => document.querySelectorAll('th[id^="application-"]').length > 0`, { timeoutMs: 30000, label: `board table job ${jobId.slice(0, 8)}` });
  await sleep(300);
}

async function openApplication(tab, applicationId) {
  await tab.click({ tag: `th#application-${applicationId} button` }, { label: `open application ${applicationId.slice(0, 8)}` });
  await tab.waitFor(`() => Array.from(document.querySelectorAll("h2")).some(h => (h.textContent || "").includes("投递时固定报告"))`, { timeoutMs: 20000, label: `report open ${applicationId.slice(0, 8)}` });
  await sleep(400); // radar chart and report items render after the header
}

async function refreshBoard(tab) {
  await tab.click({ tag: "button", text: "刷新授权投递" }, { label: "refresh board" });
  await tab.waitFor(`() => document.querySelectorAll('th[id^="application-"]').length > 0 && !Array.from(document.querySelectorAll("h2")).some(h => (h.textContent || "").includes("投递时固定报告"))`, { timeoutMs: 30000, label: "board refreshed, old report collapsed" });
  await sleep(300);
}

function replyPosts(tab, applicationId) {
  return tab.networkLog.filter(e => e.phase === "request" && e.method === "POST" && e.url.includes(`/applications/${applicationId}/reply`));
}

async function fillReplyAndSend(tab, text) {
  const before = await tab.find({ tag: "textarea" });
  if (before.length !== 1 || before[0].readOnly) throw new CdpError(`fillReplyAndSend: expected one editable textarea, found ${before.length}, readOnly=${before[0]?.readOnly}`);
  await tab.fillText({ tag: "textarea" }, text, { label: "reply body", expectValue: text });
  // The board has other checkboxes (verification section); target the reply
  // confirm via its unique label text — clicking a wrapping label toggles it.
  await tab.click({ tag: "label", text: "我已核对正文" }, { label: "manual confirm checkbox" });
  await tab.waitFor(`() => { const el = Array.from(document.querySelectorAll('input[type=checkbox]')).find(i => (i.closest('label')?.textContent || '').includes('我已核对正文')); return el ? el.checked === true : false; }`, { label: "confirm checkbox checked" });
  await saveShot(tab, "reply-filled"); // synthetic named text only, never credentials
  await tab.click({ tag: "button", text: "确认发送站内回复" }, { label: "send reply" });
}

// Post-fix ACCEPTANCE (fix card 20261005-E2E-reply-draft): after a failed
// send the surviving draft must be a real editable textarea — edit works,
// clearing to empty keeps the textarea, retyping works — while the send
// entry and the old report stay absent until authorization is re-verified.
async function verifyAcceptanceDraft(tab, originalText, variant) {
  await tab.waitFor(`() => document.querySelector('p[role=alert]') !== null`, { timeoutMs: 20000, label: `${variant}: error alert` });
  await tab.waitFor(`() => document.querySelectorAll('textarea').length === 1 && document.querySelector('textarea[aria-label="未确认发送的回复草稿"]') !== null`, { timeoutMs: 10000, label: `${variant}: single failure draft` });
  const meta = (await tab.find({ tag: "textarea" }))[0] ?? {};
  const preserved = (await tab.evalJs(`document.querySelector('textarea').value`)) === originalText;

  // 1. Edit: select-all + real IME insert must CHANGE the value.
  const editText = `【已编辑】${originalText.slice(0, 40)}`;
  await tab.fillText({ tag: "textarea" }, editText, { label: `${variant}: edit draft`, expectValue: editText });
  const editedOk = (await tab.evalJs(`document.querySelector('textarea').value`)) === editText;

  // 2. Clear to empty via select-all + Backspace: the textarea must survive.
  await tab.click({ tag: "textarea" }, { label: `${variant}: focus draft to clear` });
  await tab.send("Input.dispatchKeyEvent", { type: "rawKeyDown", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
  await tab.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers: 2, windowsVirtualKeyCode: 65, code: "KeyA", key: "a" });
  await tab.pressKey("Backspace", { code: "Backspace", key: "Backspace", windowsVirtualKeyCode: 8 });
  await sleep(200);
  const afterClear = await tab.evalJs(`(() => { const t = document.querySelector('textarea[aria-label="未确认发送的回复草稿"]'); return t === null ? null : t.value; })()`);
  const stillExists = afterClear !== null;
  const clearedOk = afterClear === "";

  // 3. Retype the full body.
  await tab.fillText({ tag: "textarea" }, originalText, { label: `${variant}: retype draft`, expectValue: originalText });
  const retypedOk = (await tab.evalJs(`document.querySelector('textarea').value`)) === originalText;

  // 4. No send entry, no old report while delivery is unverified.
  const sendButtonGone = (await tab.find({ tag: "button", text: "确认发送站内回复" })).length === 0;
  const checkboxGone = (await tab.find({ tag: "label", text: "我已核对正文" })).length === 0;
  const oldReportGone = !(await tab.evalJs(`Array.from(document.querySelectorAll('h2')).some(h => (h.textContent || '').includes('投递时固定报告'))`));

  const findings = { variant, preserved, readOnly: meta.readOnly === true, editedOk, stillExists, clearedOk, retypedOk, sendButtonGone, checkboxGone, oldReportGone };
  const ok = preserved && !findings.readOnly && editedOk && stillExists && clearedOk && retypedOk && sendButtonGone && checkboxGone && oldReportGone;
  saveJson(`${variant}-draft-acceptance`, { ...findings, originalText });
  record({ name: `${variant}-draft-acceptance`, status: ok ? "pass" : "fail", detail: `preserved=${preserved} readOnly=${findings.readOnly} edit=${editedOk} clearKeptTextarea=${stillExists} clearedEmpty=${clearedOk} retype=${retypedOk} sendGone=${sendButtonGone} checkboxGone=${checkboxGone} oldReportGone=${oldReportGone}` });
  await saveShot(tab, `${variant}-failure-draft`);
  return findings;
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------
async function scenarioSkeleton(creds) {
  const browser = new ChromeInstance("enterprise");
  try {
    await browser.launch();
    const tab = await browser.openTab();
    await tab.enable();
    await login(tab, creds.accounts.enterprise);
    await openBoard(tab, creds.enterprise.jobIdA);
    await saveShot(tab, "board-jobA");
    await openApplication(tab, creds.applications.A.id);
    await saveShot(tab, "report-A-open");
    const bodyText = await tab.bodyText();
    const hasReport = bodyText.includes("投递时固定报告");
    saveJson("skeleton-dom", { url: await tab.evalJs("location.href"), hasReportHeader: hasReport, bodyText });
    saveJson("skeleton-api-log", tab.networkLog);
    record({ name: "skeleton-report-open", status: hasReport ? "pass" : "fail", detail: `report header rendered=${hasReport}; network events=${tab.networkLog.length}` });

    // Read-only download verification (NO withdrawal this round): the page
    // download must land on disk with the authorized material's SHA256.
    const beforeDl = tab.downloadEvents.filter(e => e.state === "completed").length;
    await clickAndExpectPost(tab, { tag: "button", text: "下载本次授权简历" }, "/resume-download", "download A resume");
    const eventDl = await waitForDownload(tab, beforeDl);
    const fileDl = resolveDownloadPath(tab, eventDl);
    const hashDl = sha256File(fileDl);
    const refHash = creds.materials.student.contentHash;
    record({ name: "skeleton-download-A", status: hashDl === refHash ? "pass" : "fail", detail: `file=${path.basename(fileDl)} bytes=${fs.statSync(fileDl).size} sha256=${hashDl} matchesAuthorizedFile=${hashDl === refHash}` });
    await saveShot(tab, "download-A-done");
  } finally {
    await browser.stop();
  }
}

// Task card item 6, post-fix ACCEPTANCE on the new build: both fault
// variants (request failure / response loss) with real injection, exactly
// one POST each and no auto-resend; editable draft (edit → clear → retype);
// no send entry / old report while unverified; after refresh the server
// truth matches (request-fail undelivered, response-loss delivered and not
// re-sendable). Desktop covers application A, 390px covers application B —
// each receives exactly ONE delivered reply (recorded for the student side);
// A2 is left untouched for the late-response race. NO withdrawal this round.
async function runReplyFailureViewport(creds, label, narrow, jobId, app, delivered) {
  const browser = new ChromeInstance(`enterprise-${label}`, narrow ? { width: 390, height: 844 } : {});
  const texts = {
    requestFail: `E2E复测${label}请求失败变体${RUN_ID}：具名正文，服务器不应收到此条。`,
    responseLoss: `E2E复测${label}响应丢失变体${RUN_ID}：具名正文，服务器应已收到此条。`,
  };
  try {
    await browser.launch();
    const tab = await browser.openTab();
    await tab.enable();
    if (narrow) {
      await tab.send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
      const vw = await tab.evalJs(`({ w: window.innerWidth })`).catch(() => ({ w: null }));
      record({ name: `${label}-viewport`, status: "info", detail: `viewport=${vw.w ?? "?"} (device metrics after first load)` });
    }
    await login(tab, creds.accounts.enterprise);
    await openBoard(tab, jobId);
    const injector = new Injector(tab);
    await injector.enable([
      { urlPattern: `*${API_PATH_PREFIX}/applications/${app.id}/reply*`, requestStage: "Request" },
      { urlPattern: `*${API_PATH_PREFIX}/applications/${app.id}/reply*`, requestStage: "Response" },
    ]);

    // (a) request failure: the POST never reaches the server.
    await openApplication(tab, app.id);
    injector.dropOnce(p => p.responseStatusCode == null, "ConnectionRefused");
    await fillReplyAndSend(tab, texts.requestFail);
    await verifyAcceptanceDraft(tab, texts.requestFail, `${label}-request-fail`);
    const postsAfterRequestFail = replyPosts(tab, app.id).length;
    record({ name: `${label}-request-fail-post-count`, status: postsAfterRequestFail === 1 ? "pass" : "fail", detail: `reply POSTs=${postsAfterRequestFail} (expect 1, no auto-retry)` });
    await refreshBoard(tab);
    await openApplication(tab, app.id);
    const bodyAfterRequestFail = await tab.bodyText();
    const serverRepliedRequestFail = bodyAfterRequestFail.includes("已发送回复：");
    const formBack = (await tab.find({ tag: "textarea" })).filter(t => !t.readOnly).length === 1;
    saveJson(`${label}-request-fail-refresh-dom`, {
      serverReplied: serverRepliedRequestFail,
      editableReplyFormBack: formBack,
      statusCell: await tab.evalJs(`document.querySelector('th#application-${app.id}')?.innerText ?? null`),
    });
    record({ name: `${label}-request-fail-server-state`, status: !serverRepliedRequestFail && formBack ? "pass" : "fail", detail: `serverReplied=${serverRepliedRequestFail} replyFormBack=${formBack} (undelivered must stay sendable after re-verify)` });
    await saveShot(tab, `${label}-request-fail-after-refresh`);

    // (b) response loss: the POST reaches the server, only the response dies.
    injector.dropOnce(p => p.responseStatusCode != null, "ConnectionReset");
    await fillReplyAndSend(tab, texts.responseLoss);
    await verifyAcceptanceDraft(tab, texts.responseLoss, `${label}-response-loss`);
    const postsTotal = replyPosts(tab, app.id).length;
    await sleep(2000);
    const postsAfterWait = replyPosts(tab, app.id).length;
    record({ name: `${label}-response-loss-post-count`, status: postsTotal === 2 && postsAfterWait === 2 ? "pass" : "fail", detail: `reply POSTs=${postsTotal} after 2s wait=${postsAfterWait} (expect 2 total, no auto-retry while delivery unknown)` });
    await refreshBoard(tab);
    await openApplication(tab, app.id);
    const bodyAfterResponseLoss = await tab.bodyText();
    const deliveredNow = bodyAfterResponseLoss.includes(texts.responseLoss);
    const editableForms = (await tab.find({ tag: "textarea" })).filter(t => !t.readOnly).length;
    const sendButtonPresent = (await tab.find({ tag: "button", text: "确认发送站内回复" })).length > 0;
    saveJson(`${label}-response-loss-refresh-dom`, { serverDelivered: deliveredNow, editableReplyTextareas: editableForms, sendButtonPresent, bodyText: bodyAfterResponseLoss });
    record({ name: `${label}-response-loss-server-state`, status: deliveredNow && editableForms === 0 && !sendButtonPresent ? "pass" : "fail", detail: `serverDelivered=${deliveredNow} editableReplyForms=${editableForms} sendButton=${sendButtonPresent} (delivered reply must not be re-sendable)` });
    await saveShot(tab, `${label}-response-loss-after-refresh`);
    if (deliveredNow) delivered.push({ viewport: label, applicationId: app.id, variant: "response-loss", replyText: texts.responseLoss, serverConfirmedAt: new Date().toISOString() });
  } finally {
    await browser.stop();
  }
}

async function scenarioReplyFailure(creds) {
  const delivered = [];
  await runReplyFailureViewport(creds, "desktop", false, creds.enterprise.jobIdA, creds.applications.A, delivered);
  await runReplyFailureViewport(creds, "390", true, creds.enterprise.jobIdB, creds.applications.B, delivered);
  saveJson("delivered-replies-for-student", delivered);
  record({ name: "delivered-replies", status: delivered.length === 2 ? "pass" : "fail", detail: `${delivered.length} replies delivered (desktop→A, 390→B); bodies + timestamps in delivered-replies-for-student.json` });
}

// Task card item 5: filter the target candidate out (a zero-result keyword
// hides every candidate — the synthetic candidates share names and verdict
// sets, and a zero-result filter still proves the notice + single locate,
// per Codex review), then arrive via a REAL notification anchor while the
// authorized list response is deliberately delayed.
async function scenarioNotificationFilter(creds) {
  const browser = new ChromeInstance("enterprise");
  const jobA = creds.enterprise.jobIdA;
  // A2 is the anchor target: A/B each carry one delivered reply from
  // reply-failure, so A2 stays the clean candidate for locate-once checks.
  const target = creds.applications.A2;
  const ZERO_KEYWORD = `E2E零结果筛选词${RUN_ID}`;
  try {
    await browser.launch();
    const tab = await browser.openTab();
    await tab.enable();
    await login(tab, creds.accounts.enterprise);
    await openBoard(tab, jobA);
    const targetVisible = await tab.evalJs(`document.querySelector('th#application-${target.id}') !== null`);
    if (!targetVisible) throw new CdpError("target candidate A2 not listed on jobA board");
    record({ name: "filter-plan", status: "info", detail: `hide target=${target.id.slice(0, 8)} via zero-result keyword (shared names make per-candidate filters impossible)` });
    await saveShot(tab, "board-candidates");

    // Locate (by probing real clicks) which notification card points at the
    // target. Cards are clicked for real; wrong landings just navigate away.
    let targetCard = -1;
    for (let i = 0; i < 8; i++) {
      await tab.goto(`${FRONTEND}/notifications`);
      await tab.installFinder();
      await tab.waitFor(`() => Array.from(document.querySelectorAll('li.panel')).some(li => li.textContent.includes('核对授权并打开投递'))`, { timeoutMs: 30000, label: "notification list" });
      const cardCount = await tab.evalJs(`Array.from(document.querySelectorAll('li.panel')).filter(li => li.textContent.includes('核对授权并打开投递')).length`);
      if (i >= cardCount) break;
      await tab.clickStored(`(() => {
        const cards = Array.from(document.querySelectorAll('li.panel')).filter(li => li.textContent.includes('核对授权并打开投递'));
        const card = cards[${i}];
        if (!card) return false;
        const button = Array.from(card.querySelectorAll('button')).find(b => b.textContent.includes('核对授权并打开投递'));
        if (!button) return false;
        button.scrollIntoView({ block: 'center' });
        window.__e2eClickEl = button;
        return true;
      })()`, `notification card ${i}`);
      const landed = await tab.waitFor(`() => location.hash.startsWith('#application-')`, { timeoutMs: 15000, label: `card ${i} landing` }).then(() => true, () => false);
      if (!landed) continue;
      const hash = await tab.evalJs("location.hash");
      if (hash === `#application-${target.id}`) { targetCard = i; break; }
    }
    if (targetCard < 0) {
      record({ name: "fixture-dependency", status: "blocked", detail: `no accessible notification card navigates to application ${target.id.slice(0, 8)} (probed 8 cards)` });
      throw new CdpError("no notification anchor for target application (see fixture-dependency step)");
    }
    record({ name: "notification-card-found", status: "pass", detail: `card #${targetCard} navigates to target via real 核对授权并打开投递 click` });

    // Now the real run: delay the jobA list, navigate through the notification,
    // apply the zero-result keyword while the list is in flight, then release.
    const injector = new Injector(tab);
    await injector.enable([{ urlPattern: `*${API_PATH_PREFIX}/jobs/${jobA}/applications*`, requestStage: "Request" }]);
    const held = injector.holdOnce(p => p.responseStatusCode == null && p.request.method === "GET");

    await tab.goto(`${FRONTEND}/notifications`);
    await tab.installFinder();
    await tab.waitFor(`() => Array.from(document.querySelectorAll('li.panel')).some(li => li.textContent.includes('核对授权并打开投递'))`, { timeoutMs: 30000, label: "notification list (final)" });
    await tab.clickStored(`(() => {
      const cards = Array.from(document.querySelectorAll('li.panel')).filter(li => li.textContent.includes('核对授权并打开投递'));
      const card = cards[${targetCard}];
      if (!card) return false;
      const button = Array.from(card.querySelectorAll('button')).find(b => b.textContent.includes('核对授权并打开投递'));
      if (!button) return false;
      button.scrollIntoView({ block: 'center' });
      window.__e2eClickEl = button;
      return true;
    })()`, `target notification (final)`);
    await tab.waitFor(`() => location.pathname.includes('/applications') && location.hash === '#application-${target.id}'`, { timeoutMs: 20000, label: "anchor navigation landed" });
    record({ name: "anchor-navigation", status: "pass", detail: `landed with target hash while list response held` });
    await Promise.race([held, sleep(15000).then(() => { throw new CdpError("held list request never observed"); })]);

    // While the list is in flight, exclude EVERY candidate (incl. the target).
    await tab.fillText({ tag: "input[type=search]" }, ZERO_KEYWORD, { label: "zero-result keyword filter", expectValue: ZERO_KEYWORD });
    await injector.releaseHeld();

    await tab.waitFor(`() => Array.from(document.querySelectorAll('[role=status]')).some(el => (el.textContent || '').includes('通知指向的投递在当前筛选结果之外'))`, { timeoutMs: 20000, label: "filtered-out notice" });
    const targetHidden = await tab.evalJs(`document.querySelector('th#application-${target.id}') === null`);
    const zeroResultShown = await tab.evalJs(`Array.from(document.querySelectorAll('[role=status]')).some(el => (el.textContent || '').includes('没有匹配候选人'))`);
    record({ name: "filtered-out-notice", status: targetHidden && zeroResultShown ? "pass" : "fail", detail: `notice=true targetHidden=${targetHidden} zeroResultList=${zeroResultShown}` });
    await saveShot(tab, "filtered-out-notice");

    // Scroll telemetry: prove later that refresh does not re-scroll (B-15).
    await tab.evalJs(`(() => { window.__e2eScrolls = []; window.addEventListener('scroll', () => window.__e2eScrolls.push(Math.round(window.scrollY)), { passive: true }); return true; })()`);

    await tab.click({ tag: "button", text: "清除筛选并定位" }, { label: "clear filters and locate" });
    await tab.waitFor(`() => document.querySelector('th#application-${target.id}') !== null && !Array.from(document.querySelectorAll('[role=status]')).some(el => (el.textContent || '').includes('通知指向的投递在当前筛选结果之外'))`, { timeoutMs: 20000, label: "target revealed, notice cleared" });
    const scrollAfterReveal = await tab.evalJs(`({ y: Math.round(window.scrollY), h: Math.round(document.documentElement.scrollHeight), targetTop: Math.round(document.querySelector('th#application-${target.id}').getBoundingClientRect().top) })`);
    record({ name: "clear-filter-locate-once", status: "pass", detail: `targetVisible=true scrollY=${scrollAfterReveal.y} targetTop=${scrollAfterReveal.targetTop} pageH=${scrollAfterReveal.h}` });
    await saveShot(tab, "after-clear-filter");

    // Scroll away, then refresh the board: the consumed anchor must not hijack
    // the viewport again, and the target must survive the refresh.
    await tab.evalJs(`window.scrollTo(0, 0)`);
    const scrollBeforeRefresh = await tab.evalJs(`Math.round(window.scrollY)`);
    await refreshBoard(tab);
    const scrollAfterRefresh = await tab.evalJs(`Math.round(window.scrollY)`);
    const targetAfterRefresh = await tab.evalJs(`document.querySelector('th#application-${target.id}') !== null`);
    const noticeGone = !(await tab.evalJs(`Array.from(document.querySelectorAll('[role=status]')).some(el => (el.textContent || '').includes('通知指向的投递在当前筛选结果之外'))`));
    const scrollEvents = await tab.evalJs(`window.__e2eScrolls ?? []`);
    record({ name: "refresh-no-hijack", status: noticeGone && targetAfterRefresh && scrollAfterRefresh < 60 ? "pass" : "fail", detail: `scrollBefore=${scrollBeforeRefresh} scrollAfter=${scrollAfterRefresh} noticeGone=${noticeGone} targetRetained=${targetAfterRefresh} scrollEvents=${JSON.stringify(scrollEvents)}` });
    saveJson("notification-filter-telemetry", { scrollAfterReveal, scrollBeforeRefresh, scrollAfterRefresh, scrollEvents });
    await saveShot(tab, "after-refresh-no-hijack");
  } finally {
    await browser.stop();
  }
}

// Task card item 4 (retest): the PRIMARY variant is the same-page race —
// hold application A's open-report request at the RESPONSE stage, trigger a
// REAL same-document hash navigation to A2's anchor (address-bar equivalent;
// no component internals called, hashchange recorded page-side), let the
// refreshed board load A2's authorized report, then release A and prove the
// response is truly DELIVERED (continueRequest succeeds, responseReceived
// observed) while A2's report is not overwritten and no old draft appears.
// Secondary variant: cross-page navigation to job B (the requesting page is
// destroyed; cancellation recorded as-is). A carries a delivered reply from
// reply-failure (blockquote = overwrite detector); A2 stays unreplied.
async function scenarioLateResponse(creds) {
  const browser = new ChromeInstance("enterprise");
  const jobA = creds.enterprise.jobIdA;
  const jobB = creds.enterprise.jobIdB;
  const appA = creds.applications.A;
  const appA2 = creds.applications.A2;
  const appB = creds.applications.B;
  try {
    await browser.launch();
    const tab = await browser.openTab();
    await tab.enable();
    await login(tab, creds.accounts.enterprise);

    // ---- Variant 1: same-page hash anchor race (primary) ----
    await openBoard(tab, jobA);
    await tab.evalJs(`(() => { window.__e2eHash = []; window.addEventListener('hashchange', () => window.__e2eHash.push({ at: new Date().toISOString(), hash: location.hash })); return true; })()`);
    const injector = new Injector(tab);
    await injector.enable([{ urlPattern: `*${API_PATH_PREFIX}/applications/${appA.id}/view*`, requestStage: "Response" }]);
    const held = injector.holdOnce(p => p.responseStatusCode != null && p.request.method === "POST");

    // Open A: POST /view reaches the server, the response is paused.
    await tab.click({ tag: `th#application-${appA.id} button` }, { label: "open A (response held)" });
    await Promise.race([held, sleep(15000).then(() => { throw new CdpError("held A view response never observed"); })]);
    const busyDuringHold = await tab.evalJs(`Array.from(document.querySelectorAll('[role=status]')).some(el => (el.textContent || '').includes('正在核对授权投递'))`);
    record({ name: "a-view-held", status: "info", detail: `A /view response paused; busy indicator=${busyDuringHold}` });

    // Real address-bar anchor navigation (same document → hashchange only).
    await tab.send("Page.navigate", { url: `${FRONTEND}/jobs/${jobA}/applications#application-${appA2.id}` });
    await tab.waitFor(`() => (window.__e2eHash ?? []).some(e => e.hash === '#application-${appA2.id}')`, { timeoutMs: 20000, label: "hashchange to A2 recorded" });
    await tab.waitFor(`() => { const b = document.querySelector('th#application-${appA2.id} button'); return b && !b.disabled; }`, { timeoutMs: 30000, label: "board refreshed, A2 button enabled" });
    record({ name: "hash-navigation-accepted", status: "pass", detail: `hashchange consumed; stale session cleared via page refresh path; A2 clickable` });

    // Open A2's authorized report on the refreshed page.
    await tab.click({ tag: `th#application-${appA2.id} button` }, { label: "open A2 report" });
    await tab.waitFor(`() => Array.from(document.querySelectorAll('h2')).some(h => (h.textContent || '').includes('投递时固定报告'))`, { timeoutMs: 20000, label: "A2 report open" });
    const blockquoteBefore = await tab.evalJs(`document.body.innerText.includes('已发送回复：')`);
    await saveShot(tab, "a2-report-open-while-a-held");

    // Release A's paused response: it must be DELIVERED, not cancelled.
    const responsesBefore = tab.networkLog.filter(e => e.phase === "response" && e.url.includes(`/applications/${appA.id}/view`)).length;
    const releaseOutcomes = await injector.releaseHeld();
    const delivered = releaseOutcomes[0]?.result === "continued";
    let responseObserved = false;
    for (let i = 0; i < 50 && !responseObserved; i++) {
      await sleep(200);
      responseObserved = tab.networkLog.filter(e => e.phase === "response" && e.url.includes(`/applications/${appA.id}/view`)).length > responsesBefore;
    }
    await sleep(1500);
    const reportStillOpen = await tab.evalJs(`Array.from(document.querySelectorAll('h2')).some(h => (h.textContent || '').includes('投递时固定报告'))`);
    const blockquoteAfter = await tab.evalJs(`document.body.innerText.includes('已发送回复：')`);
    const errorShown = await tab.evalJs(`document.querySelector('p[role=alert]') !== null`);
    // A2 is unreplied, so its open report legitimately shows the NORMAL reply
    // form textarea; only the unconfirmed-draft textarea counts as a leak.
    const draftShown = await tab.evalJs(`document.querySelector('textarea[aria-label="未确认发送的回复草稿"]') !== null`);
    const hashStillA2 = await tab.evalJs(`location.hash`) === `#application-${appA2.id}`;
    const bothColumns = await tab.evalJs(`document.querySelector('th#application-${appA.id}') !== null && document.querySelector('th#application-${appA2.id}') !== null`);
    const ok = delivered && responseObserved && reportStillOpen && !blockquoteAfter && !errorShown && !draftShown && hashStillA2 && bothColumns;
    record({ name: "same-page-late-a-race", status: ok ? "pass" : "fail", detail: `release=${releaseOutcomes[0]?.result ?? "none"} responseObserved=${responseObserved} a2ReportStillOpen=${reportStillOpen} aDataOverwroteA2=${blockquoteAfter} error=${errorShown} draft=${draftShown} hashStillA2=${hashStillA2} bothColumns=${bothColumns}` });
    saveJson("same-page-race-evidence", { hashEvents: await tab.evalJs(`window.__e2eHash ?? []`), releaseOutcomes, blockquoteBefore, injectorLog: injector.log });
    await saveShot(tab, "after-late-a-release-same-page");

    // ---- Variant 2: cross-page navigation (secondary, as-is recording) ----
    const held2 = injector.holdOnce(p => p.responseStatusCode != null && p.request.method === "POST");
    await tab.click({ tag: `th#application-${appA.id} button` }, { label: "open A again (response held)" });
    await Promise.race([held2, sleep(15000).then(() => { throw new CdpError("second held A view response never observed"); })]);
    await tab.goto(`${FRONTEND}/jobs/${jobB}`);
    await tab.installFinder();
    await tab.waitFor(`() => Array.from(document.querySelectorAll('a')).some(a => (a.textContent || '').includes('查看本岗位已授权投递与匹配对照'))`, { timeoutMs: 30000, label: "job B detail entry link" });
    await tab.click({ tag: "a", text: "查看本岗位已授权投递与匹配对照" }, { label: "navigate to job B board" });
    await tab.waitFor(`() => location.pathname.endsWith('/applications') && location.pathname.includes('${jobB}')`, { timeoutMs: 30000, label: "job B board route" });
    await tab.waitFor(`() => document.querySelector('th#application-${appB.id}') !== null`, { timeoutMs: 30000, label: "job B board loaded" });
    const outcomes2 = await injector.releaseHeld();
    await sleep(1200);
    const bIntact = await tab.evalJs(`document.querySelector('th#application-${appB.id}') !== null`);
    const aColumnOnB = await tab.evalJs(`document.querySelector('th#application-${appA.id}') !== null`);
    const error2 = await tab.evalJs(`document.querySelector('p[role=alert]') !== null`);
    record({ name: "cross-page-late-a", status: bIntact && !aColumnOnB && !error2 ? "pass" : "fail", detail: `release=${outcomes2[0]?.result ?? "none"} (page destroyed → cancellation is the expected browser behavior) bBoardIntact=${bIntact} aColumnOnB=${aColumnOnB} error=${error2}` });
    await saveShot(tab, "cross-page-after-release");
  } finally {
    await browser.stop();
  }
}

function sha256File(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

async function waitForDownload(tab, completedBefore, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const done = tab.downloadEvents.filter(e => e.state === "completed");
    if (done.length > completedBefore) return done[done.length - 1];
    await sleep(200);
  }
  const dirFiles = fs.existsSync(tab.downloadDir) ? fs.readdirSync(tab.downloadDir) : [];
  const alertText = await tab.evalJs(`document.querySelector('p[role=alert]')?.innerText ?? null`).catch(() => null);
  const lastPosts = tab.networkLog.filter(e => e.method === "POST").slice(-6);
  record({ name: "download-timeout-diagnostics", status: "warn", detail: `events=${JSON.stringify(tab.downloadEvents.slice(-6))} dirFiles=${JSON.stringify(dirFiles)} alert=${alertText}` });
  saveJson("download-timeout", { events: tab.downloadEvents, dirFiles, alertText, lastPosts });
  throw new CdpError(`download did not complete within ${timeoutMs}ms`);
}

function resolveDownloadPath(tab, event) {
  if (event.filePath && fs.existsSync(event.filePath)) return event.filePath;
  const byName = event.filename ? path.join(tab.downloadDir, event.filename) : null;
  if (byName && fs.existsSync(byName)) return byName;
  const files = fs.readdirSync(tab.downloadDir).map(name => {
    const full = path.join(tab.downloadDir, name);
    return { full, mtime: fs.statSync(full).mtimeMs };
  }).sort((a, b) => b.mtime - a.mtime);
  if (!files.length) throw new CdpError("no downloaded file found in download dir");
  return files[0].full;
}

// Click a button and require its POST to appear in the network log; on
// failure capture what actually sits at the button's center (overlay check).
async function clickAndExpectPost(tab, opts, urlPart, label) {
  const before = tab.networkLog.filter(e => e.method === "POST" && e.url.includes(urlPart)).length;
  const el = await tab.click(opts, { label });
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    if (tab.networkLog.filter(e => e.method === "POST" && e.url.includes(urlPart)).length > before) return el;
    await sleep(200);
  }
  const probe = await tab.evalJs(`(() => {
    const b = Array.from(document.querySelectorAll('button')).find(x => (x.textContent || '').includes(${JSON.stringify(opts.text ?? "")}));
    if (!b) return { found: false };
    const r = b.getBoundingClientRect();
    const cx = Math.round(r.x + r.width / 2), cy = Math.round(r.y + r.height / 2);
    const at = document.elementFromPoint(cx, cy);
    return { found: true, disabled: b.disabled, rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, center: { cx, cy }, topElement: at ? at.tagName + ":" + String(at.className).slice(0, 70) : null, topIsButton: at === b, scrollY: Math.round(window.scrollY) };
  })()`);
  record({ name: "click-no-post-diagnostics", status: "warn", detail: JSON.stringify(probe) });
  throw new CdpError(`click on ${label} did not trigger POST containing ${urlPart}`);
}

// Task card item 7: download A with hash proof, save A/B snapshot reference
// hashes, let the isolated student withdraw disposable A, then verify A is
// unreadable through every old enterprise entry while B stays valid and its
// download hash unchanged. Withdrawal is irreversible — run once per run id.
async function scenarioDownloadWithdraw(creds) {
  const enterprise = new ChromeInstance("enterprise");
  const student = new ChromeInstance("student");
  const jobA = creds.enterprise.jobIdA;
  const jobB = creds.enterprise.jobIdB;
  const appA = creds.applications.A;
  const appB = creds.applications.B;
  const resumeHashRef = creds.materials.student.contentHash;
  try {
    await enterprise.launch();
    const tab = await enterprise.openTab();
    await tab.enable();
    await login(tab, creds.accounts.enterprise);

    // 1. Download A from the page; hash must match the authorized material.
    await openBoard(tab, jobA);
    await openApplication(tab, appA.id);
    const beforeA = tab.downloadEvents.filter(e => e.state === "completed").length;
    await clickAndExpectPost(tab, { tag: "button", text: "下载本次授权简历" }, "/resume-download", "download A resume");
    const eventA = await waitForDownload(tab, beforeA);
    const fileA = resolveDownloadPath(tab, eventA);
    const hashA = sha256File(fileA);
    record({ name: "download-A", status: hashA === resumeHashRef ? "pass" : "fail", detail: `file=${path.basename(fileA)} bytes=${fs.statSync(fileA).size} sha256=${hashA} matchesAuthorizedFile=${hashA === resumeHashRef}` });
    await saveShot(tab, "download-A-done");

    // 2. Download B once before withdrawal (baseline for the after-check).
    await openBoard(tab, jobB);
    await openApplication(tab, appB.id);
    const beforeB = tab.downloadEvents.filter(e => e.state === "completed").length;
    await clickAndExpectPost(tab, { tag: "button", text: "下载本次授权简历" }, "/resume-download", "download B resume (baseline)");
    const eventB = await waitForDownload(tab, beforeB);
    const fileB = resolveDownloadPath(tab, eventB);
    const hashB1 = sha256File(fileB);
    record({ name: "download-B-baseline", status: "pass", detail: `file=${path.basename(fileB)} sha256=${hashB1}` });
    saveJson("snapshot-reference", {
      A: { applicationId: appA.id, snapshotSha256: appA.snapshotSha256 },
      B: { applicationId: appB.id, snapshotSha256: appB.snapshotSha256 },
      resumeMaterialSha256: resumeHashRef,
      downloadedA: { file: path.basename(fileA), sha256: hashA, matchesMaterial: hashA === resumeHashRef },
      downloadedB: { file: path.basename(fileB), sha256: hashB1 },
    });

    // 3. The isolated student withdraws disposable A through the real UI.
    await student.launch();
    const stab = await student.openTab();
    await stab.enable();
    await login(stab, creds.accounts.student);
    await stab.goto(`${FRONTEND}/applications`);
    await stab.installFinder();
    await stab.waitFor(`() => document.querySelector('article#application-${appA.id}') !== null`, { timeoutMs: 30000, label: "student application list" });
    await stab.clickStored(`(() => {
      const row = document.querySelector('article#application-${appA.id}');
      if (!row) return false;
      const button = Array.from(row.querySelectorAll('button')).find(b => b.textContent.includes('撤回投递授权'));
      if (!button) return false;
      button.scrollIntoView({ block: 'center' });
      window.__e2eClickEl = button;
      return true;
    })()`, "withdraw A (arm)");
    await stab.click({ tag: "button", text: "确认撤回授权" }, { label: "withdraw A (confirm)" });
    await stab.waitFor(`() => (document.querySelector('article#application-${appA.id}')?.innerText || '').includes('已撤回授权')`, { timeoutMs: 30000, label: "A withdrawn" });
    record({ name: "student-withdrew-A", status: "pass", detail: `application ${appA.id.slice(0, 8)} now shows 已撤回授权 in student list` });
    await saveShot(stab, "student-withdrew-A");

    // 4. Enterprise board: A must vanish, other candidates stay. (The tab may
    // currently sit on job B; navigate to the job A board explicitly.)
    await openBoard(tab, jobA);
    const aGone = await tab.evalJs(`document.querySelector('th#application-${appA.id}') === null`);
    const a2Kept = await tab.evalJs(`document.querySelector('th#application-${creds.applications.A2.id}') !== null`);
    record({ name: "board-A-unreadable", status: aGone && a2Kept ? "pass" : "fail", detail: `aColumnGone=${aGone} otherCandidateKept=${a2Kept}` });
    await saveShot(tab, "board-A-after-withdraw");

    // 5. Old notification entry for A must not deliver the report.
    await tab.goto(`${FRONTEND}/notifications`);
    await tab.installFinder();
    await tab.waitFor(`() => Array.from(document.querySelectorAll('li.panel')).some(li => li.textContent.includes('核对授权并打开投递'))`, { timeoutMs: 30000, label: "notification list" });
    let aNotice = null;
    const cardTotal = await tab.evalJs(`Array.from(document.querySelectorAll('li.panel')).filter(li => li.textContent.includes('核对授权并打开投递')).length`);
    for (let i = 0; i < Math.min(cardTotal, 8) && aNotice === null; i++) {
      const clicked = await tab.evalJs(`(() => {
        const cards = Array.from(document.querySelectorAll('li.panel')).filter(li => li.textContent.includes('核对授权并打开投递'));
        const card = cards[${i}];
        if (!card) return false;
        const button = Array.from(card.querySelectorAll('button')).find(b => b.textContent.includes('核对授权并打开投递'));
        if (!button) return false;
        button.scrollIntoView({ block: 'center' });
        window.__e2eClickEl = button;
        return true;
      })()`);
      if (!clicked) continue;
      const landed = await tab.waitFor(`() => location.hash.startsWith('#application-') || document.querySelector('p[role=alert]') !== null`, { timeoutMs: 15000, label: `card ${i} landing` }).then(() => true, () => false);
      if (!landed) continue;
      const hash = await tab.evalJs("location.hash");
      if (hash !== `#application-${appA.id}`) { await tab.goto(`${FRONTEND}/notifications`); await tab.installFinder(); continue; }
      aNotice = await tab.waitFor(`() => Array.from(document.querySelectorAll('[role=status]')).some(el => (el.textContent || '').includes('通知对应的投递已不可访问'))`, { timeoutMs: 15000, label: "withdrawn anchor notice" }).then(() => "unavailable-notice", () => null);
      if (aNotice === null) {
        // Still on the board with A's hash but no notice: capture what is shown.
        aNotice = await tab.evalJs(`Array.from(document.querySelectorAll('h2')).some(h => (h.textContent || '').includes('投递时固定报告'))`) ? "REPORT-STILL-READABLE" : "no-notice-no-report";
      }
    }
    record({ name: "old-notification-A", status: withdrawnNotificationStatus(aNotice), detail: `probed cards for A anchor; outcome=${aNotice}` });
    await saveShot(tab, "old-notification-A-outcome");

    // 6. B must still open and download with an identical hash.
    await openBoard(tab, jobB);
    await openApplication(tab, appB.id);
    const beforeB2 = tab.downloadEvents.filter(e => e.state === "completed").length;
    await clickAndExpectPost(tab, { tag: "button", text: "下载本次授权简历" }, "/resume-download", "download B resume (after withdrawal)");
    const eventB2 = await waitForDownload(tab, beforeB2);
    const fileB2 = resolveDownloadPath(tab, eventB2);
    const hashB2 = sha256File(fileB2);
    record({ name: "download-B-after-withdraw", status: hashB2 === hashB1 ? "pass" : "fail", detail: `file=${path.basename(fileB2)} sha256=${hashB2} unchanged=${hashB2 === hashB1}` });
    await saveShot(tab, "download-B-after-withdraw");
  } finally {
    await enterprise.stop();
    await student.stop();
  }
}

// Post-withdrawal read-only verification (run AFTER scenarioDownloadWithdraw):
// job A board must not list A but must keep the other candidate; the old
// anchor URL and old notifications must not deliver A's report.
async function scenarioWithdrawVerify(creds) {
  const enterprise = new ChromeInstance("enterprise");
  const jobA = creds.enterprise.jobIdA;
  const appA = creds.applications.A;
  const appA2 = creds.applications.A2;
  try {
    await enterprise.launch();
    const tab = await enterprise.openTab();
    await tab.enable();
    await login(tab, creds.accounts.enterprise);

    await openBoard(tab, jobA);
    const aGone = await tab.evalJs(`document.querySelector('th#application-${appA.id}') === null`);
    const a2Kept = await tab.evalJs(`document.querySelector('th#application-${appA2.id}') !== null`);
    const aReportAnywhere = await tab.evalJs(`Array.from(document.querySelectorAll('h2')).some(h => (h.textContent || '').includes('投递时固定报告'))`);
    record({ name: "board-A-unreadable", status: aGone && a2Kept && !aReportAnywhere ? "pass" : "fail", detail: `aColumnGone=${aGone} otherCandidateKept=${a2Kept} aReportRendered=${aReportAnywhere}` });
    await saveShot(tab, "board-A-after-withdraw");

    // Old anchor URL (the enterprise's saved entry) must not deliver A.
    await tab.goto(`${FRONTEND}/jobs/${jobA}/applications#application-${appA.id}`);
    await tab.installFinder();
    const noticeSeen = await tab.waitFor(`() => Array.from(document.querySelectorAll('[role=status]')).some(el => (el.textContent || '').includes('通知对应的投递已不可访问'))`, { timeoutMs: 20000, label: "withdrawn anchor unavailable notice" }).then(() => true, () => false);
    const a2AfterAnchor = await tab.evalJs(`document.querySelector('th#application-${appA2.id}') !== null`);
    const aReportAfterAnchor = await tab.evalJs(`Array.from(document.querySelectorAll('h2')).some(h => (h.textContent || '').includes('投递时固定报告'))`);
    record({ name: "old-anchor-A", status: noticeSeen && a2AfterAnchor && !aReportAfterAnchor ? "pass" : "fail", detail: `unavailableNotice=${noticeSeen} otherCandidateKept=${a2AfterAnchor} aReportRendered=${aReportAfterAnchor}` });
    await saveShot(tab, "old-anchor-A-outcome");

    // Notifications: withdrawn applications intentionally have NO open button
    // (correct product behavior — not a defect). Identify A's cards by
    // correlating card timestamps with the withdrawal moment recorded in the
    // download-withdraw evidence, and prove every card that IS accessible
    // navigates to a still-valid application (A2/B), never to A.
    await tab.goto(`${FRONTEND}/notifications`);
    await tab.installFinder();
    await tab.waitFor(`() => document.querySelectorAll('li.panel').length > 0`, { timeoutMs: 30000, label: "notification list" });
    const cards = await tab.evalJs(`(() => Array.from(document.querySelectorAll('li.panel')).map((li, i) => ({
      i,
      title: li.querySelector('h2')?.innerText ?? '',
      timeText: (li.innerText.match(/\\d{4}\\/\\d{1,2}\\/\\d{1,2}\\s+\\d{1,2}:\\d{2}:\\d{2}/) ?? [null])[0],
      inaccessible: li.innerText.includes('当前投递不可访问'),
      hasOpenButton: Array.from(li.querySelectorAll('button')).some(b => b.textContent.includes('核对授权并打开投递')),
      text: li.innerText.slice(0, 200),
    })))()`);
    saveJson("notifications-after-withdraw", cards);
    let withdrewAt = null, withdrewSource = null;
    for (const dir of fs.readdirSync(EVIDENCE_DIR).filter(name => name.startsWith("download-withdraw-")).sort()) {
      const file = path.join(EVIDENCE_DIR, dir, "results.json");
      if (!fs.existsSync(file)) continue;
      const steps = JSON.parse(fs.readFileSync(file, "utf8")).steps ?? [];
      const step = steps.find(s => s.name === "student-withdrew-A");
      if (step?.at) { withdrewAt = step.at; withdrewSource = dir; break; }
    }
    const parseCardTime = text => {
      const m = /(\d{4})\/(\d{1,2})\/(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})/.exec(text ?? "");
      return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]), Number(m[6])).getTime() : NaN;
    };
    const withdrewMs = withdrewAt ? Date.parse(withdrewAt) : NaN;
    const inaccessible = cards.filter(c => c.inaccessible);
    const withdrawalEventCard = inaccessible.find(c => Number.isFinite(parseCardTime(c.timeText)) && Number.isFinite(withdrewMs) && Math.abs(parseCardTime(c.timeText) - withdrewMs) <= 120000);
    const olderInaccessible = inaccessible.filter(c => c !== withdrawalEventCard && parseCardTime(c.timeText) < withdrewMs - 60000);
    const openAnchors = [];
    const openCount = cards.filter(c => c.hasOpenButton).length;
    for (let j = 0; j < openCount; j++) {
      const clicked = await tab.evalJs(`(() => {
        const items = Array.from(document.querySelectorAll('li.panel')).filter(li => Array.from(li.querySelectorAll('button')).some(b => b.textContent.includes('核对授权并打开投递')));
        const li = items[${j}] ?? null;
        if (!li) return false;
        const button = Array.from(li.querySelectorAll('button')).find(b => b.textContent.includes('核对授权并打开投递'));
        button.scrollIntoView({ block: 'center' });
        window.__e2eClickEl = button;
        return true;
      })()`);
      if (!clicked) continue;
      // Did the click actually fire the handler? Watch for the target/read
      // API calls; retry once if the first dispatch is swallowed.
      let landed = await tab.waitFor(`() => location.hash.startsWith('#application-') || document.querySelector('p[role=alert]') !== null`, { timeoutMs: 8000, label: `open card ${j} landing` }).then(() => true, () => false);
      if (!landed) {
        const callsBefore = tab.networkLog.filter(e => e.url.includes("/target") || e.url.includes("/read")).length;
        await tab.clickStored(`(() => {
          const items = Array.from(document.querySelectorAll('li.panel')).filter(li => Array.from(li.querySelectorAll('button')).some(b => b.textContent.includes('核对授权并打开投递')));
          const li = items[${j}] ?? null;
          if (!li) return false;
          const button = Array.from(li.querySelectorAll('button')).find(b => b.textContent.includes('核对授权并打开投递'));
          button.scrollIntoView({ block: 'center' });
          window.__e2eClickEl = button;
          return true;
        })()`, `open card ${j} retry`);
        await sleep(1000);
        const callsAfter = tab.networkLog.filter(e => e.url.includes("/target") || e.url.includes("/read")).length;
        landed = await tab.waitFor(`() => location.hash.startsWith('#application-') || document.querySelector('p[role=alert]') !== null`, { timeoutMs: 10000, label: `open card ${j} landing after retry` }).then(() => true, () => false);
        if (!landed) record({ name: `open-card-${j}-no-response`, status: "warn", detail: `handler api calls before=${callsBefore} after=${callsAfter} (0 means onClick never ran)` });
      }
      const state = await tab.evalJs(`(() => ({ path: location.pathname, hash: location.hash, alert: document.querySelector('p[role=alert]')?.innerText ?? null, status: Array.from(document.querySelectorAll('p[role=status]')).map(p => p.innerText.trim()).filter(Boolean).join('|') || null }))()`);
      openAnchors.push(state.hash.startsWith("#application-") ? state.hash : `no-landing:${JSON.stringify(state)}`.slice(0, 220));
      await tab.goto(`${FRONTEND}/notifications`);
      await tab.installFinder();
      await tab.waitFor(`() => Array.from(document.querySelectorAll('li.panel')).some(li => li.textContent.includes('核对授权并打开投递'))`, { timeoutMs: 30000, label: `notification list reload for card ${j + 1}` });
    }
    const aLeak = openAnchors.includes(`#application-${appA.id}`);
    const verdict = withdrawnOpenCardsStatus({ inaccessibleCount: inaccessible.length,
      withdrawalEventFound: Boolean(withdrawalEventCard), olderUnavailableCount: olderInaccessible.length,
      openCount, openAnchors, withdrawnId: appA.id });
    record({ name: "old-notification-A", status: verdict, detail: `inaccessibleCards=${inaccessible.length} withdrawalEventCardTime=${withdrawalEventCard?.timeText ?? "none"} (withdrawnAt ${withdrewAt ?? "?"} from ${withdrewSource ?? "no evidence"}) olderInaccessible=${olderInaccessible.length} openCardAnchors=${JSON.stringify(openAnchors)} aAnchorLeak=${aLeak}` });
    await saveShot(tab, "notifications-final-state");
  } finally {
    await enterprise.stop();
  }
}

// Task card item 8: the key chain at a 390px-wide viewport.
async function scenarioViewport390(creds) {
  const browser = new ChromeInstance("enterprise-390", { width: 390, height: 844 });
  const jobA = creds.enterprise.jobIdA;
  const appA2 = creds.applications.A2;
  try {
    await browser.launch();
    const tab = await browser.openTab();
    await tab.enable();
    // Headless Chrome clamps --window-size to a ~512px minimum; use standard
    // device metrics emulation for a true 390px viewport instead. Measure on
    // a real loaded page — about:blank still reports the 980px layout viewport.
    await tab.send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
    await login(tab, creds.accounts.enterprise);
    const viewport = await tab.evalJs(`({ w: window.innerWidth, h: window.innerHeight })`);
    record({ name: "viewport", status: viewport.w === 390 ? "pass" : "fail", detail: `innerWidth=${viewport.w} innerHeight=${viewport.h} (measured on loaded page)` });
    await openBoard(tab, jobA);
    await saveShot(tab, "board-390");
    await openApplication(tab, appA2.id);
    await saveShot(tab, "report-390");
    await tab.evalJs(`(() => {
      const heading = Array.from(document.querySelectorAll('h2')).find(h => (h.textContent || '').includes('投递时固定报告'));
      heading?.scrollIntoView({ block: 'center', behavior: 'instant' });
    })()`);
    const reportVisible = await tab.waitFor(`() => {
      const heading = Array.from(document.querySelectorAll('h2')).find(h => (h.textContent || '').includes('投递时固定报告'));
      if (!heading) return false;
      const rect = heading.getBoundingClientRect();
      const coveringHeader = document.querySelector('header')?.getBoundingClientRect().bottom ?? 0;
      return rect.width > 0 && rect.height > 0 && rect.top >= Math.max(0, coveringHeader) && rect.bottom <= innerHeight;
    }`, { timeoutMs: 10000, label: '390px report heading visible in viewport' }).then(() => true, () => false);
    await saveShot(tab, "report-390-visible-viewport", false);
    const overflow = await tab.evalJs(`({ pageW: document.documentElement.scrollWidth, winW: window.innerWidth })`);
    record({ name: "key-chain-390", status: reportVisible && overflow.pageW <= overflow.winW ? "pass" : "fail", detail: `login+board+report at 390px; reportVisible=${reportVisible}; pageWidth=${overflow.pageW} vs viewport=${overflow.winW}` });
  } finally {
    await browser.stop();
  }
}

const SCENARIOS = {
  skeleton: scenarioSkeleton,
  "reply-failure": scenarioReplyFailure,
  "notification-filter": scenarioNotificationFilter,
  "late-response": scenarioLateResponse,
  "download-withdraw": scenarioDownloadWithdraw,
  "withdraw-verify": scenarioWithdrawVerify,
  viewport390: scenarioViewport390,
};

async function main() {
  const creds = loadCredentials();
  const fn = SCENARIOS[SCENARIO];
  if (!fn) throw new CdpError(`unknown scenario (available: ${Object.keys(SCENARIOS).join(", ")})`);
  record({ name: "scenario-start", status: "info", detail: `scenario=${SCENARIO} runId=${RUN_ID}` });
  await fn(creds);
  // A clean script exit is NOT acceptance: any failed/blocked step must make
  // the run exit non-zero even though the script finished normally.
  const notPassed = results.steps.filter(s => s.status === "fail" || s.status === "blocked");
  if (notPassed.length) {
    record({ name: "scenario-complete", status: "fail", detail: `${notPassed.length} step(s) not passed: ${notPassed.map(s => `${s.n}:${s.name}`).join(", ").slice(0, 300)}` });
    process.exitCode = 1;
  } else {
    record({ name: "scenario-complete", status: "pass" });
  }
}

main().catch(error => {
  record({ name: "scenario-aborted", status: "fail", detail: (error?.stack ?? error?.message ?? String(error)).split("\n").slice(0, 3).join(" | ") });
  process.exitCode = 1;
});
