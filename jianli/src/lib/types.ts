// 核心数据模型 —— 与核心创新「从项目代码验证能力 + 可追溯匹配」对应

/** 技能声明来源：简历自我描述 */
export interface SkillClaim {
  skill: string; // 归一化技能名，如 "MySQL"
  claimText: string; // 简历原文，如 "熟悉 MySQL 数据库设计与查询优化"
}

/** 证据强度 */
export type EvidenceStrength = "high" | "medium" | "low";

/** 一条从项目代码中检索到的能力证据 */
export interface CodeEvidence {
  skill: string; // 被验证的技能名
  evidenceType: string; // 证据类型：sql_ddl / sql_query / config / dependency / library_import / test / file_pattern
  filePath: string; // 证据所在文件
  snippet: string; // 命中片段（脱敏处理后的只读文本）
  strength: EvidenceStrength;
  explanation: string; // 为什么这段代码能证明该技能
}

/** 项目代码快照：一个文件的路径 + 内容 */
export interface ProjectFile {
  path: string;
  content: string;
}

/** 候选人的项目（代码仓库快照） */
export interface Project {
  id: string;
  name: string;
  description: string;
  files: ProjectFile[];
}

/** 候选人（学生） */
export interface Candidate {
  id: string;
  name: string;
  school: string;
  major: string;
  /** 简历原文（结构化文本，MVP 阶段先不解析 PDF） */
  resumeText: string;
  projects: Project[];
}

/** 岗位要求项：一条要求绑定一个可检索的技能标签 */
export interface JobRequirement {
  id: string;
  title: string; // 要求描述，如 "熟悉 MySQL 数据库设计"
  skill: string; // 用于在代码中检索证据的技能标签
  weight: number; // 权重 1-5
}

/** 岗位 */
export interface Job {
  id: string;
  title: string;
  company: string;
  description: string;
  requirements: JobRequirement[];
}

/** 单个要求项的匹配判定 */
export type Verdict = "verified" | "claimed_only" | "gap";

/** 单个要求的匹配结果（可追溯的证据链单元） */
export interface MatchItem {
  requirementId: string;
  requirementTitle: string;
  skill: string;
  /** 候选人是否在简历中声明了该技能 */
  claimed: boolean;
  claimText?: string;
  /** 代码中检索到的最强证据 */
  evidence: CodeEvidence | null;
  /** 该项检索到的全部证据（用于证据链展开） */
  evidenceList: CodeEvidence[];
  /** 判定：已验证 / 仅声明无证据 / 缺口 */
  verdict: Verdict;
  /** 该项得分 0-1 */
  score: number;
}

/** 整体匹配结果 */
export interface MatchResult {
  jobId: string;
  candidateId: string;
  overallScore: number; // 0-100
  items: MatchItem[];
  gaps: string[]; // 缺失项（verdict === gap）
  claimedOnly: string[]; // 仅声明未验证的技能
  summary: string; // 一句话结论（可由 LLM 生成，MVP 用规则生成）
}

/** 脱敏：MVP 阶段对简历中的敏感字段做占位替换 */
export type PrivacyLevel = "public" | "masked";
