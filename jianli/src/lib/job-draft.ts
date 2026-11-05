import type { JobDraftResult, RequirementInput } from "./api/domain";

export function createDraftRequestGuard() {
  let request = 0, revision = 0;
  return {
    start: () => ({request: ++request, revision}),
    sourceChanged: () => { revision++; },
    invalidate: () => { request++; revision++; },
    isLatest: (ticket: {request:number}) => ticket.request === request,
    accepts: (ticket: {request:number;revision:number}) => ticket.request === request && ticket.revision === revision,
  };
}

export function combineDraftRequirements(current: RequirementInput[], selected: RequirementInput[], mode: "append" | "replace") {
  if (!selected.length || selected.some(r=>!r.rawText.trim()||!r.skillName.trim())) throw Error("请填写选中草稿的要求说明和技能名称。");
  const rows = mode === "replace" ? selected : [...current.filter(r=>r.rawText.trim()||r.skillName.trim()), ...selected];
  if (rows.length>50) throw Error("岗位要求最多50条，请减少选中数量或先移除现有要求。");
  return rows.map(row=>({...row}));
}

export function quoteStillMatches(description: string, row: RequirementInput) {
  if (row.sourceQuote == null) return row.sourceStart == null && row.sourceEnd == null;
  const range = sourceSelectionRange(description, row.sourceStart, row.sourceEnd);
  return !!row.sourceQuote && range !== null && description.slice(...range) === row.sourceQuote;
}

// API offsets are Unicode code points; textarea selection offsets are UTF-16.
export function sourceSelectionRange(description: string, start: number | null | undefined,
  end: number | null | undefined): [number, number] | null {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start! < 0 || end! <= start!) return null;
  const points = Array.from(description);
  if (end! > points.length) return null;
  return [points.slice(0, start!).join("").length, points.slice(0, end!).join("").length];
}

export function currentDraftSource(guard: ReturnType<typeof createDraftRequestGuard>,
  ticket: {request:number;revision:number}, result: JobDraftResult): string | null {
  if (!guard.accepts(ticket)) return null;
  const source = result.normalizedDescription;
  // Never approximate the server's whitespace rules or rewrite historical references.
  if (typeof source !== "string" || !source || result.requirements.some(row => !quoteStillMatches(source,row))) {
    throw Error("草稿未返回可核对的岗位原文，请重新提取或手动填写要求。");
  }
  return source;
}
