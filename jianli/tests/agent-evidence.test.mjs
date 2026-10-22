import { test } from "node:test";
import assert from "node:assert/strict";
import { agentEvidenceRows, agentProcessSummary } from "../src/lib/agent-evidence.ts";
import { reportModeLabel } from "../src/lib/report-display.ts";

const evidence = (citationId, snippet) => ({ citationId, snippet, filePath: "project/order.py", lineStart: 1, lineEnd: 3 });
function report() {
  return { analysisMode: "ai_evidence", aiFallbackUsed: false, aiProcess: {}, aiToolCalls: [
    { tool: "retrieve_more_evidence", status: "completed", requirementId: "order", resultCount: 1, citationId: "R1-E3" },
  ], items: [{ requirementId: "order", aiStatus: "validated", aiCitationIds: ["R1-E3"], evidenceList: [
    evidence("R1-E1", "initial entry"), evidence("R1-E2", "initial write"), evidence("R1-E3", "store.rollback()"),
  ] }] };
}
test("saved added citation maps to its own requirement without claiming exact initial inputs", () => {
  const value = report();
  value.items.push({ requirementId: "other", aiCitationIds: ["R1-E3"], evidenceList: [evidence("R1-E3", "wrong owner scope")] });
  const row = agentEvidenceRows(value)[0];
  assert.equal(row.added.snippet, "store.rollback()");
  assert.deepEqual(row.otherSaved.map(e => e.citationId), ["R1-E1", "R1-E2"]);
  assert.equal(row.initial, undefined);
  assert.equal(row.used, true);
  assert.match(row.influence, /不等于评级提升/);
});
test("stored citation cannot be called adopted when its AI explanation was not validated", () => {
  const value = report(); value.items[0].aiStatus = "rejected";
  assert.equal(agentEvidenceRows(value)[0].used, false);
  assert.match(agentEvidenceRows(value)[0].influence, /没有可确认/);
});
test("fallback cannot claim that a retrieved citation was accepted by final AI", () => {
  const value = report(); value.aiFallbackUsed = true;
  assert.equal(agentEvidenceRows(value)[0].used, false);
  assert.match(agentEvidenceRows(value)[0].influence, /规则结果/);
});
test("missing saved citation does not invent a source or a conclusion change", () => {
  const value = report(); value.aiToolCalls[0].citationId = "unknown";
  assert.equal(agentEvidenceRows(value)[0].added, undefined);
  assert.match(agentEvidenceRows(value)[0].action, /不能确认/);
});
test("model stop, program budget skip, unavailable search and zero result stay distinct", () => {
  const value = report(); value.aiToolCalls = [{ tool: "retrieve_more_evidence", status: "not_requested" }];
  assert.match(agentProcessSummary(value), /模型返回/);
  value.aiToolCalls = []; value.aiProcess.planningSkippedReason = "report_budget_reserved";
  assert.match(agentProcessSummary(value), /不是模型主动/);
  value.aiProcess = {}; assert.match(agentProcessSummary(value), /不能据此认定/);
  value.aiToolCalls = [{ tool: "retrieve_more_evidence", status: "unavailable" }];
  assert.match(agentEvidenceRows(value)[0].action, /未能执行/);
  value.aiToolCalls[0].status = "no_result";
  assert.match(agentEvidenceRows(value)[0].action, /已执行/);
});
test("history is never represented as an added current source; UI fixtures are named", () => {
  const value = report(); value.aiToolCalls[0].tool = "get_previous_report_context";
  const row = agentEvidenceRows(value)[0];
  assert.equal(row.added, undefined); assert.match(row.action, /不作为本轮评级证据/);
  assert.match(reportModeLabel({ ...value, aiProvider: "mock-ui" }), /非真实模型/);
});
test("no consent, no evidence and budget skips are explicit program outcomes", () => {
  const value = report(); value.aiToolCalls = [];
  value.aiProcess.skippedReason = "consent_not_granted";
  assert.match(agentProcessSummary(value), /未调用模型/);
  value.aiProcess.skippedReason = "no_evidence";
  assert.match(agentProcessSummary(value), /程序跳过/);
  value.aiProcess.skippedReason = "usage_budget";
  assert.match(agentProcessSummary(value), /不是模型主动停止/);
});
