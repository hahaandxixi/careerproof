import { test } from "node:test";
import assert from "node:assert/strict";
import { HEATMAP_DEMO, DEMO_REQUIREMENTS, demoCellClass } from "../src/lib/heatmap-demo.ts";
import { heatmapCellClass } from "../src/lib/heatmap-cell.js";
import { filterApplications } from "../src/lib/application-comparison.ts";
import { RULE_SCORE_CAP } from "../src/lib/evidence-display.ts";

test("preset interface scores stay within the current material-support rule scale", () => {
 for (const row of HEATMAP_DEMO) for (const dimension of row.dimensions) {
  if (dimension.score !== null) assert.ok(dimension.score >= 0 && dimension.score <= RULE_SCORE_CAP);
  if (dimension.verdict === "claimed_only") assert.equal(dimension.score, 10);
 }
});
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

test("demo and real heatmaps use evidence states even when the current rule cap is below 75", () => {
 for (const row of HEATMAP_DEMO) for (const d of row.dimensions) {
  assert.equal(heatmapCellClass(d.verdict, d.score), demoCellClass(d.verdict));
 }
 assert.match(heatmapCellClass("supported", 65), /emerald/);
 assert.match(heatmapCellClass("partial", 40), /indigo/);
 // Historic high self claims must remain self claims, never look evidence-backed.
 assert.match(heatmapCellClass("claimed_only", 90), /amber.*border-dashed/);
 assert.match(heatmapCellClass("gap", 0), /border-dashed/);
 for (const score of [null, NaN, Infinity, -1, 101]) assert.match(heatmapCellClass("supported", score), /slate/);
 assert.match(heatmapCellClass("future", 65), /slate/);
});
