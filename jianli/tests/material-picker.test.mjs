import { test } from "node:test";
import assert from "node:assert/strict";
import { duplicateProjectNames, filterMaterialProjects, groupMaterialProjects, projectDisplayCategory, projectNameLabel, toggleMaterialVersion } from "../src/lib/material-picker.ts";

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

test("completed versions are newest-first without mutating saved order or choosing one", () => {
  const unordered = [{ id: "p", name: "作品", versions: [
    { id: "v1", versionNumber: 1, status: "completed", originalFilename: "same.zip" },
    { id: "v3", versionNumber: 3, status: "running", originalFilename: "same.zip" },
    { id: "v2", versionNumber: 2, status: "completed", originalFilename: "same.zip" },
  ] }];
  const original = structuredClone(unordered);
  assert.deepEqual(filterMaterialProjects(unordered, "")[0].versions.map(value => value.id), ["v2", "v1"]);
  assert.deepEqual(unordered, original);
});

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

test("project display groups prioritize named pairs without removing discoverable old fixtures", () => {
  const demoNames = ["CP08｜任务数据库管理｜测试项目"];
  const rows = [
    ...projects,
    { id: "cp", name: demoNames[0], versions: [{ id: "cp1", versionNumber: 1, originalFilename: "CP08.zip", status: "completed" }] },
    { id: "old", name: "Function Calling 合成项目 20260918-152713", versions: [{ id: "old1", versionNumber: 1, originalFilename: "archive.zip", status: "completed" }] },
  ];
  const original = structuredClone(rows);
  assert.deepEqual(groupMaterialProjects(rows, "", false, demoNames).map(p => p.id), ["p1", "cp"]);
  assert.equal(groupMaterialProjects(rows, "archive.zip", false, demoNames)[0].category, "history");
  assert.deepEqual(groupMaterialProjects(rows, "", true, demoNames).map(p => p.id), ["p1", "cp", "old"]);
  assert.equal(projectDisplayCategory("我的历史任务管理项目", demoNames), "personal");
  assert.equal(projectDisplayCategory("历史完整报告 injected-history 20260927", demoNames), "history");
  assert.equal(projectDisplayCategory("浏览器全链路项目-20260918", demoNames), "history");
  assert.equal(projectDisplayCategory("历史验收项目 20260926-142342", demoNames), "history");
  assert.equal(projectDisplayCategory("视觉与代码组合合成验收 20260926-230706", demoNames), "history");
  assert.deepEqual(rows, original);
});

// 同名项目若在选择器里显示成同一行，用户会选错材料、基于错误项目生成报告。
test("duplicateProjectNames only reports names that actually repeat", () => {
  assert.deepEqual([...duplicateProjectNames([])], []);
  assert.deepEqual([...duplicateProjectNames([{ name: "唯一项目" }])], []);
  const repeated = duplicateProjectNames([
    { name: "校园活动报名服务" }, { name: "校园活动报名服务" }, { name: "另一个项目" },
  ]);
  assert.deepEqual([...repeated], ["校园活动报名服务"]);
});

test("projectNameLabel adds the material number only for repeated names, so normal rows stay clean", () => {
  const duplicates = new Set(["校园活动报名服务"]);
  assert.equal(projectNameLabel("另一个项目", "aaaaaaaa1111", duplicates), "另一个项目");
  assert.equal(projectNameLabel("校园活动报名服务", "aaaaaaaa1111", duplicates), "校园活动报名服务 · 材料编号 aaaaaaaa");
  assert.equal(projectNameLabel("校园活动报名服务", "bbbbbbbb2222", duplicates), "校园活动报名服务 · 材料编号 bbbbbbbb");
  assert.equal(projectNameLabel("校园活动报名服务", "bbbbbbbb2222", new Set()), "校园活动报名服务");
});

test("同名的两个项目标题必须不同，且只显示编号前8位", () => {
  const rows = [
    { id: "aaaaaaaa1111", name: "同名项目" },
    { id: "bbbbbbbb2222", name: "同名项目" },
  ];
  const duplicates = duplicateProjectNames(rows);
  const labels = rows.map(row => projectNameLabel(row.name, row.id, duplicates));
  assert.notEqual(labels[0], labels[1], "同名项目的显示名不得相同");
  assert.deepEqual(labels, ["同名项目 · 材料编号 aaaaaaaa", "同名项目 · 材料编号 bbbbbbbb"]);
  assert.ok(labels.every(label => !label.includes("1111") && !label.includes("2222")), "不得显示整串编号");
});
