import test from "node:test";
import assert from "node:assert/strict";
import { activeVerificationReplyReferences, appendVerificationReplyQuestion, verificationReplyBlock } from "../src/lib/verification-reply-draft.ts";

const question = { requirementId: "requirement-1", requirementIndex: 0, requirementTitle: "异常处理", question: "请说明由你实现的重试逻辑，并提供可复现步骤。", citationIds: ["E2", "E2", "E4"] };

test("AI verification question becomes an editable, source-labeled human reply draft", () => {
  const first = appendVerificationReplyQuestion("您好，请补充以下材料：", question);
  assert.equal(first.status, "added");
  assert.match(first.text, /【第1项：异常处理】/);
  assert.match(first.text, /报告引用编号：E2、E4/);
  assert.match(first.text, /引用不自动证明能力/);
  assert.equal(appendVerificationReplyQuestion(first.text, question).status, "duplicate");
});

test("empty citation list asks for verifiable material without implying report support", () => {
  const block = verificationReplyBlock({ ...question, citationIds: [] });
  assert.match(block, /暂无支持引用/);
  assert.doesNotMatch(block, /报告引用编号/);
});

test("overlong draft is left untouched so a question cannot silently truncate a manual reply", () => {
  const original = "x".repeat(1990);
  assert.deepEqual(appendVerificationReplyQuestion(original, question), { text: original, status: "too_long" });
});

test("direct report links follow edited reply text and deduplicate each requirement", () => {
  const first = appendVerificationReplyQuestion("", question).text;
  const secondQuestion = { ...question, question: "请演示异常路径。" };
  const draft = appendVerificationReplyQuestion(first, secondQuestion).text;
  assert.deepEqual(activeVerificationReplyReferences(draft, [question, secondQuestion]), [
    { requirementId: "requirement-1", citationIds: ["E2", "E4"] },
  ]);
  assert.deepEqual(activeVerificationReplyReferences(draft.replaceAll("E4", "已移除编号"), [question]), [
    { requirementId: "requirement-1", citationIds: ["E2"] },
  ]);
  assert.deepEqual(activeVerificationReplyReferences(draft.replaceAll("【第1项：异常处理】", "异常处理"), [question]), []);
});

test("equal requirement titles remain distinct when one edited block is removed", () => {
  const other = { ...question, requirementId: "requirement-2", requirementIndex: 1, citationIds: ["E20"] };
  const first = verificationReplyBlock(question);
  const second = verificationReplyBlock(other);
  assert.deepEqual(activeVerificationReplyReferences(first + "\n\n" + second, [question, other]), [
    { requirementId: "requirement-1", citationIds: ["E2", "E4"] },
    { requirementId: "requirement-2", citationIds: ["E20"] },
  ]);
  assert.deepEqual(activeVerificationReplyReferences(first, [question, other]), [
    { requirementId: "requirement-1", citationIds: ["E2", "E4"] },
  ]);
  assert.deepEqual(activeVerificationReplyReferences(first + "\n\n【第2项：异常处理】\n无引用", [question, other]), [
    { requirementId: "requirement-1", citationIds: ["E2", "E4"] },
    { requirementId: "requirement-2", citationIds: [] },
  ]);
});

test("bracketed requirement titles retain their own report references", () => {
  const first = { ...question, requirementTitle: "【核心】Java后端", citationIds: ["R1-E1"] };
  const second = { ...question, requirementId: "requirement-2", requirementIndex: 1, requirementTitle: "测试", citationIds: ["R2-E1"] };
  const draft = `${verificationReplyBlock(first)}\n\n${verificationReplyBlock(second)}`;
  assert.deepEqual(activeVerificationReplyReferences(draft, [first, second]), [
    { requirementId: "requirement-1", citationIds: ["R1-E1"] },
    { requirementId: "requirement-2", citationIds: ["R2-E1"] },
  ]);
});

test("an edited longer citation identifier cannot keep a shorter direct link", () => {
  const input = { ...question, citationIds: ["R1-E1"] };
  const draft = verificationReplyBlock(input);
  assert.deepEqual(activeVerificationReplyReferences(draft.replace("R1-E1", "R1-E10"), [input]), [
    { requirementId: "requirement-1", citationIds: [] },
  ]);
  assert.deepEqual(activeVerificationReplyReferences(draft.replace("R1-E1", "prefix-R1-E1"), [input]), [
    { requirementId: "requirement-1", citationIds: [] },
  ]);
  assert.deepEqual(activeVerificationReplyReferences(draft, [input]), [
    { requirementId: "requirement-1", citationIds: ["R1-E1"] },
  ]);
});
