import { test } from "node:test";
import assert from "node:assert/strict";
import { coverageDisplay } from "../src/lib/source-coverage.ts";
import { revealEvidenceAnchor } from "../src/lib/evidence-anchor.ts";

function evidence(start, end, id, overrides = {}) {
  return { citationId: id, provenance: "portfolio", filePath: "version-a/orders.py", lineStart: start, lineEnd: end,
    functionLineStart: 1, functionLineEnd: 45, sourceLineCount: 45, contentHash: "hash-a", projectVersionId: "version-a",
    contextComplete: false, snippet: Array.from({ length: end - start + 1 }, (_, i) => `line ${start + i}`).join("\n"), ...overrides };
}
function item(entries = [evidence(1, 40, "R1-E1"), evidence(6, 45, "R1-E2")]) {
  return { evidenceList: entries,
    functionSourceCoverage: [{ file_path: "version-a/orders.py", function_line_start: 1, function_line_end: 45,
      covered_line_count: 45, fully_covered: true, citation_ids: ["R1-E1", "R1-E2"] }],
    fileSourceCoverage: [{ file_path: "version-a/orders.py", source_line_count: 45,
      covered_line_count: 45, fully_covered: true, citation_ids: ["R1-E1", "R1-E2"] }] };
}

test("overlapping bounded excerpts expose 45 actual lines, without claiming either excerpt is complete", () => {
  const source = item();
  assert.equal(source.evidenceList.every(e => !e.contextComplete), true);
  assert.deepEqual(coverageDisplay(source).map(row => [row.kind, row.covered, row.total, row.verified, row.complete]),
    [["function", 45, 45, true, true], ["file", 45, 45, true, true]]);
  assert.deepEqual(coverageDisplay(source)[0].citationIds, ["R1-E1", "R1-E2"]);
});

test("complete function does not imply complete file", () => {
  const source = item([evidence(1, 40, "R1-E1", { sourceLineCount: 80 }), evidence(6, 45, "R1-E2", { sourceLineCount: 80 })]);
  source.fileSourceCoverage[0] = { ...source.fileSourceCoverage[0], source_line_count: 80, fully_covered: false };
  const rows = coverageDisplay(source);
  assert.equal(rows[0].complete && rows[0].verified, true);
  assert.equal(rows[1].complete, false);
  assert.equal(rows[1].verified, true);
  assert.equal(rows[1].covered, 45);
  assert.equal(rows[1].total, 80);
});

test("legacy ranges are unknown rather than inferred from snippet endpoints", () => {
  assert.deepEqual(coverageDisplay({ evidenceList: item().evidenceList }), []);
  const source = item();
  delete source.evidenceList[0].functionLineStart;
  delete source.evidenceList[0].sourceLineCount;
  assert.equal(coverageDisplay(source).every(row => !row.verified && row.citationIds.length === 0), true);
});

test("a missing interior line cannot be displayed as full coverage", () => {
  const source = item([evidence(1, 20, "R1-E1"), evidence(22, 45, "R1-E2")]);
  assert.equal(coverageDisplay(source).every(row => !row.verified), true);
  source.functionSourceCoverage[0] = { ...source.functionSourceCoverage[0], covered_line_count: 44, fully_covered: false };
  source.fileSourceCoverage[0] = { ...source.fileSourceCoverage[0], covered_line_count: 44, fully_covered: false };
  assert.equal(coverageDisplay(source).every(row => row.verified && !row.complete), true);
});

test("reference, changed version, conflicting hash, and wrong file cannot complete personal coverage", () => {
  for (const overrides of [{ provenance: "reference" }, { projectVersionId: "version-b" }, { contentHash: "hash-b" }, { filePath: "version-b/orders.py" }]) {
    const source = item([evidence(1, 40, "R1-E1"), evidence(6, 45, "R1-E2", overrides)]);
    assert.equal(coverageDisplay(source).every(row => !row.verified && !row.citationIds.length), true, JSON.stringify(overrides));
  }
});

test("stale, duplicate, or missing citation identifiers and truncated snippets fail closed", () => {
  for (const alter of [
    source => source.evidenceList.pop(),
    source => source.evidenceList.push(source.evidenceList[1]),
    source => source.functionSourceCoverage[0].citation_ids.push("R1-E2"),
    source => source.evidenceList[1].snippet = "only one line",
  ]) {
    const source = item(); alter(source);
    const row = coverageDisplay(source)[0];
    assert.equal(row.verified, false);
    assert.deepEqual(row.citationIds, []);
  }
});

test("coverage beyond the source range and inconsistent full flags are not presented as verified", () => {
  const source = item();
  source.functionSourceCoverage[0].covered_line_count = 80;
  source.fileSourceCoverage[0].fully_covered = false;
  assert.equal(coverageDisplay(source).every(row => !row.verified), true);
});

test("deep links reveal nested evidence details and handle missing anchors safely", () => {
  const outer = { tagName: "DETAILS", open: false, parentElement: null };
  const inner = { tagName: "DETAILS", open: false, parentElement: outer };
  const target = { tagName: "DIV", parentElement: inner };
  const doc = { getElementById: id => id === "citation-R1-E2" ? target : null };
  assert.equal(revealEvidenceAnchor("citation-R1-E2", doc), target);
  assert.equal(inner.open && outer.open, true);
  assert.equal(revealEvidenceAnchor("citation-unknown", doc), null);
});
