export interface VerificationReplyQuestion {
  requirementId: string;
  requirementIndex: number;
  requirementTitle: string;
  question: string;
  citationIds: string[];
}

export interface ReplyReference {
  requirementId: string;
  citationIds: string[];
}

function verificationReplyMarker(input: VerificationReplyQuestion): string {
  const title = input.requirementTitle.trim() || "岗位要求";
  return "【第" + (input.requirementIndex + 1) + "项：" + title + "】";
}

export function verificationReplyBlock(input: VerificationReplyQuestion): string {
  const marker = verificationReplyMarker(input);
  const question = input.question.trim();
  const citations = [...new Set(input.citationIds.map(id => id.trim()).filter(Boolean))];
  return `${marker}\n${question}${citations.length ? `\n报告引用编号：${citations.join("、")}（请核对原文；引用不自动证明能力）` : "\n本项暂无支持引用，请说明可核验的本人材料。"}`;
}

export function appendVerificationReplyQuestion(existing: string, input: VerificationReplyQuestion, maxLength = 2000): {
  text: string; status: "added" | "duplicate" | "too_long";
} {
  const block = verificationReplyBlock(input);
  if (existing.includes(block)) return { text: existing, status: "duplicate" };
  const text = `${existing.trimEnd()}${existing.trim() ? "\n\n" : ""}${block}`;
  if (text.length > maxLength) return { text: existing, status: "too_long" };
  return { text, status: "added" };
}

function hasCitationId(text: string, citationId: string): boolean {
  const escaped = citationId.replace(/[.*+?^\${}()|[\]\\]/g, "\\$&");
  return new RegExp("(^|[^A-Za-z0-9_-])" + escaped + "(?![A-Za-z0-9_-])").test(text);
}

function replyBlocks(text: string, marker: string): string[] {
  const markers = [...text.matchAll(/^(【第[1-9]\d*项：[^\r\n]+】)[ \t]*\r?$/gm)];
  return markers.flatMap((match, index) => match[1] === marker
    ? [text.slice((match.index ?? 0) + match[0].length, markers[index + 1]?.index ?? text.length)]
    : []);
}

// A removed requirement marker or citation must not leave behind a misleading
// direct link after the enterprise edits its message.
export function activeVerificationReplyReferences(text: string, questions: VerificationReplyQuestion[]): ReplyReference[] {
  const grouped = new Map<string, Set<string>>();
  for (const question of questions) {
    const blocks = replyBlocks(text, verificationReplyMarker(question));
    if (!blocks.length) continue;
    const citations = grouped.get(question.requirementId) ?? new Set<string>();
    for (const id of question.citationIds) if (blocks.some(block => hasCitationId(block, id))) citations.add(id);
    grouped.set(question.requirementId, citations);
  }
  return [...grouped].map(([requirementId, citationIds]) => ({ requirementId, citationIds: [...citationIds] }));
}
