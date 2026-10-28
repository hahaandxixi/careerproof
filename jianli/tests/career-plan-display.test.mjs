import { test } from "node:test";
import assert from "node:assert/strict";
import { careerPlanConfigurationBlocked, careerPlanFailureMessage, careerPlanRecommendations, visibleCareerChanges } from "../src/lib/career-plan-display.ts";

test("configuration, transport, output and evidence failures have distinct honest messages", () => {
  assert.match(careerPlanFailureMessage("external_ai_disabled"), /未启用外部 AI.*没有调用模型/);
  assert.match(careerPlanFailureMessage("mock_provider"), /模拟模型/);
  assert.match(careerPlanFailureMessage("model_timeout"), /超时/);
  assert.match(careerPlanFailureMessage("model_rate_limited"), /请求受限/);
  assert.match(careerPlanFailureMessage("model_quota_exceeded"), /额度不足/);
  assert.match(careerPlanFailureMessage("model_output_truncated"), /长度上限/);
  assert.match(careerPlanFailureMessage("model_output_schema_invalid"), /必要字段或结构/);
  assert.match(careerPlanFailureMessage("model_business_validation_failed"), /引用、证据或表述校验/);
  assert.ok(!careerPlanFailureMessage("model_unavailable_or_invalid").includes("通过校验"), "legacy unknown failures cannot be relabelled as validation failures");
  for (const status of ["external_ai_disabled", "mock_provider", "model_configuration_error", "model_auth_error", "model_request_rejected", "model_quota_exceeded"]) assert.equal(careerPlanConfigurationBlocked(status), true);
  for (const status of ["model_timeout", "model_network_error", "validated"]) assert.equal(careerPlanConfigurationBlocked(status), false);
});

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
