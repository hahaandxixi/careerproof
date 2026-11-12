import type { InterviewSession, PracticeGeneration, PracticeTurn } from "./api/domain.ts";

export const PRACTICE_DRAFT_PREFIX = "careerproof.interview.draft";
export const PRACTICE_TOKEN_PREFIX = "careerproof.interview.token";

/** Drafts are scoped to one account and one session, so switching accounts never
 * restores someone else's unsent answer. */
export function draftKey(userId: string, sessionId: string, turnIndex: number) {
  return `${PRACTICE_DRAFT_PREFIX}.${userId}.${sessionId}.${turnIndex}`;
}

export function tokenKey(userId: string, sessionId: string, turnIndex: number) {
  return `${PRACTICE_TOKEN_PREFIX}.${userId}.${sessionId}.${turnIndex}`;
}

export function newClientToken(): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `practice-${random}`;
}

export function practiceStatusLabel(status: InterviewSession["status"] | undefined) {
  if (status === "draft") return "等待确认发送范围";
  if (status === "completed") return "练习已完成";
  if (status === "in_progress") return "练习进行中";
  return "正在加载";
}

export function turnLabel(turn: Pick<PracticeTurn, "kind" | "turnIndex">) {
  return turn.kind === "follow_up" ? "追问" : `第 ${turn.turnIndex + 1} 问`;
}

export function openTurn(session: InterviewSession | null): PracticeTurn | null {
  if (!session || session.status !== "in_progress") return null;
  return session.turns.find(turn => turn.state === "question") ?? null;
}

export function selectedPracticeTurn(session: InterviewSession, selectedIndex: number | null) {
  return session.turns.find(turn => turn.turnIndex === selectedIndex) ?? openTurn(session) ?? session.turns.at(-1) ?? null;
}

export function practiceTurnSources(turn: PracticeTurn | null, session: Pick<InterviewSession, "evidence" | "knowledge">) {
  if (!turn) {
    return { kind: "session", citations: session.evidence, knowledge: session.knowledge } as const;
  }
  if (turn.feedback) {
    return { kind: "feedback", citations: turn.feedback.citations, knowledge: turn.feedback.knowledge } as const;
  }
  return {
    kind: turn.kind === "follow_up" ? "first-related" : "question",
    citations: turn.citations,
    knowledge: turn.knowledge,
  } as const;
}

export function canSubmit(session: InterviewSession | null, turn: PracticeTurn | null) {
  return !!session && !!turn && session.status === "in_progress" && turn.state === "question" && !session.knowledgeOutdated;
}

export function consentItems(session: InterviewSession): string[] {
  const files = Array.from(new Set(session.evidence.map(item => item.filePath.split("/").pop() || item.filePath)));
  const items = ["当前问题", "你在本轮输入的回答", "点评所需的前轮问答与待核对项"];
  items.push(files.length ? `相关材料片段（${files.join("、")}，共 ${session.evidence.length} 处）` : "当前要求的岗位原文与技术知识条目");
  items.push(`技术知识条目（${session.knowledge.length} 条标题与原理）`);
  return items;
}

/** Saved state decides what is shown; an unknown network result never re-asks. */
export function turnNotice(turn: PracticeTurn) {
  if (turn.state === "failed") return turn.failureReason || "点评未生成，回答已保存";
  if (turn.state === "answered") {
    if (!turn.feedbackTask) return "回答已保存，点评尚未生成";
    return turn.feedbackTask.status === "running" ? "回答已保存，正在生成点评" : "回答已保存，等待点评";
  }
  return "";
}

export function feedbackStatusLabel(turn: PracticeTurn) {
  if (turn.feedback) return "点评已生成";
  if (generationPending(turn.feedbackTask)) return turn.feedbackTask?.status === "running" ? "正在生成点评" : "点评等待处理";
  if (turn.state === "failed" || turn.feedbackTask?.status === "failed") return "点评未生成";
  return turn.state === "question" ? "待点评" : "点评尚未生成";
}

export function canRetryFeedback(turn: PracticeTurn) {
  return turn.state === "failed" || (turn.state === "answered" && !turn.feedbackTask);
}

/** Consent was recorded but no question was saved (model failure): the page must offer a
 * retry for the first question instead of showing an empty practice. */
export function questionRetryNote(session: InterviewSession) {
  if (session.status === "draft" || session.turns.length || generationPending(session.questionTask)) return "";
  return session.failureReason || "首问还没有生成，可以重新生成。";
}

export function summaryLine(summary: InterviewSession["summary"]) {
  if (!summary) return "";
  return `本次共完成 ${summary.answeredTurns} 轮回答；小结不改变报告判断、技能等级与投递快照。`;
}


export function visibleSummaryNextStep(summary: InterviewSession["summary"], turn: PracticeTurn | null) {
  const nextStep = summary?.nextStep;
  const normalize = (value?: string) => value?.trim().replace(/\s+/g, " ");
  return normalize(nextStep) !== normalize(turn?.feedback?.reviewSuggestion) ? nextStep || "" : "";
}

export function generationPending(task?: PracticeGeneration | null) {
  return task?.status === "pending" || task?.status === "running";
}

export function savedSubmission(session: InterviewSession | null, turnIndex: number, answer: string) {
  const turn = session?.turns.find(item => item.turnIndex === turnIndex);
  return turn?.answerText === answer ? turn : null;
}
