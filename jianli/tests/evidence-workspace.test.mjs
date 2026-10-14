import { test } from "node:test";
import assert from "node:assert/strict";
import { evidenceWorkspace, evidenceWorkspaceSummary, distinctActionText } from "../src/lib/evidence-workspace.ts";
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

test("all gaps survive a three-item action plan; priority uses weight, level then report order", () => {
 const items = Array.from({ length: 6 }, (_, index) => ({ ...item(`r${index}`, "gap", 5), requirementTitle: `要求${index}`, evidenceLevel: index < 2 ? 2 : null }));
 const state = evidenceWorkspace(items);
 assert.equal(state.gaps.length, 6);
 assert.deepEqual(state.gaps.map(value => value.requirementId), ["r2", "r3", "r4", "r5", "r0", "r1"]);
 assert.equal(state.supported.length + state.partial.length + state.gaps.length + state.other.length, items.length);
});

test("summary preserves every saved status, excludes reviewed items from support and invents no recommendation", () => {
 const items = [{ ...item("a", "supported"), requirementTitle: "接口" }, { ...item("b", "claimed_only", 5), requirementTitle: "Python" }, { ...item("c", "supported", 5, "rejected"), requirementTitle: "SQL" }];
 const summary = evidenceWorkspaceSummary(items);
 assert.match(summary, /3 项要求：1 项有证据支持、0 项部分支持、1 项待补材料、1 项未覆盖或需复核/);
 assert.ok(summary.includes("先补「Python」的材料缺口"));
 assert.ok(!evidenceWorkspaceSummary([items[0]]).includes("先补"));
 assert.ok(!evidenceWorkspaceSummary([]).includes("0 项有证据支持"));
});

test("deduplication hides identical saved advice and gaps while retaining distinct AI text", () => {
 assert.deepEqual(distinctActionText({ action: "补充实现材料。", evidenceGap: "补充实现材料。" }), { advice: "补充实现材料。", gap: "" });
 assert.deepEqual(distinctActionText({ action: "补充实现材料。", evidenceGap: "补充实现材料。" }, "补充实现材料。"), { advice: "", gap: "" });
 assert.deepEqual(distinctActionText({ action: "核对  运行结果", evidenceGap: "核对\n运行结果" }), { advice: "核对  运行结果", gap: "" });
 assert.deepEqual(distinctActionText({ action: "保存接口运行记录", evidenceGap: "缺少失败分支记录" }, "缺少参数校验"), { advice: "保存接口运行记录", gap: "缺少失败分支记录" });
});
