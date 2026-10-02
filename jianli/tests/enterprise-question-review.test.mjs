import { test } from "node:test";
import assert from "node:assert/strict";
import { enterpriseQuestionReview } from "../src/lib/enterprise-question-review.ts";

const item = (overrides = {}) => ({
  status: "existing", changes: [], targetInformationGap: "  缺少可定位的运行结果  ",
  addedEvidence: [], ...overrides,
});

test("question review separates personal evidence from third-party reference and preserves the report gap", () => {
  assert.deepEqual(enterpriseQuestionReview(item({ addedEvidence: [
    { provenance: "portfolio" }, { provenance: "reference" }, { provenance: "portfolio" },
  ] })), {
    personalEvidenceCount: 2, referenceEvidenceCount: 1,
    criterionChanged: false, remainingGap: "缺少可定位的运行结果",
  });
});

test("reference-only evidence and a missing gap never imply the question is resolved", () => {
  assert.deepEqual(enterpriseQuestionReview(item({
    addedEvidence: [{ provenance: "reference" }], targetInformationGap: " ",
  })), {
    personalEvidenceCount: 0, referenceEvidenceCount: 1,
    criterionChanged: false, remainingGap: null,
  });
});

test("changed and removed requirements demand a separate comparison", () => {
  assert.equal(enterpriseQuestionReview(item({ changes: ["requirement"] })).criterionChanged, true);
  assert.equal(enterpriseQuestionReview(item({ status: "removed" })).criterionChanged, true);
});
