import { test } from "node:test";
import assert from "node:assert/strict";
import { applicationFilterView, filterApplications, mixedComparisonBasis } from "../src/lib/application-comparison.ts";

const item = (id, score, verdict, basis = "same", at = "2026-09-28T12:00:00Z") => ({
  id, candidateName: id, createdAt: at, comparisonBasis: basis, overallScore: score,fixedRequirementBasisComplete:true,
  dimensions: [{ requirementId: "sql", title: "数据库查询", skill: "SQL", score, verdict }],
});

test("filtering keeps unsupported and claimed-only separate from evidence-backed rows", () => {
  const values = [item("自述", 90, "claimed_only"), item("作品", 40, "partial"), item("不可评", null, "unsupported")];
  assert.deepEqual(filterApplications(values, "sql", "sql", "supported").map(i => i.id), ["作品"]);
  assert.deepEqual(filterApplications(values, "", "sql", "unsupported").map(i => i.id), ["不可评"]);
  assert.deepEqual(filterApplications(values, "", "absent", "supported"), []);
  assert.deepEqual(values.map(i => i.id), ["自述", "作品", "不可评"]);
});

test("incomparable versions sort by submission time rather than implying a score ranking", () => {
  const values = [item("旧要求高分", 99, "supported", "old"), item("新要求低分", 30, "partial", "new", "2026-09-28T13:00:00Z")];
  assert.equal(mixedComparisonBasis(values), true);
  assert.deepEqual(filterApplications(values, "", "sql", "").map(i => i.id), ["新要求低分", "旧要求高分"]);
  assert.equal(mixedComparisonBasis([item("a", 50, "partial", ""), item("b", 60, "partial")]), true);
  assert.equal(mixedComparisonBasis([item("a", 50, "partial")]), false);
});

test("equal criteria use saved scores with unassessed values last", () => {
  const values = [item("未评", null, "unsupported"), item("低", 20, "partial"), item("高", 50, "supported")];
  assert.deepEqual(filterApplications(values, "", "sql", "").map(i => i.id), ["高", "低", "未评"]);
});

test("missing fixed comparison fields are unknown and cannot imply score-based ranking",()=>{
 const values=[{...item("旧记录",99,"supported"),fixedRequirementBasisComplete:undefined},{...item("新记录",20,"partial","same","2026-10-01T00:00:00Z"),fixedRequirementBasisComplete:false}];
 assert.equal(mixedComparisonBasis(values),true);
 assert.deepEqual(filterApplications(values,"","","").map(i=>i.id),["新记录","旧记录"]);
});

test("filter view reports empty results and selected reports outside the current filter", () => {
  const values = [item("甲", 50, "partial"), item("乙", 60, "supported")];
  const outside = applicationFilterView(values, "甲", "", "", "乙");
  assert.deepEqual(outside.visible.map(i => i.id), ["甲"]);
  assert.equal(outside.empty, false);
  assert.equal(outside.selectedOutside, true);
  const empty = applicationFilterView(values, "不存在", "", "", "乙");
  assert.deepEqual(empty.visible, []);
  assert.equal(empty.empty, true);
  assert.equal(empty.selectedOutside, true);
  assert.equal(applicationFilterView(values, "", "", "", "甲").selectedOutside, false);
});
