import { test } from "node:test";
import assert from "node:assert/strict";
import { evidenceWorkspace } from "../src/lib/evidence-workspace.ts";
const item = (id, verdict, weight = 1, confirmationStatus = "pending") => ({ requirementId: id, verdict, weight, confirmationStatus });
test("unsupported, rejected, corrected and unknown states never inflate support counts", () => {
 const result = evidenceWorkspace([item("a", "supported"), item("b", "verified"), item("c", "partial"), item("d", "gap"), item("e", "claimed_only"), item("f", "unsupported"), item("g", "supported", 5, "rejected"), item("h", "partial", 5, "corrected"), item("i", "future")]);
 assert.deepEqual([result.supported.length, result.partial.length, result.gaps.length, result.other.length], [2,1,2,4]);
 assert.deepEqual(result.priorities.map(x => x.requirementId), ["c","d","e"]);
});
test("priorities preserve requirement identities, stable equal weights and original report order", () => {
 const items = [item("low", "gap", 1), item("high", "partial", 5), item("equal", "claimed_only", 5)];
 const before = JSON.stringify(items);
 assert.deepEqual(evidenceWorkspace(items).priorities.map(x => x.requirementId), ["high", "equal", "low"]);
 assert.equal(JSON.stringify(items), before);
});
test("empty or fully supported reports do not invent a deficiency or completion claim", () => {
 assert.equal(evidenceWorkspace([]).priorities.length, 0);
 assert.equal(evidenceWorkspace([item("a", "supported")]).priorities.length, 0);
});
