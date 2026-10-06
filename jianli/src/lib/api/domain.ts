export interface Page<T> { items: T[]; total: number; page: number; pageSize: number }
export interface Option { value: string; label: string }
export interface JobOptions { categories: Option[]; employmentTypes: Option[]; skills: { name: string; category: string }[] }
export interface Enterprise { id: string; name: string; description: string; isVerified: boolean; role: string }
export interface RequirementInput { rawText: string; skillName: string; weight: number; isRequired: boolean;
  sourceQuote?: string | null; sourceStart?: number | null; sourceEnd?: number | null }
export interface JobDraftRequirement extends RequirementInput {
  sourceQuote: string; sourceStart: number; sourceEnd: number;
  evidenceRequest?: string; verificationQuestion?: string; weightReason?: string;
}
export interface JobDraftResult {
  requirements: JobDraftRequirement[]; model: string; usage: { input_tokens?: number; output_tokens?: number } | null;
  confirmed: boolean;
}
export interface JobRequirement extends RequirementInput { id: string; skillId: string | null; normalizedStatus: string }
export interface JobSummary {
  id: string; title: string; companyName: string; description: string; status: string;
  category: string; city: string; employmentType: string; requirementCount: number; createdAt: string;
}
export interface JobDetail extends JobSummary { enterpriseId: string | null; createdBy: string; requirements: JobRequirement[] }
export interface JobInput {
  title: string; companyName: string; description: string; enterpriseId: string;
  category: string; city: string; employmentType: string; status: string; requirements: RequirementInput[];
}
export interface ResumePreview { id: string; status: string; sections: { id: string; sectionType: string; content: string; pageNumber: number | null }[] }
export interface ProjectFileSummary { id: string; relativePath: string; language: string; sizeBytes: number; lineCount: number }
export interface ProjectFileContent { id: string; relativePath: string; content: string; projectVersionId: string }
export interface ReportSummary {
  id: string; jobId: string; jobTitle: string; candidateId: string; candidateName: string;
  overallScore: number | null; summary: string; createdAt: string; taskId: string; jobCategory: string;
  analysisMode: string; aiProvider: string | null; aiModel: string | null; aiFallbackUsed: boolean;
  evidenceContextVersion: string | null;
}
export interface ReportEvidence {
  citationId: string | null;
  provenance?: "portfolio" | "reference";
  contextComplete: boolean; contextNote: string;
  functionLineStart?: number | null; functionLineEnd?: number | null; sourceLineCount?: number | null;
  skill: string; evidenceType: string; filePath: string; lineStart: number; lineEnd: number;
  snippet: string; strength: string; explanation: string; contentHash: string;
  projectFileId: string | null; projectVersionId: string | null; sourceId: string | null;
}
export interface FunctionSourceCoverage {
  file_path: string; function_line_start: number; function_line_end: number;
  covered_line_count: number; fully_covered: boolean; citation_ids: string[];
}
export interface FileSourceCoverage {
  file_path: string; source_line_count: number;
  covered_line_count: number; fully_covered: boolean; citation_ids: string[];
}
export interface ReportItem {
  functionSourceCoverage?: FunctionSourceCoverage[]; fileSourceCoverage?: FileSourceCoverage[];
    evidenceLevelSource?: string; skillPath?: string[];
    ratingCriteria?: { criterion: string; supported: boolean; citation_ids: string[]; reason: string }[];
  requirementId: string; requirementTitle: string; skill: string; claimed: boolean; claimText: string | null;
  evidence: ReportEvidence | null; evidenceList: ReportEvidence[]; verdict: string; aiConfidence: number | null;
  evidenceLevel?: number | null; evidenceLevelLabel?: string; evidenceLevelReason?: string; evidenceLevelGap?: string; evidenceLevelVersion?: string;
  ruleBaseScore: number; weight: number; finalScore: number | null; explanation: string; formulaVersion: string;
  evidenceId: string | null; confirmationStatus: "pending" | "accepted" | "rejected" | "corrected" | null;
  confirmedAt: string | null; reviewerNote: string | null;
  aiExplanation: string | null; aiCitationIds: string[]; aiInformationGap: string | null;
  aiSuggestion: string | null; aiTaskPlan?: { deliverable: string; steps: string[]; acceptanceChecks: string[] } | null;
  aiTaskPlanWarning?: string | null;
  aiSuggestionRedundant?: boolean; aiStatus: string; aiOrigin?: string | null;
}
export interface MatchReport extends ReportSummary {
  visualClaims?: VisualReview[];
  materials: { kind: string; id: string; title: string; versionNumber: number; contentHash: string; materialRole?: "portfolio" | "reference" | null }[];
  gaps: string[]; claimedOnly: string[]; items: ReportItem[];
  aiUsage: { input_tokens?: number; output_tokens?: number; latency_ms?: number } | null;
  aiToolCalls: { tool: string; round?: number; requirementId?: string; query?: string; resultCount?: number; scope?: string; citationId?: string; status?: string; reason?: string }[];
  actionPlan: {
    requirementId: string; requirementTitle: string; skill: string; weight: number;
    currentLevel: number | null; source: "ai_suggestion" | "rules" | "review";
    evidenceGap: string; action: string; citationIds: string[];
  }[];
}

export interface ApplicationVerificationItem {
  requirementId: string;
  visibleSupport: string | null;
  informationGap: string;
  verificationQuestions: string[];
  nextStep: "review_materials" | "request_evidence" | "discuss_implementation" | null;
  nextStepReason: string | null;
  citationIds: string[];
}

export interface GrowthPlan {
  requirementId: string;
  gapKind: "implementation" | "execution" | "contribution" | "review";
  deliverable: string;
  steps: string[];
  acceptanceChecks: string[];
}
// PRODUCT-01 私人回答草稿：保存回执里的引用（含服务端验证的可用性与原文片段）。
export interface PrivateAnswerDraftReference {
  reportId: string; requirementId: string; citationId: string;
  available: boolean; snippet: string | null;
  filePath: string | null; lineStart: number | null; lineEnd: number | null;
  provenance?: "portfolio" | "reference" | null;
}
export interface PrivateAnswerDraft {
  taskId: string; requirementId: string; text: string;
  references: PrivateAnswerDraftReference[];
  revision: number; updatedAt: string; boundary: string;
}
// 可选引用列表条目：三重引用ID + 报告来源；按协议不含 snippet。
export interface PrivateAnswerReferenceOption {
  reportId: string; requirementId: string; citationId: string;
  reportKind: "base" | "target";
  filePath: string; lineStart: number; lineEnd: number;
  provenance?: "portfolio" | "reference" | null;
}
// PUT 为完整替换；后端 extra=forbid，载荷不得携带任何额外字段。
export interface PrivateAnswerSaveReference { reportId: string; requirementId: string; citationId: string }
export interface PrivateAnswerSave { text: string; references: PrivateAnswerSaveReference[]; expectedRevision: number }
export interface EnterpriseReplyContext {
  applicationId: string; reportId: string; requirementId: string;
  replyKind: string | null; text: string; citationIds: string[];
}
export interface GrowthTask {
  id: string; baseReportId: string; jobId: string; jobTitle: string;
  // 有效已保存的目标岗位；旧任务后端回填原岗位。后端未升级前字段可能缺失。
  targetJobId?: string | null; targetJobTitle?: string | null;
  requirementId: string; requirementTitle: string; gap: string; originalAction: string;
  actionSource?: "ai_suggestion" | "rules" | "review"; actionCitationIds?: string[];
  actionNeedsRecheck?: boolean; taskPlanNeedsRecheck?: boolean; taskPlanWarning?: string | null;
  enterpriseReply?: EnterpriseReplyContext | null;
  plan: GrowthPlan; baseMaterials: MatchReport["materials"]; materials: MatchReport["materials"];
  status: "planned" | "materials_selected" | "analyzing" | "analysis_failed" | "compared";
  analysisTaskId: string | null; analysisStatus: string | null; analysisError: string | null;
  targetReportId: string | null; comparison: ReportComparison | null;
  createdAt: string; boundary: string;
}

export interface ApplicationVerificationTask {
  taskId: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  aiStatus: string;
  aiModel: string | null;
  promptVersion: string;
  snapshotHash: string;
  analysis: { items: ApplicationVerificationItem[] } | null;
  usage: { inputTokens?: number; outputTokens?: number; cacheHitTokens?: number; latencyMs?: number } | null;
  inputPreflights: Record<string, unknown>[];
  failureKind: string | null;
  currentStep: string | null;
  createdAt: string;
  errorMessage: string | null;
  boundary: string;
  reused?: boolean;
}

export interface VisualReview {
  id: string; projectVersionId: string; sourceHash: string;
  status: "completed" | "unavailable"; failureKind?: string | null; model: string | null; promptVersion: string;
  observations: { image_kind: string; observations: {
    description: string; visible_text: string; region: number[]; needs_verification: string;
  }[] } | null;
  reviewStatus: "pending" | "accepted" | "rejected"; reviewerNote: string;
  reviewedAt: string | null; createdAt: string; boundary: string;
  usage: { input_tokens?: number; output_tokens?: number; latency_ms?: number } | null;
}
export interface JobRecommendation {
  jobId: string; jobTitle: string; companyName: string; category: string; city: string; employmentType: string;
  priority: "high" | "medium" | "explore"; assessedCount: number; requirementCount: number;
  supportedCount: number; claimedCount: number; matchedSkills: string[]; gaps: string[];
  requirements?: { text: string; skill: string; weight: number; isRequired: boolean; ruleVerdict: string }[];
  evidence: { citationId?: string | null; projectFileId?: string | null; projectVersionId?: string | null; skill: string; filePath: string; lineStart: number; lineEnd: number; strength: string; explanation: string; snippet?: string; contentHash?: string }[];
}
export interface JobRecommendationResult {
  primaryDirection: string | null; summary: string;
  materials: { kind: string; id: string; title: string; versionNumber: number; contentHash: string }[];
  recommendations: JobRecommendation[];
}
export interface CareerPlanResult extends JobRecommendationResult {
  planId: string | null; previousPlanId: string | null;
  aiPlan: {
    comparison: string; focusJobId: string | null;
    advice: { jobId: string; reason: string; keyGap: string; nextTask: string; taskPlan?: { deliverable: string; steps: string[]; acceptanceChecks: string[] } | null; citationIds: string[] }[];
  } | null;
  aiFallbackUsed: boolean; aiStatus: string; aiModel: string | null;
  aiUsage: { input_tokens?: number; output_tokens?: number; latency_ms?: number } | null;
  changes: { jobId: string; jobTitle: string; status?: "current" | "not_in_current";
    previousSupportedCount: number | null; currentSupportedCount: number | null;
    previousPriority: string | null; currentPriority: string | null;
    detail: string; materialsChanged?: boolean; requirementsChanged?: boolean; jobDetailsChanged?: boolean; evidenceIds: string[] }[];
  aiValidationIssues?: { reason: string; rejectedClaim: string; citationIds: string[] }[];
}
export const CATEGORY_LABELS: Record<string, string> = {
  software: "软件开发", data_analysis: "数据分析", operations: "运营", design: "设计", other: "其他",
};
export const EMPLOYMENT_LABELS: Record<string, string> = {
  internship: "实习", campus: "校园招聘", full_time: "全职",
};

export interface ReportComparison {
  baseId: string; targetId: string; contextChanges: string[];
  // 跨岗位补证对比携带的原/目标岗位身份；旧同岗位比较后端可能不下发。
  baseJobId?: string | null; targetJobId?: string | null;
  baseJobTitle?: string | null; targetJobTitle?: string | null;
  baseMaterials: MatchReport["materials"]; targetMaterials: MatchReport["materials"];
  limitations: string[];
  items: { requirementId: string; title: string; status: string;
    baseRequirement: { title?: string; skill?: string; weight?: number } | null;
    targetRequirement: { title?: string; skill?: string; weight?: number } | null;
    baseLevel: number | null; targetLevel: number | null;
    baseAiStatus: string | null; targetAiStatus: string | null;
    baseReview: string | null; targetReview: string | null;
    baseExplanation?: string | null; targetExplanation?: string | null;
    baseSuggestion?: string | null; targetSuggestion?: string | null;
    baseTaskPlanWarning?: string | null; targetTaskPlanWarning?: string | null;
    baseTaskPlan?: ReportItem["aiTaskPlan"]; targetTaskPlan?: ReportItem["aiTaskPlan"];
    baseInformationGap?: string | null; targetInformationGap?: string | null;
    addedEvidence: ReportEvidence[]; removedEvidence: ReportEvidence[]; changes: string[];
  }[];
}

export interface NotificationItem {
  id: string; type: string; title: string; createdAt: string;
  readAt: string | null; accessible: boolean;
}
export interface NotificationPage {
  items: NotificationItem[]; total: number; page: number; pageSize: number; unreadCount: number;
}
