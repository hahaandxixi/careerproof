import type { Candidate, Job, MatchResult, SkillClaim } from "../types";
import { parseResume, maskResumeText } from "../ai/resumeParser";
import { findEvidence } from "../analyzer/codeAnalyzer";
import { matchCandidate } from "../matcher/matcher";
import { getAiProvider } from "../ai/provider";

/**
 * Agent 工作流编排器 —— 把「解析 → 检索 → 匹配 → 总结」显式拆成可追踪步骤。
 *
 * 每个步骤都会留下 trace，供前端展示真实的工具调用过程，
 * 回应「Agent/RAG 不能只堆名词」的评审风险。
 */

export interface PipelineStep {
  step: number;
  name: string;
  detail: string;
}

export interface PipelineOutput {
  claims: SkillClaim[];
  result: MatchResult;
  summary: string;
  steps: PipelineStep[];
}

export async function runMatchPipeline(job: Job, candidate: Candidate): Promise<PipelineOutput> {
  const steps: PipelineStep[] = [];

  // 步骤 1：简历解析（脱敏后提取技能声明）
  const masked = maskResumeText(candidate.resumeText);
  const claims = parseResume(masked);
  steps.push({
    step: 1,
    name: "解析简历",
    detail: `从简历中识别出 ${claims.length} 项技能声明：${claims.map((c) => c.skill).join("、") || "无"}`,
  });

  // 步骤 2：RAG 证据检索（以每项岗位技能为 query，在代码语料中检索证据）
  const allFiles = candidate.projects.flatMap((p) => p.files);
  const evidenceSummary = job.requirements
    .map((r) => `${r.skill}(${findEvidence(allFiles, r.skill).length}条证据)`)
    .join("、");
  steps.push({
    step: 2,
    name: "检索代码证据",
    detail: `在 ${candidate.projects.length} 个项目共 ${allFiles.length} 个文件中检索：${evidenceSummary}`,
  });

  // 步骤 3：可追溯匹配
  const result = matchCandidate(job, claims, allFiles, candidate.id);
  steps.push({
    step: 3,
    name: "可追溯匹配",
    detail: `生成 ${result.items.length} 项要求匹配，综合得分 ${result.overallScore}`,
  });

  // 步骤 4：结论生成（LLM 槽位，MVP 用 mock）
  const summary = await getAiProvider().summarizeMatch(result, job.title, candidate.name);
  steps.push({
    step: 4,
    name: "生成结论",
    detail: summary,
  });

  return { claims, result, summary, steps };
}
