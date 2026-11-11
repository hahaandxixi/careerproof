import test from "node:test";
import assert from "node:assert/strict";
import { materialReportContext, materialReportReturn } from "../src/lib/material-report-link.ts";

test("material preview carries the original saved report citation in the URL", () => {
  const query = materialReportContext("report-1", "req-2", "citation-R2-E1");
  assert.equal(materialReportReturn(Object.fromEntries(query)), "/reports/report-1#citation-R2-E1");
  assert.equal(materialReportReturn({ reportId: "report-1", requirementId: "req-2" }), "/reports/report-1#requirement-req-2");
  assert.equal(materialReportReturn({ reportId: "report-1" }), "/reports/report-1#report-materials");
});

test("only fixed report routes are accepted as material return destinations", () => {
  assert.equal(materialReportReturn({ reportId: "https://example.com" }), undefined);
  assert.equal(materialReportReturn({ reportId: "../jobs" }), undefined);
  assert.equal(materialReportReturn({}), undefined);
  assert.equal(materialReportReturn({ reportId: "report-1", requirementId: "req-2", sourceId: "rule-source-req-3-1" }), "/reports/report-1#requirement-req-2");
});
