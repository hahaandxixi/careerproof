import { test } from "node:test";
import assert from "node:assert/strict";
import {
  isRuleCountSummary,
  reportAiRatedCount,
  reportModeLabel,
  reportSummaryText,
} from "../src/lib/report-display.ts";

test("only the complete generated count summary is redundant in a fixed report", () => {
  const counts = "共3项岗位要求，其中1项有项目证据支撑，2项仅有简历声明，0项当前无法确认，0项暂不支持评估且不计分。分数为材料支持度，不是能力或录用结论。";
  assert.equal(isRuleCountSummary(counts), true);
  assert.equal(isRuleCountSummary(counts + "本次来源缺少第 19 行后文。"), false);
});

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
