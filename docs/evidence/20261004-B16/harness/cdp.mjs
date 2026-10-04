// 最小 CDP 客户端（Node 内置 WebSocket），仅服务本机回环的合成复现页。
export async function launch({ chromePath, downloadDir }) {
  const { spawn } = await import("node:child_process");
  const { mkdtempSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const profile = mkdtempSync(join(tmpdir(), "b16-chrome-"));
  const child = spawn(chromePath, [
    "--headless=new", "--remote-debugging-port=9333", `--user-data-dir=${profile}`,
    "--no-first-run", "--no-default-browser-check", "--window-size=1280,900", "about:blank",
  ], { stdio: "ignore" });
  let wsUrl;
  for (let i = 0; i < 50 && !wsUrl; i++) {
    await sleep(200);
    try {
      const res = await fetch("http://127.0.0.1:9333/json/version");
      wsUrl = (await res.json()).webSocketDebuggerUrl;
    } catch {}
  }
  if (!wsUrl) { child.kill(); throw new Error("Chrome DevTools 端口未就绪"); }
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let seq = 0;
  const pending = new Map();
  const events = [];
  const eventWaiters = [];
  ws.onmessage = (message) => {
    const msg = JSON.parse(message.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method) {
      events.push(msg);
      for (let i = 0; i < eventWaiters.length; i++) {
        if (eventWaiters[i](msg)) { eventWaiters.splice(i, 1); break; }
      }
    }
  };
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  await send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloadDir, eventsEnabled: true });
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const api = {
    async open(url) {
      await send("Page.enable", {}, sessionId);
      await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false }, sessionId);
      const loaded = new Promise(resolve => eventWaiters.push(m => m.method === "Page.loadEventFired" && m.sessionId === sessionId && resolve()));
      await send("Page.navigate", { url }, sessionId);
      await loaded;
      await sleep(300);
    },
    async evaluate(expression) {
      const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, sessionId);
      if (exceptionDetails) throw new Error("页面异常: " + JSON.stringify(exceptionDetails));
      return result.value;
    },
    async withDownloads(expected, timeoutMs, action) {
      events.length = 0;
      const started = Date.now();
      const begun = [];
      const done = new Map();
      let scanned = 0;
      // 每个事件只处理一次：用扫描指针消费 events，绝不重复注册/重复扫描。
      const check = (m) => {
        if (m.method === "Browser.downloadWillBegin") begun.push({ guid: m.params.guid, suggested: m.params.suggestedFilename });
        if (m.method === "Browser.downloadProgress" && (m.params.state === "completed" || m.params.state === "canceled")) done.set(m.params.guid, m.params.state);
      };
      const actionPromise = action();
      while (Date.now() - started < timeoutMs) {
        while (scanned < events.length) check(events[scanned++]);
        if (begun.length >= expected && begun.every(b => done.get(b.guid))) break;
        await sleep(150);
      }
      while (scanned < events.length) check(events[scanned++]);
      if (begun.length < expected) throw new Error(`下载开始事件不足：${begun.length}/${expected}（${Math.round((Date.now()-started)/1000)}s）`);
      const missing = begun.filter(b => !done.get(b.guid));
      if (missing.length) throw new Error("下载未完成: " + JSON.stringify(missing));
      return begun.map(b => ({ guid: b.guid, suggested: b.suggested, state: done.get(b.guid) }));
    },
    async screenshot(path) {
      const { data } = await send("Page.captureScreenshot", { format: "png" }, sessionId);
      const { writeFileSync } = await import("node:fs");
      writeFileSync(path, Buffer.from(data, "base64"));
    },
    async viewport(width, height, mobile) {
      await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile }, sessionId);
    },
    async close() {
      await send("Target.closeTarget", { targetId });
      ws.close();
      child.kill();
    },
  };
  api.sleep = sleep;
  return api;
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
