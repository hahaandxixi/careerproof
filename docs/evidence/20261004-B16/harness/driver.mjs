// B-16 复现驱动：用本机已安装的 Chrome（无新组件）+ Node 22 内置 WebSocket 直连 CDP。
// 复刻 ApplicationBoard.tsx:96 的交付模式在真实 Chromium 中的下载结果；全部合成数据。
import { launch } from "./cdp.mjs";

const BASE = "http://127.0.0.1:8931";
const DL_DIR = process.argv[2] ?? "D:\\jbcode\\tmp\\b16-repro\\dl";
const results = [];
const cdp = await launch({ chromePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", downloadDir: DL_DIR });

async function clickAndCollect(name, expression, { expected = 1, settleMs = 2000, timeoutMs = 60000, preCaptureMs = 0 } = {}) {
  // preCaptureMs：场景 D 在页面卸载前先取走 REPRO_RESULTS（源哈希随文档销毁）。
  let preState = null;
  const files = await cdp.withDownloads(expected, timeoutMs, async () => {
    await cdp.evaluate(expression);
    if (preCaptureMs) {
      await cdp.sleep(preCaptureMs);
      preState = JSON.parse(await cdp.evaluate("JSON.stringify(window.REPRO_RESULTS ?? {})"));
    }
  });
  await cdp.sleep(settleMs);
  const pageState = preState ?? JSON.parse(await cdp.evaluate("JSON.stringify(window.REPRO_RESULTS ?? {})"));
  results.push({ scenario: name, downloads: files, pageState });
  console.log(`\n=== ${name} ===`);
  console.log(JSON.stringify({ downloads: files, pageState }, null, 2));
}

await cdp.open(`${BASE}/`);
// 场景 A：小文件（贴近真实简历量级）
await clickAndCollect("A-64KB", `document.getElementById("a").click()`);
// 场景 B：大文件 256MB
await clickAndCollect("B-256MB", `document.getElementById("b").click()`, { settleMs: 3000 });
// 场景 C：双击连下两个
await clickAndCollect("C-double", `document.getElementById("c").click()`, { expected: 2, settleMs: 3000 });
// 场景 D：点击后 300ms 页面卸载（撤销定时器不触发）
await clickAndCollect("D-unload-300ms", `document.getElementById("d").click()`, { settleMs: 3000, preCaptureMs: 250 });
// 场景 E：撤销后 fetch 同一 URL（机制验证）；D 已导航走，先回到复现页。
await cdp.open(`${BASE}/`);
await clickAndCollect("E-revoke-sanity", `document.getElementById("e").click()`, { expected: 1, settleMs: 2500 });

await cdp.close();
const { createHash } = await import("node:crypto");
const { readdirSync, readFileSync } = await import("node:fs");
const { join } = await import("node:path");
console.log("\n=== 落盘文件与哈希比对 ===");
for (const entry of results) {
  for (const file of entry.downloads) {
    const bytes = readFileSync(join(DL_DIR, file.suggested));
    const hash = createHash("sha256").update(bytes).digest("hex");
    const generated = (entry.pageState.generated ?? []).find(g => file.suggested.includes(g.name));
    console.log(JSON.stringify({
      scenario: entry.scenario, file: file.name, sizeOnDisk: bytes.length,
      expectedSize: generated?.size, expectedSha256: generated?.hash, actualSha256: hash,
      match: generated ? hash === generated.hash && bytes.length === generated.size : "no-source-hash",
    }));
  }
}
console.log("\nALL_DONE");
