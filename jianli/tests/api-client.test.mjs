import { test } from "node:test";
import assert from "node:assert/strict";
import { api, ApiError, errorMessage, request } from "../src/lib/api/client.ts";

const envelope = (data, status = 200, message = "success") => new Response(JSON.stringify({ code: status === 200 ? 0 : status, message, data, requestId: "test-request" }), { status, headers: { "Content-Type": "application/json" } });

test("refresh server failure is not classified as an expired session", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async url => url.endsWith("/auth/refresh") ? envelope(null, 503, "服务暂不可用") : envelope(null, 401);
  try { await assert.rejects(api.getMe(), error => error instanceof ApiError && error.status === 503); }
  finally { globalThis.fetch = original; }
});

test("definitive refresh rejection remains an authentication error", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => envelope(null, 401, "请重新登录");
  try { await assert.rejects(api.getMe(), error => error instanceof ApiError && error.status === 401); }
  finally { globalThis.fetch = original; }
});

test("concurrent protected reads share one refresh and retry with cookies", async () => {
  const original = globalThis.fetch;
  let refreshed = false;
  let refreshCount = 0;
  globalThis.fetch = async (url, init) => {
    assert.equal(init.credentials, "include");
    if (url.endsWith("/auth/refresh")) { refreshCount++; await new Promise(resolve => setTimeout(resolve, 10)); refreshed = true; return envelope({}); }
    return refreshed ? envelope({ id: "current-user" }) : envelope(null, 401);
  };
  try {
    const users = await Promise.all([api.getMe(), api.getMe()]);
    assert.equal(refreshCount, 1);
    assert.deepEqual(users.map(user => user.id), ["current-user", "current-user"]);
  } finally { globalThis.fetch = original; }
});

test("network failures remain connection errors rather than 401", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
  try { await assert.rejects(api.getMe(), error => !(error instanceof ApiError) && error.message.includes("无法连接服务")); }
  finally { globalThis.fetch = original; }
});

test("failed refresh network call also stays a connection error", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async url => { if (url.endsWith("/auth/refresh")) throw new TypeError("offline"); return envelope(null, 401); };
  try { await assert.rejects(api.getMe(), error => !(error instanceof ApiError) && error.message.includes("确认会话")); }
  finally { globalThis.fetch = original; }
});

test("authenticated retry preserves the exact multipart upload and request key", async () => {
  const original = globalThis.fetch;
  const form = new FormData(); form.append("file", new File(["project"], "sample.txt")); form.append("requestId", "same-logical-upload");
  let posts = 0;
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/auth/refresh")) return envelope({});
    assert.equal(init.body, form); assert.equal(init.body.get("requestId"), "same-logical-upload");
    return ++posts === 1 ? envelope(null, 401) : envelope({ versionId: "version-1" });
  };
  try { assert.deepEqual(await request("/projects/project-1/versions", { method: "POST", body: form }), { versionId: "version-1" }); assert.equal(posts, 2); }
  finally { globalThis.fetch = original; }
});

test("validation details become an actionable field message", () => {
  const error = new ApiError(
    "请求参数校验失败",
    422,
    4220,
    "validation-request",
    [{ loc: ["body", "email"], msg: "invalid address", type: "value_error" }],
  );
  assert.match(errorMessage(error), /邮箱格式不正确/);
  assert.match(errorMessage(error), /validation-request/);
});

test("visual generation and review send JSON content types and keep consent separate", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    assert.equal(new Headers(init.headers).get("Content-Type"), "application/json");
    calls.push({ url, method: init.method, body: JSON.parse(init.body) });
    return envelope({ id: "observation" });
  };
  try {
    await api.observeImage("owned-version");
    await api.reviewVisual("observation", "pending", "仅核对描述");
    assert.deepEqual(calls.map(call => [call.method, call.body]), [
      ["POST", { externalImageConsent: true }],
      ["PATCH", { status: "pending", note: "仅核对描述" }],
    ]);
    assert.ok(calls[0].url.endsWith("/project-versions/owned-version/visual-review"));
    assert.ok(calls[1].url.endsWith("/visual-reviews/observation"));
  } finally { globalThis.fetch = original; }
});
