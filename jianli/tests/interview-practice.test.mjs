import test from "node:test";
import assert from "node:assert/strict";
import {
  PRACTICE_DRAFT_PREFIX, canRetryFeedback, canSubmit, consentItems, draftKey, newClientToken, openTurn,
  feedbackStatusLabel, practiceStatusLabel, practiceTurnSources, selectedPracticeTurn, questionRetryNote, savedSubmission, summaryLine, tokenKey, turnLabel, turnNotice,
} from "../src/lib/interview-practice.ts";

const evidence = (id, path = "version-1/test_pipeline.py") => ({
  citationId: id, filePath: path, lineStart: 3, lineEnd: 4, snippet: "assert True", provenance: "portfolio",
});
const turn = (turnIndex, state, kind = "first") => ({
  turnIndex, kind, question: `question ${turnIndex}`, focus: "", state, answerText: null,
  answeredAt: null, failureReason: null, citations: [], knowledge: [], feedback: null,
});
const session = (overrides = {}) => ({
  id: "session-1", status: "in_progress", reportId: "report-1", requirementId: "req-1",
  requirementTitle: "编写可复现的 pytest 测试", skill: "pytest", jobTitle: "数据工程实习生",
  materials: [{ kind: "project", id: "version-1", title: "数据清洗脚本", versionNumber: 2, contentHash: "h" }],
  evidence: [evidence("R3-E1")], knowledge: [{ knowledgeId: "tech-pytest-assertion-specific", title: "断言要具体" }],
  consentAt: "2026-11-10T00:00:00Z", consentScope: "scope", currentTurn: 0, maxTurns: 2,
  summary: null, failureReason: null, createdAt: "", updatedAt: "", turns: [turn(0, "question")],
  ...overrides,
});

test("drafts and submit tokens are isolated per account and session", () => {
  assert.notEqual(draftKey("user-a", "session-1", 0), draftKey("user-b", "session-1", 0));
  assert.notEqual(draftKey("user-a", "session-1", 0), draftKey("user-a", "session-2", 0));
  assert.ok(draftKey("user-a", "session-1", 0).startsWith(PRACTICE_DRAFT_PREFIX));
  assert.notEqual(tokenKey("user-a", "session-1", 0), draftKey("user-a", "session-1", 0));
});

test("a fresh client token is unique and never a fixed constant", () => {
  const first = newClientToken();
  const second = newClientToken();
  assert.match(first, /^practice-/);
  assert.notEqual(first, second);
});

test("only the in-progress unanswered turn accepts a submission", () => {
  assert.equal(openTurn(session())?.turnIndex, 0);
  assert.equal(canSubmit(session(), openTurn(session())), true);
  assert.equal(canSubmit({ ...session(), knowledgeOutdated: true }, openTurn(session())), false);
  assert.equal(openTurn(session({ status: "completed" })), null);
  assert.equal(canSubmit(session(), turn(0, "feedback")), false);
  assert.equal(canSubmit(session(), turn(0, "answered")), false);
  assert.equal(canSubmit(session({ status: "draft" }), turn(0, "question")), false);
});

test("the consent list states the sent scope without exposing principles", () => {
  const items = consentItems(session());
  const joined = items.join("\n");
  assert.match(joined, /当前问题/);
  assert.match(joined, /你在本轮输入的回答/);
  assert.match(joined, /test_pipeline\.py/);
  assert.match(joined, /1 处/);
  assert.match(joined, /技术知识条目（1 条/);
  assert.doesNotMatch(joined, /参考要点|principle|答案/);
});

test("failed turns keep the saved answer and never claim a finished critique", () => {
  assert.match(turnNotice(turn(0, "failed")), /点评未生成/);
  assert.match(turnNotice({ ...turn(0, "failed"), failureReason: "模型响应超时，回答已保存，可稍后重试" }), /超时/);
  const legacy = turn(0, "answered");
  const pending = { ...legacy, feedbackTask: { status: "pending" } };
  assert.match(turnNotice(legacy), /尚未生成/);
  assert.equal(canRetryFeedback(legacy), true);
  assert.match(turnNotice(pending), /等待点评/);
  assert.equal(canRetryFeedback(pending), false);
  assert.match(turnNotice({ ...pending, feedbackTask: { status: "running" } }), /正在生成点评/);
  assert.equal(turnNotice(turn(0, "feedback")), "");
});

test("a delayed response can only clear the exact saved submission", () => {
  const result = session({ turns: [{ ...turn(0, "answered"), answerText: "原回答" }] });
  assert.ok(savedSubmission(result, 0, "原回答"));
  assert.ok(!savedSubmission(result, 0, "后来编辑的回答"));
  assert.ok(!savedSubmission(result, 1, "原回答"));
});

test("labels distinguish the first question from a follow-up and the summary caveat", () => {
  assert.equal(turnLabel(turn(0, "question")), "第 1 问");
  assert.equal(turnLabel(turn(1, "question", "follow_up")), "追问");
  assert.equal(practiceStatusLabel("draft"), "等待确认发送范围");
  assert.equal(practiceStatusLabel("completed"), "练习已完成");
  assert.match(summaryLine({ answeredTurns: 2, covered: [], inconsistent: [], remaining: [], nextStep: "", note: "" }), /不改变报告判断/);
  assert.equal(summaryLine(null), "");
});

test("a session that recorded consent but has no question offers a retry, not a blank page", () => {
  assert.equal(questionRetryNote(session()), "");
  assert.equal(questionRetryNote(session({ status: "draft", turns: [] })), "");
  assert.match(
    questionRetryNote(session({ turns: [], failureReason: "模型输出未通过校验，请重试" })),
    /未通过校验/,
  );
  assert.match(questionRetryNote(session({ turns: [], failureReason: null })), /首问还没有生成/);
});


test("round feedback status follows its saved task and feedback rather than the session status",()=>{
 const saved={...turn(1,"answered"),answerText:"原回答"};
 assert.equal(feedbackStatusLabel(saved),"点评尚未生成");
 assert.equal(feedbackStatusLabel({...saved,feedbackTask:{status:"pending"}}),"点评等待处理");
 assert.equal(feedbackStatusLabel({...saved,feedbackTask:{status:"running"}}),"正在生成点评");
 assert.equal(feedbackStatusLabel({...saved,feedbackTask:{status:"failed"}}),"点评未生成");
 assert.equal(feedbackStatusLabel({...saved,feedback:{covered:[]},feedbackTask:{status:"completed"}}),"点评已生成");
});

test("reading a historical turn leaves the unanswered turn and its draft identity unchanged", () => {
  const previous = turn(0, "feedback");
  const current = turn(1, "question", "follow_up");
  const practice = session({ turns: [previous, current], currentTurn: 1 });
  assert.equal(selectedPracticeTurn(practice, null), current);
  assert.equal(selectedPracticeTurn(practice, 0), previous);
  assert.equal(openTurn(practice), current);
  assert.equal(canSubmit(practice, selectedPracticeTurn(practice, 0)), false);
  assert.equal(selectedPracticeTurn(practice, 99), current);
});

test("saved feedback sources stay scoped to the selected turn, even if its citations are empty", () => {
  const firstFile = evidence("first");
  const citedFile = evidence("feedback", "version-2/service.py");
  const topic = { knowledgeId: "topic", title: "事务边界" };
  const first = { ...turn(0, "feedback"), feedback: { citations: [citedFile], knowledge: [] } };
  const followUp = { ...turn(1, "question", "follow_up"), citations: [firstFile], knowledge: [topic] };
  const practice = session({ turns: [first, followUp] });
  assert.deepEqual(practiceTurnSources(selectedPracticeTurn(practice, 0), practice), {
    kind: "feedback", citations: [citedFile], knowledge: [],
  });
  assert.deepEqual(practiceTurnSources(selectedPracticeTurn(practice, null), practice), {
    kind: "first-related", citations: [firstFile], knowledge: [topic],
  });
  assert.deepEqual(practiceTurnSources({ ...followUp, feedback: { citations: [], knowledge: [topic] } }, practice), {
    kind: "feedback", citations: [], knowledge: [topic],
  });
});

test("before the first question the confirmed scope can be reviewed from saved session material", () => {
  const practice = session({ status: "draft", turns: [] });
  assert.deepEqual(practiceTurnSources(selectedPracticeTurn(practice, null), practice), {
    kind: "session", citations: practice.evidence, knowledge: practice.knowledge,
  });
});
