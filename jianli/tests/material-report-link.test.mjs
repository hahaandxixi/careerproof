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

test("full source return restores each report filter without accepting arbitrary values",()=>{
 for(const filter of ["priority","all","supported","partial","gaps","other"]){
  const params=materialReportContext("report-1","req-1","citation-S1",filter,"q=SQL&page=2");
  const target=new URL(materialReportReturn(Object.fromEntries(params)),"http://localhost");
  assert.equal(target.pathname,"/reports/report-1");
  assert.equal(target.hash,"#citation-S1");
  assert.equal(target.searchParams.get("filter"),filter);
  assert.equal(target.searchParams.get("from"),"q=SQL&page=2");
 }
 assert.equal(materialReportReturn({reportId:"report-1",requirementId:"req-1",filter:"invalid"}),"/reports/report-1#requirement-req-1");
});

test("material-level returns retain a full encoded search and its history scope", () => {
  const origin = new URLSearchParams({
    q: "岗位".repeat(100), jobId: "1a234567-1234-1234-1234-123456789abc",
    candidateId: "candidate-1", page: "2", history: "1",
  }).toString();
  const params = materialReportContext("report-1", undefined, undefined, "gaps", origin);
  const target = new URL(materialReportReturn(Object.fromEntries(params)), "http://localhost");
  assert.equal(target.hash, "#report-materials");
  assert.equal(target.searchParams.get("filter"), "gaps");
  assert.equal(target.searchParams.get("from"), origin);
});
