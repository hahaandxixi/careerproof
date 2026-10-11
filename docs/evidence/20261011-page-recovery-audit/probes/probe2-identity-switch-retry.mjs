// 探针2：同一浏览器两个标签页先后登录不同角色时，旧标签页的下一个请求会
// 401→refresh 成功→以"新身份 cookie"静默重试并拿到新身份数据，
// 全程无任何错误或事件通知 AuthProvider（页面顶部仍显示旧身份的 displayName）。
// request() 成功路径不携带身份信息、AuthProvider 只监听 refresh 失败后的
// careerproof:session-expired（client.ts:186-188 只在 401 且 refresh 失败后到达）。
// 复用 tests/api-client.test.mjs 的 mock fetch 手法，纯 Node 无网络。
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../../..");
const require = createRequire(import.meta.url);
const { transform } = require(path.join(ROOT, "jianli/node_modules/sucrase/dist/index.js"));

registerHooks({
  resolve(specifier, context, nextResolve) {
    if ((specifier.startsWith("./") || specifier.startsWith("../")) && !path.extname(specifier)) {
      for (const suffix of ["", ".ts", ".tsx", "/index.ts", "/index.tsx"]) {
        try { return nextResolve(new URL(specifier + suffix, context.parentURL).href, context); } catch {}
      }
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".ts") || url.endsWith(".tsx")) {
      const out = transform(readFileSync(fileURLToPath(url), "utf8"), {
        transforms: ["typescript", "jsx"], jsxRuntime: "automatic", production: false, filePath: url,
      });
      return { format: "module", source: out.code, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});

const { api } = await import(pathToFileURL(path.join(ROOT, "jianli/src/lib/api/client.ts")).href);

const envelope = (data, status = 200) => new Response(
  JSON.stringify({ code: status === 200 ? 0 : status, message: status === 200 ? "success" : "expired", data, requestId: "probe2" }),
  { status, headers: { "Content-Type": "application/json" } });

let sessionExpiredEvents = 0;
// request() 通过 window.dispatchEvent 通知过期；Node 无 window，用全局桩捕获真实调用次数。
globalThis.window = { dispatchEvent: event => { if (event.type === "careerproof:session-expired") sessionExpiredEvents++; return true; } };

const original = globalThis.fetch;
let phase = 0; // 0=旧身份 token 过期 1=refresh 后（新身份 cookie 生效）
let refreshCalls = 0, mineCalls = 0;
globalThis.fetch = async url => {
  if (String(url).endsWith("/auth/refresh")) { refreshCalls++; phase = 1; return envelope({}); }
  if (String(url).endsWith("/applications/mine")) {
    mineCalls++;
    // 第一次：学生 access token 已过期 → 401；refresh 后浏览器 cookie 已被
    // 另一标签页的企业登录轮换 → 重试以企业身份通过 → 返回企业账号的空投递列表。
    return phase === 0 ? envelope(null, 401) : envelope([]);
  }
  throw new Error("unexpected " + url);
};

try {
  const result = await api.myApplications();
  assert.deepEqual(result, [], "重试静默成功：旧'学生投递页'拿到的是企业账号的空列表");
  assert.equal(mineCalls, 2, "401 后确实以同一请求重试了一次");
  assert.equal(refreshCalls, 1, "refresh 单飞一次");
  assert.equal(sessionExpiredEvents, 0, "refresh 成功路径不派发 session-expired：AuthProvider 与页面身份完全不知情");
  console.log("PROBE2 PASS：角色切换后旧页面以新身份静默取数（学生页显示企业数据），无任何提示或事件。");
} finally {
  globalThis.fetch = original;
  delete globalThis.window;
}
