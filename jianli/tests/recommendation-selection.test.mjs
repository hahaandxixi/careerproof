import { test } from "node:test";
import assert from "node:assert/strict";
import {
  jobAnalysisHref,
  resolveInitialMaterialSelection,
} from "../src/lib/recommendation-selection.ts";

test("career recommendation carries the exact selected material versions to the job", () => {
  const href = jobAnalysisHref("job 1", "resume-2", ["project-3", "project-4"]);
  const url = new URL(href, "http://careerproof.local");
  assert.equal(url.pathname, "/jobs/job%201");
  assert.equal(url.searchParams.get("resumeVersionId"), "resume-2");
  assert.deepEqual(url.searchParams.getAll("projectVersionId"), ["project-3", "project-4"]);
});

test("job analysis accepts only completed owned versions and removes duplicates", () => {
  assert.deepEqual(
    resolveInitialMaterialSelection(
      ["resume-1", "resume-2"],
      ["project-1", "project-2"],
      "resume-2",
      ["project-2", "missing", "project-2"],
    ),
    { resumeVersionId: "resume-2", projectVersionIds: ["project-2"] },
  );
});

test("invalid requested resume stays unselected instead of silently replacing materials", () => {
  assert.deepEqual(
    resolveInitialMaterialSelection(["resume-1"], ["project-1"], "missing", ["missing"]),
    { resumeVersionId: "", projectVersionIds: [] },
  );
});

test("direct job entry does not automatically select the newest career case", () => {
  assert.deepEqual(
    resolveInitialMaterialSelection(["CP09-resume", "CP08-resume"], ["CP09-project"], "", []),
    { resumeVersionId: "", projectVersionIds: [] },
  );
});
