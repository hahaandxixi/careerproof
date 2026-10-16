// 传智杯56：岗位页投递感知控制器回归。myApplications 只读、与材料加载解耦；
// 只有返回记录能证明具体状态，缺失/失败一律不是“未投递”，撤回史不得当成进行中投递；
// 重试只读不写、过期/岗位切换/卸载后响应必须丢弃。直接驱动真实会话控制器，非源码正则。
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(here, "../src");
const require = createRequire(import.meta.url);
const { transform } = require("sucrase");

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("next/") && !specifier.endsWith(".js")) {
      try { return nextResolve(specifier + ".js", context); } catch {}
      return nextResolve(specifier, context);
    }
    if (specifier.startsWith("@/")) {
      const base = path.join(SRC, specifier.slice(2));
      for (const candidate of [base, base + ".ts", base + ".tsx", path.join(base, "index.ts"), path.join(base, "index.tsx")]) {
        try { return nextResolve(pathToFileURL(candidate).href, context); } catch {}
      }
      throw new Error(`无法解析别名导入：${specifier}`);
    }
    if ((specifier.startsWith("./") || specifier.startsWith("../")) && !path.extname(specifier)) {
      for (const suffix of ["", ".ts", ".tsx", "/index.ts", "/index.tsx", ".js", "/index.js"]) {
        try { return nextResolve(new URL(specifier + suffix, context.parentURL).href, context); } catch {}
      }
      return nextResolve(specifier, context);
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

const status = await import(pathToFileURL(path.join(SRC, "lib/job-application-status.ts")).href);
const { createJobApplicationStatusSession, resolveJobApplicationStatus } = status;

function record(overrides = {}) {
  return { id: "app-1", jobId: "job-1", status: "submitted", createdAt: "2026-10-12T08:00:00Z", ...overrides };
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
function sessionOf(handler) {
  const calls = [];
  const session = createJobApplicationStatusSession({
    api: {
      myApplications() { calls.push("myApplications"); return handler(calls.length); },
      errorMessage: error => `显示:${error instanceof Error ? error.message : String(error)}`,
    },
    publish: value => published.push(value),
  });
  const published = [];
  return { calls, published, session };
}

test("同岗位未撤回投递解析为 active，携带真实 id/状态；重试仍只调用只读接口", async () => {
  const { calls, published, session } = sessionOf(() => [record({ status: "viewed" })]);
  session.activate();
  await session.refresh("job-1");
  assert.deepEqual(published, [
    { kind: "loading" },
    { kind: "active", application: { id: "app-1", status: "viewed", createdAt: "2026-10-12T08:00:00Z" } },
  ]);
  await session.refresh("job-1");
  assert.equal(calls.length, 2);
  assert.ok(calls.every(call => call === "myApplications"), "重试只能重读，不得触发任何写/模型动作");
});

test("其他岗位的记录不得给本岗位下结论：解析为 unknown", () => {
  assert.deepEqual(resolveJobApplicationStatus([record({ jobId: "job-2", id: "app-2" })], "job-1"), { kind: "unknown" });
  const { published, session } = sessionOf(() => [record({ jobId: "job-2", id: "app-2" })]);
  session.activate();
  return session.refresh("job-1").then(() => {
    assert.deepEqual(published, [{ kind: "loading" }, { kind: "unknown" }]);
  });
});

test("只有撤回记录时解析为 withdrawn，绝不当成进行中的投递", () => {
  const outcome = resolveJobApplicationStatus([
    record({ id: "app-w", status: "withdrawn", createdAt: "2026-10-14T08:00:00Z" }),
  ], "job-1");
  assert.deepEqual(outcome, { kind: "withdrawn", application: { id: "app-w", status: "withdrawn", createdAt: "2026-10-14T08:00:00Z" } });
});

test("撤回与进行中并存时 active 优先；多条 active 取最新 createdAt", () => {
  const mixed = resolveJobApplicationStatus([
    record({ id: "app-w", status: "withdrawn", createdAt: "2026-10-15T00:00:00Z" }),
    record({ id: "app-old", status: "submitted", createdAt: "2026-10-01T00:00:00Z" }),
  ], "job-1");
  assert.equal(mixed.kind, "active");
  assert.equal(mixed.application.id, "app-old");
  const newest = resolveJobApplicationStatus([
    record({ id: "app-new", status: "replied", createdAt: "2026-10-10T00:00:00Z" }),
    record({ id: "app-old", status: "submitted", createdAt: "2026-10-11T00:00:00Z" }),
  ], "job-1");
  assert.equal(newest.application.id, "app-old");
});

test("残缺记录不能证明任何状态：缺 id/缺 status/非对象一律 unknown", () => {
  assert.deepEqual(resolveJobApplicationStatus([
    { jobId: "job-1", status: "submitted", createdAt: "2026-10-12T08:00:00Z" },
    { id: "app-2", jobId: "job-1", createdAt: "2026-10-12T08:00:00Z" },
    { id: "app-3", jobId: "job-1", status: "", createdAt: "2026-10-12T08:00:00Z" },
    null,
    "garbage",
  ], "job-1"), { kind: "unknown" });
  assert.deepEqual(resolveJobApplicationStatus([], "job-1"), { kind: "unknown" });
});

test("读取失败解析为显式 error，绝不是未投递，也不冒充成功", async () => {
  const { published, session } = sessionOf(() => Promise.reject(new Error("网络中断")));
  session.activate();
  await session.refresh("job-1");
  assert.equal(published.length, 2);
  assert.equal(published[0].kind, "loading");
  assert.deepEqual(published[1], { kind: "error", message: "显示:网络中断" });
});

test("失败后重试成功可以恢复：仅新增一次只读调用", async () => {
  const { calls, published, session } = sessionOf(index => (index === 1 ? Promise.reject(new Error("超时")) : [record()]));
  session.activate();
  await session.refresh("job-1");
  await session.refresh("job-1");
  assert.deepEqual(calls, ["myApplications", "myApplications"]);
  assert.equal(published[3].kind, "active");
});

test("乱序响应：晚到的旧响应被丢弃，状态停留在后发起的那次读取", async () => {
  const first = deferred(), second = deferred();
  const { published, session } = sessionOf(index => (index === 1 ? first.promise : second.promise));
  session.activate();
  const read1 = session.refresh("job-1");
  const read2 = session.refresh("job-1");
  second.resolve([record({ id: "app-second" })]);
  await read2;
  first.resolve([record({ id: "app-first", status: "viewed" })]);
  await read1;
  const last = published[published.length - 1];
  assert.equal(last.kind, "active");
  assert.equal(last.application.id, "app-second", "先发出但晚返回的响应不得覆盖新状态");
});

test("岗位切换：立即清成 loading，旧岗位的迟到响应丢弃，只认新岗位数据", async () => {
  const forOld = deferred();
  const { published, session } = sessionOf(index => (index === 1 ? forOld.promise : [record({ id: "app-new", jobId: "job-2" })]));
  session.activate();
  const oldRead = session.refresh("job-1");
  const newRead = session.refresh("job-2");
  assert.equal(published[published.length - 1].kind, "loading", "切换岗位必须先清掉上一个岗位的展示");
  await newRead;
  forOld.resolve([record({ id: "app-old" })]);
  await oldRead;
  const last = published[published.length - 1];
  assert.equal(last.kind, "active");
  assert.equal(last.application.id, "app-new");
});

test("卸载后到达的响应绝不发布；dispose 前只留下 loading", async () => {
  const pending = deferred();
  const { published, session } = sessionOf(() => pending.promise);
  session.activate();
  const read = session.refresh("job-1");
  session.dispose();
  pending.resolve([record()]);
  await read;
  assert.deepEqual(published, [{ kind: "loading" }]);
});

test("未 activate 的会话不发起读取、不发布状态", async () => {
  const { calls, published, session } = sessionOf(() => [record()]);
  await session.refresh("job-1");
  assert.deepEqual(calls, []);
  assert.deepEqual(published, []);
});

test("page lifecycle invalidates hidden reads, coalesces return events and removes listeners", async () => {
  const {bindJobApplicationStatusLifecycle}=status;
  const page=new EventTarget();const doc=Object.assign(new EventTarget(),{visibilityState:"visible"});
  const first=deferred();const f=sessionOf(index=>index===1?first.promise:[record({id:"returned"})]);
  const cleanup=bindJobApplicationStatusLifecycle(f.session,"job-1",{page,document:doc});
  assert.equal(f.calls.length,1);
  page.dispatchEvent(new Event("blur"));doc.visibilityState="hidden";doc.dispatchEvent(new Event("visibilitychange"));
  first.resolve([record({id:"stale"})]);for(let i=0;i<5;i++)await Promise.resolve();
  assert.ok(f.published.every(value=>value.kind==="loading"));
  doc.visibilityState="visible";doc.dispatchEvent(new Event("visibilitychange"));
  page.dispatchEvent(new Event("focus"));page.dispatchEvent(new Event("pageshow"));
  for(let i=0;i<5;i++)await Promise.resolve();
  assert.equal(f.calls.length,2,"return event cluster reads once");
  assert.equal(f.published.at(-1).application.id,"returned");
  cleanup();page.dispatchEvent(new Event("blur"));page.dispatchEvent(new Event("focus"));
  assert.equal(f.calls.length,2);assert.equal(f.published.at(-1).application.id,"returned");
  assert.ok(f.calls.every(call=>call==="myApplications"),"lifecycle has read-only API access");
});

test("hidden mount waits until visible and cleanup rejects late response", async () => {
  const {bindJobApplicationStatusLifecycle}=status;
  const page=new EventTarget();const doc=Object.assign(new EventTarget(),{visibilityState:"hidden"});
  const pending=deferred();const f=sessionOf(()=>pending.promise);
  const cleanup=bindJobApplicationStatusLifecycle(f.session,"job-1",{page,document:doc});
  page.dispatchEvent(new Event("focus"));page.dispatchEvent(new Event("pageshow"));assert.equal(f.calls.length,0);
  doc.visibilityState="visible";doc.dispatchEvent(new Event("visibilitychange"));assert.equal(f.calls.length,1);
  cleanup();pending.resolve([record()]);for(let i=0;i<5;i++)await Promise.resolve();
  assert.deepEqual(f.published,[{kind:"loading"}]);
});
