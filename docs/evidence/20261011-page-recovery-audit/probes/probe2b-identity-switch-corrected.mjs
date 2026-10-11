// 探针2b（更正版）：修正 probe2 的过度结论。Codex 复核指出真实后端
// backend/app/services/applications.py:161-165（_student：非学生角色必抛 403 code=4037）
// 与 :349-350（mine() 先过 _student）意味着"企业 cookie 调 /applications/mine 返回 200 空列表"
// 不成立。本探针重新按真实形态分两个序列证明：
//   序列A（同角色另一学生，离线 mock 模拟同角色另一学生的有效 cookie）：
//     401 → refresh 成功 → 重试 200 返回另一学生的投递列表 → 前端静默接受、无任何事件。
//     这是"显示他人数据"的可达路径；明确为离线 mock，不是真实双标签页/越权实测。
//   序列B（跨角色，对齐真实后端 403 形态）：
//     401 → refresh 成功 → 重试 403（envelope 与 AppError 序列化一致：
//     app/core/exceptions.py:18-28，code=4037"请使用学生账号"）→ 前端收到错误但仍
//     无 session-expired、AuthProvider 不感知、不引导重新登录。
// 核心缺陷结论不变：refresh 成功路径没有任何身份同步（client.ts:174-176），
// AuthProvider 只监听 refresh 失败后的失效事件（AuthProvider.tsx:55-59）。
// 纯 Node + mock fetch，无网络/服务/DB/浏览器。
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

const { api, ApiError } = await import(pathToFileURL(path.join(ROOT, "jianli/src/lib/api/client.ts")).href);

const okEnvelope = data => new Response(
  JSON.stringify({ code: 0, message: "success", data, requestId: "probe2b" }),
  { status: 200, headers: { "Content-Type": "application/json" } });
// 与 backend/app/core/exceptions.py error_body + AppError("请使用学生账号", code=4037, status_code=403) 对齐：
const forbiddenEnvelope = () => new Response(
  JSON.stringify({ code: 4037, message: "请使用学生账号", data: {}, requestId: "probe2b" }),
  { status: 403, headers: { "Content-Type": "application/json" } });

let sessionExpiredEvents = 0;
globalThis.window = { dispatchEvent: event => { if (event.type === "careerproof:session-expired") sessionExpiredEvents++; return true; } };

const original = globalThis.fetch;
try {
  // 序列A：同角色另一学生（离线 mock，非真实双标签页实测）。
  {
    let phase = 0, refreshCalls = 0, mineCalls = 0;
    globalThis.fetch = async url => {
      if (String(url).endsWith("/auth/refresh")) { refreshCalls++; phase = 1; return okEnvelope({}); }
      if (String(url).endsWith("/applications/mine")) {
        mineCalls++;
        // 第一次：旧学生 access token 过期 → 401；refresh 后浏览器 cookie 已被
        // 另一标签页的"另一个学生账号"登录轮换 → 重试 200 返回另一学生的列表。
        return phase === 0
          ? new Response(JSON.stringify({ code: 401, message: "expired", data: null, requestId: "probe2b" }), { status: 401, headers: { "Content-Type": "application/json" } })
          : okEnvelope([{ id: "app-of-STUDENT-B", jobTitle: "另一个学生的投递", status: "submitted" }]);
      }
      throw new Error("unexpected " + url);
    };
    const result = await api.myApplications();
    assert.equal(result[0].id, "app-of-STUDENT-B", "同角色另一学生：重试静默成功，旧页面渲染出另一账号的投递列表");
    assert.equal(mineCalls, 2, "401 后以同一请求静默重试一次");
    assert.equal(refreshCalls, 1, "refresh 单飞一次");
    assert.equal(sessionExpiredEvents, 0, "仍无 session-expired：AuthProvider 与页头旧身份完全不知情");
    console.log("序列A PASS（离线 mock）：同角色另一学生 cookie 下，旧页面静默显示他人投递，无任何提示或事件。");
  }

  // 序列B：跨角色（企业），对齐真实后端 403 形态 —— 更正 probe2 的"200 空列表"过度结论。
  {
    let phase = 0;
    globalThis.fetch = async url => {
      if (String(url).endsWith("/auth/refresh")) { phase = 1; return okEnvelope({}); }
      if (String(url).endsWith("/applications/mine")) {
        return phase === 0
          ? new Response(JSON.stringify({ code: 401, message: "expired", data: null, requestId: "probe2b" }), { status: 401, headers: { "Content-Type": "application/json" } })
          : forbiddenEnvelope();
      }
      throw new Error("unexpected " + url);
    };
    await assert.rejects(api.myApplications(), error => error instanceof ApiError && error.status === 403 && error.code === 4037,
      "跨角色：真实后端形态是 403（_student 门槛），不是 200 空列表");
    assert.equal(sessionExpiredEvents, 0, "403 路径同样不派发 session-expired：AuthProvider 不感知身份已换，页头仍显示学生名，错误文案'请使用学生账号'与页头身份自相矛盾且不引导重新登录");
    console.log("序列B PASS：跨角色为 403 错误提示（不串数据），但无身份同步、不引导重新登录。");
  }

  console.log("PROBE2B PASS：身份同步缺失成立；数据串号仅限同角色跨账号（离线 mock 证明），跨角色为 403。");
} finally {
  globalThis.fetch = original;
  delete globalThis.window;
}
