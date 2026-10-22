import test from "node:test";
import assert from "node:assert/strict";
import { safeReturnPath, authEntry, roleReturnPath, checkedReturnPath, authReturnFromLocation } from "../src/lib/auth-return.ts";

test("return accepts only known internal pages and preserves selected materials and citation", () => {
  const target = "/jobs/owned-job?resumeVersionId=v1&projectVersionId=p1#matching";
  assert.equal(safeReturnPath(target), target);
  assert.equal(new URL(authEntry("/login", target), "https://local.invalid").searchParams.get("next"), target);
  assert.equal(new URL(authEntry("/register", target), "https://local.invalid").searchParams.get("next"), target);
});

test("external, encoded path, authentication loops and mutation endpoints cannot be return destinations", () => {
  for (const raw of ["//evil.test", "https://evil.test", "/\\evil.test", "/%2f%2fevil.test", "/login?next=/reports", "/register", "/backend/api/v1/applications", "/jobs/a\n", "/jobs/%61", "/unknown", "javascript:alert(1)"]) assert.equal(safeReturnPath(raw), null, raw);
});

test("role defaults cannot land a student in enterprise tools or enterprise in private material work", () => {
  assert.equal(roleReturnPath("/jobs/abc/applications", "student"), "/portfolio");
  assert.equal(roleReturnPath("/growth/abc", "enterprise"), "/jobs/mine");
  assert.equal(roleReturnPath("/reports/abc", "enterprise"), "/jobs/mine");
  assert.equal(roleReturnPath("/tasks/abc", "enterprise"), "/jobs/mine");
  assert.equal(roleReturnPath(null, "admin"), "/jobs");
  assert.equal(roleReturnPath("/jobs/abc?resumeVersionId=v1", "student"), "/jobs/abc?resumeVersionId=v1");
});

test("owned saved resources are checked with read-only calls; denied resources fall back", async () => {
  const calls = [];
  const api = new Proxy({}, { get: (_, name) => async (...args) => { calls.push([name, ...args]); if (args[0] === "other-owner") throw { status: 404 }; } });
  assert.equal(await checkedReturnPath("/growth/owned#private-answer", "student", api), "/growth/owned#private-answer");
  assert.deepEqual(calls, [["growthTask", "owned"]]);
  assert.equal(await checkedReturnPath("/reports/other-owner", "student", api), "/portfolio");
  assert.equal(await checkedReturnPath("/jobs/owned/applications", "enterprise", api), "/jobs/owned/applications");
  assert.deepEqual(calls.at(-1), ["jobApplications", "owned", 1, 1]);
  assert.ok(calls.every(([name]) => !/create|view|readNotification|reply|save|analyze|withdraw/.test(name)));
});

test("temporary connection failure keeps recoverable destination rather than pretending access was denied", async () => {
  const api = { getReport: async () => { throw new Error("offline"); } };
  assert.equal(await checkedReturnPath("/reports/owned#citation-R1-E1", "student", api), "/reports/owned#citation-R1-E1");
});

test("header auth links retain the original task and edit routes verify company ownership", async () => {
  const original = "/growth/owned#private-answer";
  assert.equal(authReturnFromLocation("/login", "?next=" + encodeURIComponent(original)), original);
  assert.equal(authReturnFromLocation("/register", "?next=//evil.test"), null);
  assert.equal(authReturnFromLocation("/jobs/owned", "?resumeVersionId=v1", "#matching"), "/jobs/owned?resumeVersionId=v1#matching");
  assert.equal(roleReturnPath("/jobs/owned/edit", "student"), "/portfolio");
  const calls = [];
  const api = { jobApplications: async (...args) => { calls.push(args); } };
  assert.equal(await checkedReturnPath("/jobs/owned/edit", "enterprise", api), "/jobs/owned/edit");
  assert.deepEqual(calls, [["owned", 1, 1]]);
});

test("admin edit return uses job access without requesting enterprise-only candidates", async () => {
  const calls = [];
  const api = {
    getJob: async (id) => { calls.push(["getJob", id]); },
    jobApplications: async () => { throw { status: 403 }; },
  };
  assert.equal(await checkedReturnPath("/jobs/owned/edit", "admin", api), "/jobs/owned/edit");
  assert.deepEqual(calls, [["getJob", "owned"]]);
  api.getJob = async () => { throw { status: 404 }; };
  assert.equal(await checkedReturnPath("/jobs/missing/edit", "admin", api), "/jobs");
});
