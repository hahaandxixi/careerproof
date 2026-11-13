import type { CareerPlanResult, JobRecommendation } from "./api/domain.ts";
import { demoJobAlias, displayJobTitle, displayMaterialTitle } from "./demo-display-identity.js";

/** Display projection only: preserve saved IDs, versions, evidence and model text. */
export function careerPlanDisplayIdentity(result: CareerPlanResult): CareerPlanResult {
  return {
    ...result,
    materials: result.materials.map(material => ({
      ...material, title: displayMaterialTitle(material.title, material.id),
    })),
    recommendations: result.recommendations.map(job => ({
      ...job, jobTitle: displayJobTitle(job.jobTitle, job.jobId),
      companyName: demoJobAlias(job.jobId)?.companyName ?? job.companyName,
    })),
    changes: result.changes.map(change => ({
      ...change, jobTitle: displayJobTitle(change.jobTitle, change.jobId),
    })),
  };
}

export function careerPlanConfigurationBlocked(status: string): boolean {
  return ["external_ai_disabled", "mock_provider", "model_configuration_error", "model_auth_error", "model_request_rejected", "model_quota_exceeded"].includes(status);
}

export function careerPlanFailureMessage(status: string): string {
  const messages: Record<string, string> = {
    external_ai_disabled: "当前环境未启用外部 AI，本次没有调用模型。",
    mock_provider: "当前环境使用模拟模型，无法生成真实 AI 建议。",
    model_configuration_error: "当前 AI 服务配置不可用，尚未调用模型；请联系维护者核对配置。",
    model_auth_error: "AI 服务未通过身份验证，请联系维护者核对配置。",
    model_timeout: "AI 请求超时，稍后可主动重试。",
    model_network_error: "暂时无法连接 AI 服务，请稍后重试。",
    model_rate_limited: "AI 服务请求受限，请稍后重试。",
    model_quota_exceeded: "AI 服务额度不足，请联系维护者核对额度。",
    model_request_rejected: "AI 服务拒绝了本次请求，请联系维护者核对请求配置。",
    model_http_error: "AI 服务暂时返回错误，请稍后重试。",
    model_request_budget: "本次请求超出允许的输入或输出预算，未发送模型请求。",
    daily_report_limit: "今日 AI 规划次数已达上限，未调用模型。",
    daily_input_token_limit: "今日 AI 输入额度不足，未调用模型。",
    daily_output_token_limit: "今日 AI 输出额度不足，未调用模型。",
    usage_budget: "当前 AI 使用额度不足，未调用模型。",
    model_output_truncated: "模型输出达到长度上限，规划未完整返回。",
    model_json_invalid: "模型未返回可读取的 JSON 规划。",
    model_output_schema_invalid: "模型规划缺少必要字段或结构不符合要求。",
    saved_plan_needs_recheck: "这份历史规划的 AI 建议暂不可用，可继续核对已保存的岗位与材料。",
  };
  if (messages[status]) return messages[status];
  if (["change_attribution_conflict", "change_fact_conflict", "task_plan_evidence_gap_conflict", "visible_code_fact_conflict", "model_business_validation_failed"].includes(status)) {
    return "本次 AI 建议暂不可用，可继续核对下方岗位与材料。";
  }
  return "本次未生成可用的 AI 规划。";
}

export function careerPlanRecommendations(
  result: Pick<CareerPlanResult, "recommendations" | "aiPlan" | "aiValidationIssues">,
  expanded: boolean,
): JobRecommendation[] {
  if (expanded) return result.recommendations;
  const comparedIds = new Set(result.aiPlan?.advice.map(advice => advice.jobId) ?? []);
  if (result.aiPlan?.focusJobId) comparedIds.add(result.aiPlan.focusJobId);
  const hasComparedCandidate = result.recommendations.some(item => comparedIds.has(item.jobId));
  if (!hasComparedCandidate) result.recommendations.slice(0, 3).forEach(item => comparedIds.add(item.jobId));
  // Rejected outputs still need their current evidence visible for inspection.
  const diagnosticIds = new Set(
    result.aiValidationIssues?.flatMap(issue => issue.citationIds) ?? [],
  );
  const relevant = result.recommendations.filter(item =>
    comparedIds.has(item.jobId)
    || item.evidence.some(evidence => evidence.citationId && diagnosticIds.has(evidence.citationId)),
  );
  return relevant;
}

export function visibleCareerChanges(
  changes: CareerPlanResult["changes"], visibleRecommendations: JobRecommendation[],
): CareerPlanResult["changes"] {
  const visibleJobIds = new Set(visibleRecommendations.map(item => item.jobId));
  return changes.filter(change => change.status === "not_in_current" || visibleJobIds.has(change.jobId));
}
