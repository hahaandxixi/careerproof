import { test } from "node:test";
import assert from "node:assert/strict";
import { planMatchesReport } from "../src/lib/career-plan-report.ts";

test("a career plan can only accompany the same job and exact fixed materials", () => {
  const resume = { kind:"resume", id:"r1", contentHash:"h1" };
  const project = { kind:"project", id:"p1", contentHash:"h2" };
  const plan = { materials:[resume, project] };
  assert.equal(planMatchesReport(plan, {jobId:"job",materials:[project,resume]}, "job"), true);
  for (const report of [
    {jobId:"other",materials:[resume,project]},
    {jobId:"job",materials:[resume,{...project,id:"p2"}]},
    {jobId:"job",materials:[resume,{...project,contentHash:"changed"}]},
    {jobId:"job",materials:[resume]},
    {jobId:"job",materials:[resume,{...project,contentHash:""}]},
    {jobId:"job"},
  ]) assert.equal(planMatchesReport(plan, report, "job"), false);
});
