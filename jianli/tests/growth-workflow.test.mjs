import { test } from "node:test";
import assert from "node:assert/strict";
import { createGrowthRequestGuard, growthCanSelect, growthAutoQueryStep } from "../src/lib/growth-workflow.ts";

test("hiding or switching accounts invalidates an in-flight saved task or generation response", () => {
  const old = createGrowthRequestGuard();
  const request = old.start(); old.clear();
  assert.equal(old.accepts(request), false);
  const next = old.start();
  assert.equal(old.accepts(request), false);
  assert.equal(old.accepts(next), true);
});

test("a newer read or mutation prevents an older response from replacing the selected versions", () => {
  const guard = createGrowthRequestGuard();
  const read = guard.start(), mutation = guard.start();
  assert.equal(guard.accepts(read), false);
  assert.equal(guard.accepts(mutation), true);
});

test("pending or compared reports freeze selected materials; only an explicit failed workflow can reselect", () => {
  assert.equal(growthCanSelect({ analysisTaskId: null, status: "planned" }), true);
  for (const status of ["analyzing", "compared"]) assert.equal(growthCanSelect({ analysisTaskId: "saved", status }), false);
  assert.equal(growthCanSelect({ analysisTaskId: "failed", status: "analysis_failed" }), true);
});

test("B-13: a successful refresh that finds the task finished clears the stopped-auto-query notice", () => {
  // 读取已保存任务 succeeded: the reload reset the poll budget and the saved
  // task is no longer analyzing, so the stale stop notice must be cleared.
  const plan = growthAutoQueryStep({ polls: 0, analyzing: false });
  assert.equal(plan.poll, false);
  assert.equal(plan.notice, "");
});

test("B-13: re-entering normal querying plans polls without the stopped notice", () => {
  const plan = growthAutoQueryStep({ polls: 0, analyzing: true });
  assert.equal(plan.poll, true);
  assert.equal(plan.notice, "");
});

test("B-13: an exhausted poll budget still stops polling with the stop notice", () => {
  const plan = growthAutoQueryStep({ polls: 60, analyzing: true });
  assert.equal(plan.poll, false);
  assert.ok(plan.notice.startsWith("已停止自动查询"));
});

test("B-13: a failed or busy refresh keeps its error visible and leaves the notice untouched", () => {
  const failed = growthAutoQueryStep({ polls: 0, analyzing: true, error: "网络错误，请稍后重试" });
  assert.equal(failed.poll, false);
  assert.equal(failed.notice, null);
  const busy = growthAutoQueryStep({ polls: 0, analyzing: true, busy: true });
  assert.equal(busy.poll, false);
  assert.equal(busy.notice, null);
});
