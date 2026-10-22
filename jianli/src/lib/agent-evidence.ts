import type { MatchReport, ReportEvidence } from "./api/domain";

export function agentProcessSummary(report: MatchReport): string {
  if (report.aiFallbackUsed) return "模型调用或校验未完成，已保留规则结果；补检索记录不代表模型结论已采信。";
  if (report.aiProcess?.skippedReason === "consent_not_granted") return "未授权外部分析，本次未调用模型；下方仍可使用规则证据和补证入口。";
  if (report.aiProcess?.skippedReason === "no_evidence") return "没有可用的模型证据上下文，程序跳过外部分析；不代表材料中完全没有相关实现。";
  if (report.aiProcess?.skippedReason === "usage_budget") return "本次预算闸门未放行模型分析，保留规则结果；这不是模型主动停止。";
  if (report.aiProcess?.planningSkippedReason === "report_budget_reserved") return "程序为最终分析预留用量，停止额外工具规划；这不是模型主动选择停止。";
  if (report.aiToolCalls.some(call => call.status === "not_requested")) return "模型返回了不再调用工具的选择；是否已取得新证据，以逐条记录为准。";
  if (!report.aiToolCalls.length) return "本报告没有保存额外工具调用记录，不能据此认定模型主动停止或曾经补检索。";
  return "核对实际动作、补充原文与最终解释的引用关系；以下不是模型思考过程。";
}

export function agentEvidenceRows(report: MatchReport) {
  return report.aiToolCalls.map(call => {
    const item = report.items.find(item => item.requirementId === call.requirementId);
    const addedIds = new Set(report.aiToolCalls.filter(other => other.tool === "retrieve_more_evidence"
      && other.requirementId === call.requirementId && other.status === "completed"
      && other.resultCount === 1 && other.citationId).map(other => other.citationId));
    const added = call.tool === "retrieve_more_evidence" && call.status === "completed"
      && call.resultCount === 1 && call.citationId
      ? item?.evidenceList.find(evidence => evidence.citationId === call.citationId) : undefined;
    // Citation IDs establish a saved mapping, not the chronology or exact input
    // of an earlier physical request. Do not reconstruct an initial prompt here.
    const otherSaved: ReportEvidence[] = item?.evidenceList.filter(evidence => evidence.citationId && !addedIds.has(evidence.citationId)) ?? [];
    let action: string;
    if (call.tool === "get_previous_report_context") action = call.status === "completed"
      ? "读取了本人同岗位历史解释；历史不作为本轮评级证据。" : "历史读取不可用，继续使用当前证据。";
    else if (call.status === "not_requested") action = "模型选择不再调用工具。";
    else if (call.status === "rejected") action = "工具请求未通过边界校验，没有据此接受补充证据。";
    else if (call.status === "unavailable") action = "补检索未能执行，不能视为材料中没有证据。";
    else if (call.status === "no_result") action = "已执行补检索，没有返回新证据；不代表候选人没有能力。";
    else if (added) action = "按工具请求补检索，新增片段已保存，可与最终解释逐项核对。";
    else action = "保存的记录不足以定位新增片段，不能确认补充了什么。";
    const used = !!added && !report.aiFallbackUsed && item?.aiStatus === "validated"
      && !!item.aiCitationIds.includes(added.citationId ?? "");
    const influence = report.aiFallbackUsed ? "当前采用规则结果，不据工具成功声称AI结论发生变化。"
      : used ? "通过结构校验的最终解释引用了这条补充证据；这不等于评级提升或运行已经验证。"
      : added ? "新增片段已保存，但没有可确认已采用它的有效AI解释。"
      : "没有可对应的新增引用，不能声称补检索改变了结论。";
    return { call, item, added, otherSaved, action, used, influence };
  });
}
