import { test } from "node:test";
import assert from "node:assert/strict";
import { careerPlanRecommendations, visibleCareerChanges } from "../src/lib/career-plan-display.ts";

const recommendations = Array.from({ length: 10 }, (_, index) => ({
  jobId: `job-${index}`, jobTitle: "相同岗位名称", companyName: `企业${index}`,
  evidence: [{ citationId: `J${index}-E1` }],
}));

test("only AI-compared jobs are shown initially, retaining rule order and distinct companies", () => {
  const result = { recommendations, aiPlan: { focusJobId: "job-8", advice: [
    { jobId: "job-8" }, { jobId: "job-2" }, { jobId: "job-5" },
  ] } };
  const before = structuredClone(result);
  assert.deepEqual(careerPlanRecommendations(result, false).map(item => item.jobId),
    ["job-2", "job-5", "job-8"]);
  assert.deepEqual(result, before);
  assert.equal(careerPlanRecommendations(result, true), recommendations);
});

test("model unavailable results retain the top three rule candidates and all saved candidates", () => {
  const result = { recommendations, aiPlan: null };
  assert.deepEqual(careerPlanRecommendations(result, false).map(item => item.jobId),
    ["job-0", "job-1", "job-2"]);
  assert.equal(careerPlanRecommendations(result, true).length, 10);
});

test("rejected model diagnostics never link to a candidate hidden by the compact view", () => {
  const result = { recommendations, aiPlan: null, aiValidationIssues: [
    { citationIds: ["J8-E1", "unknown"] },
  ] };
  assert.deepEqual(careerPlanRecommendations(result, false).map(item => item.jobId),
    ["job-0", "job-1", "job-2", "job-8"]);
});

test("empty or older saved results with unmatched advice do not invent or discard candidates", () => {
  assert.deepEqual(careerPlanRecommendations({ recommendations: [], aiPlan: null }, false), []);
  assert.deepEqual(careerPlanRecommendations({ recommendations: recommendations.slice(0, 2),
    aiPlan: { focusJobId: "absent", advice: [{ jobId: "absent" }] },
  }, false), recommendations.slice(0, 2));
});

test("a previous focus job absent from current candidates remains visible in changes", () => {
  const changes = [
    { jobId: "job-0", status: "current", detail: "本轮仍在" },
    { jobId: "job-old", status: "not_in_current", detail: "本轮列表未见" },
    { jobId: "job-8", status: "current", detail: "本轮收起" },
  ];
  assert.deepEqual(visibleCareerChanges(changes, recommendations.slice(0, 1)), changes.slice(0, 2));
  assert.deepEqual(visibleCareerChanges(changes, []), [changes[1]]);
});
