import { test } from "node:test";
import assert from "node:assert/strict";
import { createApplicationVerificationSession, verificationFailureMessage, verificationMatchesReport } from "../src/lib/application-verification-session.ts";

const task = (status = "completed") => ({
  taskId: "verification-1", status, aiStatus: status === "completed" ? "validated" : "pending",
  aiModel: "deepseek-chat", promptVersion: "enterprise-verification-v1", snapshotHash: "frozen-snapshot",
  analysis: status === "completed" ? { items: [{ requirementId: "python", visibleSupport: "实现可见", informationGap: "需核验本人贡献", verificationQuestions: ["如何定位异常？"], nextStep: "discuss_implementation", nextStepReason: "确认实现过程", citationIds: ["E1"] }] } : null,
  usage: null, inputPreflights: [], failureKind: null, currentStep: null, createdAt: "2026-09-29T00:00:00Z",
  errorMessage: null, boundary: "建议需人工确认",
});
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

test("failed saved task distinguishes a pre-send budget stop from model rejection without leaking provider text", async () => {
  const view = fixture({ latest: async () => ({ ...task("failed"), failureKind: "input_budget", errorMessage: "private-provider-body" }) });
  await view.session.load();
  assert.match(view.latest().error, /外发前停止/);
  assert.equal(view.calls.create, 0);
  assert.doesNotMatch(view.latest().error, /private-provider-body/);
  assert.match(verificationFailureMessage({ ...task("failed"), failureKind: "visible_code_fact_conflict" }), /事实冲突/);
  assert.match(verificationFailureMessage({ ...task("completed"), failureKind: "saved_validation_failed" }), /已保存的核验建议未通过/);
  assert.match(verificationFailureMessage({ ...task("failed"), failureKind: "provider_http_503", errorMessage: "private-provider-body" }), /没有自动重试/);
  assert.doesNotMatch(verificationFailureMessage({ ...task("failed"), errorMessage: "private-provider-body" }), /private-provider-body/);
  assert.match(verificationFailureMessage({ ...task("failed"), failureKind: "__proto__" }), /没有自动重试/);
  view.session.dispose();
});
const eventually = async condition => {
  const end = Date.now() + 1000;
  while (!condition()) { if (Date.now() > end) assert.fail("session did not settle"); await new Promise(resolve => setTimeout(resolve, 2)); }
};
function fixture(overrides = {}, options = {}) {
  const states = [], calls = { create: 0, read: 0, unavailable: 0 };
  const session = createApplicationVerificationSession({
    latest: async () => null,
    create: async () => { calls.create++; return task(); },
    read: async () => { calls.read++; return task(); },
    errorMessage: error => error.message,
    unavailable: error => error.status === 404 || error.status === 403,
    onUnavailable: () => { calls.unavailable++; },
    accepts: () => true,
    ...overrides,
  }, state => states.push(state), { pollMs: 1, ...options });
  session.activate();
  return { session, states, calls, latest: () => states.at(-1) };
}

test("generation requires explicit consent; loading saved suggestions never generates", async () => {
  const view = fixture();
  await view.session.load();
  await view.session.generate(false);
  assert.equal(view.calls.create, 0);
  assert.equal(view.latest().task, null);
  await view.session.generate(true);
  assert.equal(view.calls.create, 1);
  assert.equal(view.latest().task.aiStatus, "validated");
  view.session.dispose();
});

test("hiding clears AI text, aborts requests and ignores a late result", async () => {
  const pending = deferred(); let signal;
  const view = fixture({ latest: async value => { signal = value; return pending.promise; } });
  const load = view.session.load();
  view.session.clear();
  assert.equal(signal.aborted, true);
  pending.resolve(task()); await load;
  assert.equal(view.latest().task, null);
  assert.equal(view.latest().loading, false);
});

test("disposed application cannot replace a newly opened application's saved result", async () => {
  const pending = deferred(); const old = fixture({ latest: () => pending.promise });
  const load = old.session.load(); old.session.dispose();
  const next = fixture({ latest: async () => ({ ...task(), taskId: "verification-2" }) });
  await next.session.load();
  pending.resolve(task()); await load;
  assert.equal(old.latest().task, null);
  assert.equal(next.latest().task.taskId, "verification-2");
  next.session.dispose();
});

test("hiding during polling aborts the read and prevents a late completed result", async () => {
  const pending = deferred(); let readSignal;
  const view = fixture({ latest: async () => task("pending"), read: async (_taskId, signal) => { readSignal = signal; return pending.promise; } });
  await view.session.load(); await eventually(() => !!readSignal);
  view.session.clear(); assert.equal(readSignal.aborted, true);
  pending.resolve(task()); await new Promise(resolve => setTimeout(resolve, 2));
  assert.equal(view.latest().task, null); assert.equal(view.latest().loading, false);
});

test("polling reaches saved completed result without generating another task", async () => {
  const view = fixture({ latest: async () => task("pending") });
  await view.session.load();
  await eventually(() => view.latest().task?.status === "completed");
  assert.equal(view.calls.read, 1); assert.equal(view.calls.create, 0);
  assert.equal(view.latest().loading, false); view.session.dispose();
});

test("polling is finite and a later manual read resumes an existing task", async () => {
  let reads = 0;
  const view = fixture({ latest: async () => task("running"), read: async () => { reads++; return task("running"); } }, { maxPolls: 2 });
  await view.session.load();
  await eventually(() => !view.latest().loading);
  assert.equal(reads, 2); assert.match(view.latest().notice, /停止自动查询/);
  await view.session.load();
  await eventually(() => !view.latest().loading);
  assert.equal(reads, 4); assert.equal(view.calls.create, 0); view.session.dispose();
});

test("a failed poll clears AI result and does not loop or generate", async () => {
  let reads = 0;
  const view = fixture({ latest: async () => task("pending"), read: async () => { reads++; throw new Error("服务暂不可用"); } });
  await view.session.load();
  await eventually(() => !view.latest().loading);
  assert.equal(view.latest().task, null); assert.match(view.latest().error, /原报告仍可/);
  assert.equal(reads, 1); assert.equal(view.calls.create, 0); view.session.dispose();
});

test("revoked result clears saved AI text and requests an authorization refresh", async () => {
  let revoked = false;
  const view = fixture({ latest: async () => { if (revoked) throw { status: 404 }; return task(); } });
  await view.session.load(); assert.equal(view.latest().task.taskId, "verification-1");
  revoked = true; await view.session.load();
  assert.equal(view.latest().task, null); assert.equal(view.calls.unavailable, 1);
  assert.match(view.latest().error, /刷新授权投递/); view.session.dispose();
});

test("a stale revoked response cannot clear a different mounted application", async () => {
  const pending = deferred(); const view = fixture({ latest: () => pending.promise });
  const load = view.session.load(); view.session.dispose();
  pending.reject({ status: 404 }); await load;
  assert.equal(view.calls.unavailable, 0);
});

test("effect cleanup and activation reload safely without retaining a stuck loading state", async () => {
  const pending = deferred(); let attempt = 0;
  const view = fixture({ latest: () => ++attempt === 1 ? pending.promise : Promise.resolve(task()) });
  const stale = view.session.load(); view.session.dispose(); view.session.activate();
  await view.session.load(); pending.resolve(null); await stale;
  assert.equal(view.latest().task.taskId, "verification-1");
  assert.equal(view.latest().loading, false); view.session.dispose();
});

test("AI output uses each frozen requirement's citations and cannot borrow another requirement's evidence", () => {
  const report = { items: [{ requirementId: "python", evidenceList: [{ citationId: "E1" }] }, { requirementId: "redis", evidenceList: [{ citationId: "E2" }] }] };
  const output = task(); output.analysis.items.push({ ...output.analysis.items[0], requirementId: "redis", citationIds: [] });
  assert.equal(verificationMatchesReport(output, report), true);
  output.analysis.items[0].citationIds = ["E2"];
  assert.equal(verificationMatchesReport(output, report), false);
  output.analysis.items[0].citationIds = ["E1"];
  output.analysis.items[1].requirementId = "private-requirement";
  assert.equal(verificationMatchesReport(output, report), false);
});

test("mismatched frozen report output is cleared before display", async () => {
  const view = fixture({ latest: async () => task(), accepts: () => false });
  await view.session.load(); assert.equal(view.latest().task, null);
  assert.match(view.latest().error, /固定报告要求或引用/); view.session.dispose();
});

test("legacy fixed reports may use their own saved primary evidence, while duplicate requirements are rejected", () => {
  const report = { items: [{ requirementId: "python", evidenceList: [], evidence: { citationId: "E1" } }] };
  const output = task();
  assert.equal(verificationMatchesReport(output, report), true);
  output.analysis.items.push({ ...output.analysis.items[0] });
  assert.equal(verificationMatchesReport(output, report), false);
});
