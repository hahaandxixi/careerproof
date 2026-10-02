import { test } from "node:test";
import assert from "node:assert/strict";
import { adoptGrowthAdvice, sourceContextVerified, taskUsedExternalAI, validatedGrowthAdvice } from "../src/lib/analysis-status.ts";

test("DeepSeek task steps are shown as successful AI analysis", () => {
  assert.equal(taskUsedExternalAI("deepseek", false), true);
  assert.equal(taskUsedExternalAI("deepseek", undefined), true);
});

test("fallback and local-only steps are not presented as successful AI", () => {
  assert.equal(taskUsedExternalAI("deepseek", true), false);
  assert.equal(taskUsedExternalAI("rules", false), false);
  assert.equal(taskUsedExternalAI(undefined, false), false);
});

test("current source-verified reports are not labeled as unverified history", () => {
  assert.equal(sourceContextVerified("source-context-v2"), true);
  assert.equal(sourceContextVerified("source-context-v4-semantic-documents"), true);
  assert.equal(sourceContextVerified("source-context-v1"), false);
  assert.equal(sourceContextVerified(null), false);
});

function adviceCase() {
  return {
    report: { evidenceContextVersion: "source-context-v25-explicit-citation-policy" },
    item: {
      aiStatus: "validated", confirmationStatus: "pending", verdict: "partial",
      aiSuggestion: " 提交具名查询脚本并核对运行记录。 ",
      aiInformationGap: "运行结果尚待核验", evidenceLevelGap: "补充运行记录",
      aiCitationIds: ["R1-E1"], evidenceList: [{ citationId: "R1-E1" }],
    },
  };
}

test("validated current AI suggestion becomes an editable draft with same-item citation", () => {
  const { report, item } = adviceCase();
  assert.deepEqual(validatedGrowthAdvice(report, item), {
    suggestion: "提交具名查询脚本并核对运行记录。",
    gap: "运行结果尚待核验", citationIds: ["R1-E1"], suggestedKind: "execution",
    taskPlan: null,
  });
  assert.equal(item.aiSuggestion, " 提交具名查询脚本并核对运行记录。 ");
});

test("draft type favors missing execution, then contribution, while staying editable", () => {
  const { report, item } = adviceCase();
  item.aiInformationGap = "缺少本人贡献记录";
  assert.equal(validatedGrowthAdvice(report, item).suggestedKind, "contribution");
  item.aiInformationGap = "缺少可定位实现";
  assert.equal(validatedGrowthAdvice(report, item).suggestedKind, "implementation");
  item.aiInformationGap = "当前材料未展示任何 Redis 客户端调用、缓存读写实现或相关运行记录。";
  assert.equal(validatedGrowthAdvice(report, item).suggestedKind, "implementation");
});

test("validated structured AI task draft carries editable steps and checks", () => {
  const { report, item } = adviceCase();
  item.aiTaskPlan = {
    deliverable: " 具名接口运行记录 ",
    steps: [" 运行合成接口 ", "保存脱敏响应"],
    acceptanceChecks: ["请求与响应可定位"],
  };
  assert.deepEqual(validatedGrowthAdvice(report, item).taskPlan, {
    deliverable: "具名接口运行记录",
    steps: ["运行合成接口", "保存脱敏响应"],
    acceptanceChecks: ["请求与响应可定位"],
  });
  item.aiTaskPlan.acceptanceChecks = [];
  assert.equal(validatedGrowthAdvice(report, item).taskPlan, null);
  assert.equal(item.aiTaskPlan.deliverable, " 具名接口运行记录 ");
});

test("saved task-plan warning keeps advice but blocks unsafe draft adoption", () => {
  const { report, item } = adviceCase();
  item.aiTaskPlan = {
    deliverable: "具名接口运行记录", steps: ["再次提交该函数源码"],
    acceptanceChecks: ["输出可定位"],
  };
  item.aiTaskPlanWarning = "AI任务草稿重复要求提交已完整展示的源码，请重新核对。";
  const advice = validatedGrowthAdvice(report, item);
  assert.equal(advice.suggestion, "提交具名查询脚本并核对运行记录。");
  assert.equal(advice.taskPlan, null);
});

test("historical, failed, reviewed, or incorrectly cited advice cannot prefill a task", () => {
  const variants = [
    ({ report }) => { report.evidenceContextVersion = "source-context-v1"; },
    ({ item }) => { item.aiStatus = "invalid_output"; },
    ({ item }) => { item.aiSuggestionRedundant = true; },
    ({ item }) => { item.confirmationStatus = "rejected"; },
    ({ item }) => { item.confirmationStatus = "corrected"; },
    ({ item }) => { item.aiCitationIds = ["R2-E1"]; },
    ({ item }) => { item.aiCitationIds = ["R1-E1", "R1-E1"]; },
    ({ item }) => { item.aiCitationIds = []; },
    ({ item }) => { item.aiSuggestion = " "; },
  ];
  for (const alter of variants) {
    const value = adviceCase(); alter(value);
    assert.equal(validatedGrowthAdvice(value.report, value.item), null);
  }
});

test("AI draft fills blanks after a student writes the deliverable without replacing their plan", () => {
  const { report, item } = adviceCase();
  item.aiTaskPlan = {
    deliverable: "AI交付物", steps: ["记录合成请求", "保存响应"],
    acceptanceChecks: ["命令与响应可定位"],
  };
  const advice = validatedGrowthAdvice(report, item);
  const current = { kind: "contribution", kindEdited: true, deliverable: " 我的交付物 ", steps: "本人手写步骤", checks: " " };
  assert.deepEqual(adoptGrowthAdvice(current, advice), {
    ...current, checks: "命令与响应可定位",
  });
  assert.equal(current.checks, " ");
  assert.deepEqual(adoptGrowthAdvice({ ...current, kindEdited: false, steps: "" }, advice), {
    ...current, kindEdited: false, kind: "execution", steps: "记录合成请求\n保存响应", checks: "命令与响应可定位",
  });
});

test("legacy advice only fills a blank deliverable and leaves hand-written checks intact", () => {
  const { report, item } = adviceCase();
  const advice = validatedGrowthAdvice(report, item);
  const current = { kind: "review", kindEdited: true, deliverable: "", steps: "手写步骤", checks: "手写核验条件" };
  assert.deepEqual(adoptGrowthAdvice(current, advice), { ...current, deliverable: advice.suggestion });
});
