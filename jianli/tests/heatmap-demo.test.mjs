import { test } from "node:test";
import assert from "node:assert/strict";
import { HEATMAP_DEMO, DEMO_REQUIREMENTS } from "../src/lib/heatmap-demo.ts";
import { filterApplications } from "../src/lib/application-comparison.ts";
test("demo has three synthetic identities with aligned requirement columns and no real report", () => {
 assert.equal(HEATMAP_DEMO.length, 3);
 for (const row of HEATMAP_DEMO) {
  assert.match(row.candidateName, /合成/);
  assert.equal(row.overallScore, null);
  assert.equal(row.report, undefined);
  assert.deepEqual(row.dimensions.map(d => d.requirementId), DEMO_REQUIREMENTS.map(r => r.id));
 }
 assert.equal(new Set(HEATMAP_DEMO.map(r => r.id)).size, 3);
 const unassessed=HEATMAP_DEMO[2].dimensions.find(d=>d.verdict==="unsupported");
 assert.equal(unassessed.score, null);
});
test("same production filter narrows demo by candidate, focused requirement and material state", () => {
 assert.deepEqual(filterApplications(HEATMAP_DEMO,"候选人 B","","").map(r=>r.candidateName),["合成候选人 B"]);
 assert.deepEqual(filterApplications(HEATMAP_DEMO,"","demo-sql","gap").map(r=>r.candidateName),["合成候选人 C"]);
 assert.deepEqual(filterApplications(HEATMAP_DEMO,"","demo-test","supported").map(r=>r.candidateName),["合成候选人 B"]);
 assert.equal(filterApplications(HEATMAP_DEMO,"不存在","","").length,0);
});
