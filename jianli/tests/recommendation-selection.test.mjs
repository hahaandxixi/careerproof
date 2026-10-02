import { test } from "node:test";
import assert from "node:assert/strict";
import {
  careerPlanHref,
  jobAnalysisHref,
  resolveInitialMaterialSelection,
} from "../src/lib/recommendation-selection.ts";

test("growth continuation carries its exact material versions without starting AI", () => {
  const url = new URL(careerPlanHref("resume-v2", ["project-v2", "project-v3"]), "http://careerproof.local");
  assert.equal(url.pathname, "/recommendations");
  assert.equal(url.searchParams.get("resumeVersionId"), "resume-v2");
  assert.deepEqual(url.searchParams.getAll("projectVersionId"), ["project-v2", "project-v3"]);
  assert.deepEqual(resolveInitialMaterialSelection(["resume-v1"], ["project-v2"],
    url.searchParams.get("resumeVersionId"), url.searchParams.getAll("projectVersionId")),
    { resumeVersionId: "", projectVersionIds: ["project-v2"] });
});

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
