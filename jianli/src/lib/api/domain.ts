export interface Page<T> { items: T[]; total: number; page: number; pageSize: number }
export interface Option { value: string; label: string }
export interface JobOptions { categories: Option[]; employmentTypes: Option[]; skills: { name: string; category: string }[] }
export interface Enterprise { id: string; name: string; description: string; isVerified: boolean; role: string }
export interface RequirementInput { rawText: string; skillName: string; weight: number; isRequired: boolean }
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
  contextComplete: boolean; contextNote: string;
  skill: string; evidenceType: string; filePath: string; lineStart: number; lineEnd: number;
  snippet: string; strength: string; explanation: string; contentHash: string;
  projectFileId: string | null; projectVersionId: string | null; sourceId: string | null;
}
  export interface ReportItem {
    evidenceLevelSource?: string; skillPath?: string[];
    ratingCriteria?: { criterion: string; supported: boolean; citation_ids: string[]; reason: string }[];
  requirementId: string; requirementTitle: string; skill: string; claimed: boolean; claimText: string | null;
  evidence: ReportEvidence | null; evidenceList: ReportEvidence[]; verdict: string; aiConfidence: number | null;
  evidenceLevel?: number | null; evidenceLevelLabel?: string; evidenceLevelReason?: string; evidenceLevelGap?: string; evidenceLevelVersion?: string;
  ruleBaseScore: number; weight: number; finalScore: number | null; explanation: string; formulaVersion: string;
  evidenceId: string | null; confirmationStatus: "pending" | "accepted" | "rejected" | "corrected" | null;
  confirmedAt: string | null; reviewerNote: string | null;
  aiExplanation: string | null; aiCitationIds: string[]; aiInformationGap: string | null;
  aiSuggestion: string | null; aiStatus: string; aiOrigin?: string | null;
}
export interface MatchReport extends ReportSummary {
  materials: { kind: string; id: string; title: string; versionNumber: number; contentHash: string }[];
  gaps: string[]; claimedOnly: string[]; items: ReportItem[];
  aiUsage: { input_tokens?: number; output_tokens?: number; latency_ms?: number } | null;
}
export interface DeepSeekWebHandoff {
  providerUrl: string; prompt: string; promptVersion: string;
  privacyNotice: string; requirementCount: number; contextDigest: string;
}
export const CATEGORY_LABELS: Record<string, string> = {
  software: "软件开发", data_analysis: "数据分析", operations: "运营", design: "设计", other: "其他",
};
export const EMPLOYMENT_LABELS: Record<string, string> = {
  internship: "实习", campus: "校园招聘", full_time: "全职",
};
