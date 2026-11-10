import { test } from "node:test";
import assert from "node:assert/strict";
import {
  reportAiRatedCount,
  reportModeLabel,
  reportSummaryText,
} from "../src/lib/report-display.ts";

const item = source => ({ evidenceLevelSource: source });
const report = (analysisMode, aiFallbackUsed, items) => ({ analysisMode, aiFallbackUsed, items });

test("non-AI and fallback reports render no analysis badge while validated AI keeps a short one", () => {
  assert.equal(reportModeLabel(report("rules", false, [item("rules")])), "");
  assert.equal(reportModeLabel(report("ai_evidence", true, [item("ai_preliminary")])), "");
  assert.equal(reportModeLabel(report("ai_evidence", false, [item("rules")])), "");
  assert.equal(reportModeLabel(report("ai_evidence", false, [item("ai_preliminary"), item("rules")])), "AI 分析");
  assert.equal(reportModeLabel({...report("ai_evidence", false, [item("rules")]), aiProvider:"mock"}), "演示结果");
  assert.equal(reportModeLabel(report("unknown_future_mode", false, [item("rules")])), "");
  assert.equal(reportAiRatedCount(report("ai_evidence", false, [item("ai_preliminary"), item("rules")])), 1);
});

test("historical summary wording is normalized for display without changing facts", () => {
  const old = "分数为材料支持度，不是能力或录用结论。0项暂不支持评估且不计分。";
  assert.equal(reportSummaryText(old), "评级描述材料证据，不是能力或录用结论。0项暂不支持评估且不评级。");
  const current = "评级描述材料证据，不是能力或录用结论。0项暂不支持评估且不评级。";
  assert.equal(reportSummaryText(current), current);
  assert.equal(reportSummaryText("不含旧措辞的摘要"), "不含旧措辞的摘要");
});
