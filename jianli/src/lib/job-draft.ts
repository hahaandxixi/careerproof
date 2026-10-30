import type { RequirementInput } from "./api/domain";

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
  return !row.sourceQuote || (row.sourceStart!=null && row.sourceEnd!=null && description.slice(row.sourceStart,row.sourceEnd)===row.sourceQuote);
}
