import { test } from "node:test";
import assert from "node:assert/strict";
import { api, ApiError, errorMessage, request } from "../src/lib/api/client.ts";

const envelope = (data, status = 200, message = "success") => new Response(JSON.stringify({ code: status === 200 ? 0 : status, message, data, requestId: "test-request" }), { status, headers: { "Content-Type": "application/json" } });

test("authorized resume download preserves binary bytes and filename after session refresh", async()=>{
  const original=globalThis.fetch;let calls=0;
  globalThis.fetch=async(url,init)=>{
    assert.equal(init.credentials,"include");
    if(url.endsWith("/auth/refresh"))return envelope({});
    assert.equal(init.method,"POST");calls++;
    return calls===1?envelope(null,401):new Response(new Uint8Array([0,255,13,10]),{headers:{"Content-Disposition":"attachment; filename*=UTF-8''%E7%AE%80%E5%8E%86.pdf","Content-Type":"application/pdf"}});
  };
  try{const result=await api.downloadApplicationResume("synthetic");assert.equal(result.filename,"简历.pdf");assert.deepEqual([...new Uint8Array(await result.blob.arrayBuffer())],[0,255,13,10]);assert.equal(calls,2);}finally{globalThis.fetch=original;}
});

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

test("enterprise verification sends separate consent and reads only the application-scoped saved task", async () => {
  const original = globalThis.fetch;
  const calls = [], controller = new AbortController();
  globalThis.fetch = async (url, init) => {
    assert.equal(init.credentials, "include"); assert.equal(init.cache, "no-store");
    assert.equal(init.signal, controller.signal);
    calls.push({ url, method: init.method, body: init.body ? JSON.parse(init.body) : undefined });
    return envelope({ taskId: "verification-1", status: "pending" }, init.method === "POST" ? 202 : 200);
  };
  try {
    await api.createApplicationVerification("application-1", controller.signal);
    await api.applicationVerification("application-1", undefined, controller.signal);
    await api.applicationVerification("application-1", "verification-1", controller.signal);
    assert.deepEqual(calls.map(call => call.url), [
      "/backend/api/v1/applications/application-1/verification",
      "/backend/api/v1/applications/application-1/verification",
      "/backend/api/v1/applications/application-1/verification/verification-1",
    ]);
    assert.deepEqual(calls[0].body, { externalAiConsent: true });
    assert.ok(calls.slice(1).every(call => call.body === undefined && call.method !== "POST"));
  } finally { globalThis.fetch = original; }
});

test("growth task reads and version association do not grant model consent or replace an application", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, method: init.method, body: init.body ? JSON.parse(init.body) : undefined });
    return envelope({ id: "growth-1" });
  };
  try {
    await api.growthTask("growth-1");
    await api.growthMaterials("growth-1", { resumeVersionId: "resume-v1", projectVersionIds: ["project-v2"] });
    await api.analyzeGrowth("growth-1", false);
    assert.deepEqual(calls[1].body, { resumeVersionId: "resume-v1", projectVersionIds: ["project-v2"] });
    assert.deepEqual(calls[2].body, { externalAiConsent: false });
    assert.equal(calls[0].body, undefined);
    assert.ok(calls.every(call => call.url.includes("/growth-tasks/growth-1") && !call.url.includes("applications")));
  } finally { globalThis.fetch = original; }
});

test("successful application events refresh notification count; failed requests do not",async()=>{
  const oldFetch=globalThis.fetch,oldWindow=globalThis.window;let changed=0;const urls=[];
  globalThis.window={dispatchEvent(event){assert.equal(event.type,"notifications-changed");changed++;}};
  globalThis.fetch=async(url,init)=>{urls.push([url,init.method??"GET"]);return envelope({id:"a"});};
  try {
    await api.withdrawApplication("a");assert.equal(changed,1);
    await api.applicationDetail("a");await api.existingGrowthTask("report","requirement");assert.equal(changed,1);
    assert.deepEqual(urls.slice(1),[["/backend/api/v1/applications/a","GET"],["/backend/api/v1/match-reports/report/growth-tasks/requirement","GET"]]);
    globalThis.fetch=async()=>envelope(null,503,"failure");await assert.rejects(api.withdrawApplication("a"));assert.equal(changed,1);
  }finally{globalThis.fetch=oldFetch;if(oldWindow===undefined)delete globalThis.window;else globalThis.window=oldWindow;}
});

test("enterprise reply context is an owned report read with no model consent", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body });
    return envelope(null);
  };
  try {
    assert.equal(await api.enterpriseReplyContext("report-1", "requirement-1"), null);
    assert.deepEqual(calls, [{
      url: "/backend/api/v1/match-reports/report-1/enterprise-replies/requirement-1",
      method: "GET",
      body: undefined,
    }]);
  } finally { globalThis.fetch = original; }
});

test("human reply sends frozen report references with its text", async () => {
  const original = globalThis.fetch;
  let body;
  globalThis.fetch = async (url, init) => {
    assert.ok(url.endsWith("/applications/synthetic/reply"));
    body = JSON.parse(init.body);
    return envelope({ id: "synthetic" });
  };
  try {
    await api.replyApplication("synthetic", "continue", "【数据库】\n引用 R1-E1", [
      { requirementId: "requirement-1", citationIds: ["R1-E1"] },
    ]);
    assert.deepEqual(body, {
      kind: "continue", text: "【数据库】\n引用 R1-E1",
      references: [{ requirementId: "requirement-1", citationIds: ["R1-E1"] }],
    });
  } finally { globalThis.fetch = original; }
});
