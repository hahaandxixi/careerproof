import { test } from "node:test";
import assert from "node:assert/strict";
import { createGrowthRequestGuard, growthCanSelect } from "../src/lib/growth-workflow.ts";

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
