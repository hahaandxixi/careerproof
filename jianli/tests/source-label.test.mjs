import test from "node:test";
import assert from "node:assert/strict";
import { sourceLabel, sourceLocationId } from "../src/lib/source-label.ts";

const VERSION_A = "11111111-1111-4111-8111-111111111111";
const VERSION_B = "11111111-1111-4111-8111-222222222222";
const NESTED_UUID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const material = (id, title, versionNumber) => ({ kind: "project", id, title, versionNumber });
const compact = value => value.replace(/\s+/g, "");

test("two projects with service.py keep distinct saved project names", () => {
  const materials = [material(VERSION_A, "订单服务", 1), material(VERSION_B, "库存服务", 1)];
  const a = sourceLabel({ filePath: `${VERSION_A}/service.py`, projectVersionId: VERSION_A }, materials);
  const b = sourceLabel({ filePath: `${VERSION_B}/service.py`, projectVersionId: VERSION_B }, materials);
  assert.ok(a.includes("订单服务") && b.includes("库存服务"));
  assert.ok(a.includes("service.py") && b.includes("service.py"));
  assert.notEqual(a, b);
});

test("same project file in two saved versions stays distinguishable", () => {
  const materials = [material(VERSION_A, "订单服务", 1), material(VERSION_B, "订单服务", 2)];
  const a = sourceLabel({ filePath: `${VERSION_A}/service.py`, projectVersionId: VERSION_A }, materials);
  const b = sourceLabel({ filePath: `${VERSION_B}/service.py`, projectVersionId: VERSION_B }, materials);
  assert.ok(compact(a).includes("第1版"));
  assert.ok(compact(b).includes("第2版"));
  assert.notEqual(a, b);
});

test("duplicate title and version do not collapse even when IDs share eight characters", () => {
  const materials = [material(VERSION_A, "服务", 1), material(VERSION_B, "服务", 1)];
  const labels = [VERSION_A, VERSION_B].map(projectVersionId => sourceLabel({
    filePath: `${projectVersionId}/service.py`, projectVersionId,
  }, materials));
  assert.equal(new Set(labels).size, 2);
});

test("only the proven leading version prefix is shortened, never a nested UUID", () => {
  const path = `${VERSION_A}/snapshots/${NESTED_UUID}/service.py`;
  const label = sourceLabel({ filePath: path, projectVersionId: VERSION_A }, [
    material(VERSION_A, "订单服务", 3),
  ]);
  assert.ok(label.includes(`snapshots/${NESTED_UUID}/service.py`));
  assert.ok(compact(label).includes("第3版"));
});

test("UUID in a legitimate filename and a non-matching leading UUID are preserved", () => {
  const materials = [material(VERSION_A, "订单服务", 1)];
  for (const filePath of [`archive/${NESTED_UUID}.py`, `${VERSION_B}/service.py`]) {
    const label = sourceLabel({ filePath, projectVersionId: VERSION_A }, materials);
    assert.ok(label.includes(filePath), label);
  }
});

test("historical or unrecognized metadata leaves the full raw source available", () => {
  const filePath = `${VERSION_A}/service.py`;
  assert.ok(sourceLabel({ filePath }).includes(filePath));
  assert.ok(sourceLabel({ filePath, projectVersionId: VERSION_A }, []).includes(filePath));
  assert.ok(sourceLabel({ filePath, projectVersionId: null }, [
    material(VERSION_A, "当前同名项目", 9),
  ]).includes(filePath));
});

test("labels use the supplied fixed snapshot rather than another report's current version", () => {
  const source = { filePath: `${VERSION_A}/service.py`, projectVersionId: VERSION_A };
  const fixed = sourceLabel(source, [material(VERSION_A, "投递时名称", 1)]);
  const unrelated = sourceLabel(source, [material(VERSION_B, "后来重命名项目", 2)]);
  assert.ok(fixed.includes("投递时名称"));
  assert.ok(compact(fixed).includes("第1版"));
  assert.ok(!unrelated.includes("后来重命名项目"));
  assert.ok(unrelated.includes(source.filePath));
});

test("formatting does not mutate paths, snippets, IDs, ranges or frozen material metadata", () => {
  const source = Object.freeze({
    filePath: `${VERSION_A}/service.py`, projectVersionId: VERSION_A,
    citationId: "R1-E2", projectFileId: "original-file-id", lineStart: 8, lineEnd: 12,
    snippet: `return "${VERSION_A}/service.py"`,
  });
  const materials = Object.freeze([Object.freeze(material(VERSION_A, "订单服务", 1))]);
  const before = JSON.stringify({ source, materials });
  sourceLabel(source, materials);
  sourceLocationId("requirement-original", source, 3);
  assert.equal(JSON.stringify({ source, materials }), before);
});

test("range cards preserve citation anchors and give uncited candidates stable distinct anchors", () => {
  assert.equal(sourceLocationId("req", { citationId: "R1-E2" }, 9), "citation-R1-E2");
  assert.equal(sourceLocationId("req", { citationId: null }, 0), "rule-source-req-1");
  assert.equal(sourceLocationId("req", {}, 1), "rule-source-req-2");
  assert.notEqual(sourceLocationId("req", {}, 0), sourceLocationId("req", {}, 1));
});
