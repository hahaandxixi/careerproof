// Rules for the analysis-task progress display. These are the pure decisions TaskView
// uses, so a regression here shows up without a browser: a fabricated tick, an invented
// duration, or a connection message the data cannot support.

import test from "node:test";
import assert from "node:assert/strict";
import {
  completionCount,
  connectionLabel,
  formatSeconds,
  isCompletedRecord,
  modelStepQualifier,
  realDurationSeconds,
  stageText,
  taskModeLabel,
} from "../src/lib/process-trace.ts";

const step = (eventType, name = "步骤") => ({ eventType, name });

test("only recorded completion events are ticked; unavailable is not a completion", () => {
  for (const eventType of ["tool.completed", "task.completed", "verification.completed"]) {
    assert.equal(isCompletedRecord(eventType), true, eventType);
  }
  for (const eventType of ["verification.unavailable", "tool.started", "task.failed", ""]) {
    assert.equal(isCompletedRecord(eventType), false, eventType);
  }
});

test("completion count reflects only completion records, never the step total", () => {
  const steps = [
    step("tool.completed"),
    step("tool.completed"),
    step("verification.unavailable"),
    step("task.completed"),
  ];
  assert.equal(steps.length, 4);
  assert.equal(completionCount(steps), 3);
  assert.equal(completionCount([]), 0);
});

test("duration appears only when both real timestamps exist and are ordered", () => {
  const start = "2026-10-17T01:00:00Z";
  const end = "2026-10-17T01:00:12.500Z";
  assert.equal(realDurationSeconds(start, end), 12.5);
  // Missing either side: no duration instead of a guess.
  assert.equal(realDurationSeconds(start, null), null);
  assert.equal(realDurationSeconds(null, end), null);
  assert.equal(realDurationSeconds(undefined, undefined), null);
  // Unparseable or reversed timestamps are not trusted.
  assert.equal(realDurationSeconds("not-a-date", end), null);
  assert.equal(realDurationSeconds(end, start), null);
  assert.equal(realDurationSeconds(start, start), 0);
});

test("seconds are rounded to one decimal and labelled", () => {
  assert.equal(formatSeconds(12.34), "12.3 秒");
  assert.equal(formatSeconds(12.35), "12.4 秒");
  assert.equal(formatSeconds(0), "0 秒");
});

test("degraded, AI-assisted and rules-only modes stay distinct", () => {
  assert.equal(taskModeLabel({ usedAI: true, fellBack: true }), "模型已降级，本次为规则结果");
  assert.equal(taskModeLabel({ usedAI: true, fellBack: false }), "AI 解释已参与");
  assert.equal(taskModeLabel({ usedAI: false, fellBack: false }), "规则模式（未使用外部 AI）");
});

test("a missing model record is pending or unknown, never a fabricated rules result", () => {
  assert.equal(taskModeLabel({ usedAI: false, fellBack: false, active: true, modelRecorded: false }), "处理中，外部 AI 调用结果待确认");
  assert.equal(taskModeLabel({ usedAI: false, fellBack: false, active: false, modelRecorded: false }), "未记录模型处理结果");
  assert.equal(taskModeLabel({ usedAI: false, fellBack: false, active: true, modelRecorded: true }), "规则模式（未使用外部 AI）");
});

test("production step events and their tick decision", () => {
  // Derived from the four generation sites, not from the string shape alone.
  const production = [
    { site: "match_agent.py:41/48/58", name: "解析简历/扫描项目/可追溯匹配", eventType: "tool.completed", tick: true },
    { site: "match_agent.py:86", name: "生成结论", eventType: "task.completed", tick: true },
    { site: "analysis.py:1175", name: "任务各阶段（含模型证据分析、检索步骤）", eventType: "tool.completed", tick: true },
    { site: "application_verification.py:746", name: "核验成功", eventType: "verification.completed", tick: true },
    { site: "application_verification.py:748", name: "核验未成功", eventType: "verification.unavailable", tick: false },
  ];
  for (const entry of production) {
    assert.equal(isCompletedRecord(entry.eventType), entry.tick, `${entry.site} ${entry.name}`);
  }
  // A tick means "this stage finished", not "the model succeeded": that distinction is
  // carried by the qualifier below, not by withholding the tick.
  assert.equal(isCompletedRecord("tool.completed"), true);
  assert.equal(modelStepQualifier({ fallbackUsed: true }), "模型已降级");
});

test("connection wording distinguishes unsupported, never-opened and interrupted", () => {
  assert.equal(connectionLabel("live", true, true), "实时更新中");
  // Reconnect succeeded: the label must stop saying the connection is interrupted.
  assert.equal(connectionLabel("live", true, true), "实时更新中");
  // No EventSource in the environment: this is not a "disconnected" stream.
  assert.equal(connectionLabel("polling", false, false), "当前环境不支持实时推送，已改为定时刷新");
  // Stream dropped after it had opened.
  assert.equal(connectionLabel("polling", true, true), "实时连接已中断，正在定时刷新");
  // Fetch/first-connect failure before any onopen: must not claim an interruption.
  assert.equal(connectionLabel("polling", true, false), "实时进度暂未建立，正在定时刷新");
  assert.equal(connectionLabel("polling", null, false), "实时进度暂未建立，正在定时刷新");
  assert.equal(connectionLabel("connecting", null, false), "正在连接实时进度");
  assert.equal(connectionLabel("idle", true, true), "任务已结束，状态不再变化");
});

test("model steps name a skipped or degraded model instead of implying AI success", () => {
  // tool.completed is recorded for the model step even when no model ran.
  assert.equal(modelStepQualifier({ skippedReason: "external_ai_not_consented" }), "未调用模型");
  assert.equal(modelStepQualifier({ skippedReason: "daily_report_limit" }), "未调用模型");
  assert.equal(modelStepQualifier({ skippedReason: "   " }), null);
  assert.equal(modelStepQualifier({ fallbackUsed: true }), "模型已降级");
  // A normal model run and non-model payloads carry no qualifier.
  assert.equal(modelStepQualifier({ fallbackUsed: false }), null);
  assert.equal(modelStepQualifier({}), null);
  assert.equal(modelStepQualifier(null), null);
  assert.equal(modelStepQualifier(undefined), null);
  // skippedReason wins over fallbackUsed when both are present.
  assert.equal(modelStepQualifier({ skippedReason: "budget", fallbackUsed: true }), "未调用模型");
});

test("stage text uses the recorded step, and neutral wording when there is none", () => {
  assert.equal(stageText("正在解析简历", true), "正在解析简历");
  assert.equal(stageText("正在解析简历", false), "正在解析简历");
  // Blank or missing step never becomes a fake stage during an active run.
  assert.equal(stageText("", true), "正在准备处理");
  assert.equal(stageText("   ", true), "正在准备处理");
  assert.equal(stageText(null, true), "正在准备处理");
  // A finished task with no recorded stage says so instead of implying work in progress.
  assert.equal(stageText(null, false), "本次任务没有记录当前阶段");
});
