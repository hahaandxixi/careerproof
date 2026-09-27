import { test } from "node:test";
import assert from "node:assert/strict";
import { filterMaterialProjects, toggleMaterialVersion } from "../src/lib/material-picker.ts";

const projects = [
  { id: "p1", name: "后端练习", versions: [
    { id: "v2", versionNumber: 2, originalFilename: "api.zip", status: "completed" },
    { id: "v1", versionNumber: 1, originalFilename: "old.zip", status: "completed" },
    { id: "v3", versionNumber: 3, originalFilename: "new.zip", status: "running" },
  ] },
  { id: "p2", name: "未完成项目", versions: [
    { id: "failed", versionNumber: 1, originalFilename: null, status: "failed" },
  ] },
];

test("search excludes unfinished versions and finds historical filenames without mutating history", () => {
  const original = structuredClone(projects);
  assert.deepEqual(filterMaterialProjects(projects, " API.ZIP ")[0].versions.map(v => v.id), ["v2"]);
  assert.deepEqual(filterMaterialProjects(projects, "后端")[0].versions.map(v => v.id), ["v2", "v1"]);
  assert.deepEqual(filterMaterialProjects(projects, "").map(p => p.id), ["p1"]);
  assert.deepEqual(projects, original);
});

test("hiding selected versions by search does not discard the selection", () => {
  const selected = ["v1", "v2"];
  assert.deepEqual(filterMaterialProjects(projects, "not-found"), []);
  assert.deepEqual(toggleMaterialVersion(selected, "v2", false), ["v1"]);
  assert.deepEqual(selected, ["v1", "v2"]);
});

test("ten-version limit keeps selected versions removable and does not duplicate IDs", () => {
  const selected = Array.from({length: 10}, (_, i) => `v${i}`);
  assert.deepEqual(toggleMaterialVersion(selected, "extra", true), selected);
  assert.deepEqual(toggleMaterialVersion(selected, "v0", true), selected);
  const removed = toggleMaterialVersion(selected, "v0", false);
  assert.equal(toggleMaterialVersion(removed, "extra", true).length, 10);
  assert.equal(removed.includes("v0"), false);
});
