import type { SkillClaim } from "../types";

/**
 * 简历解析器（规则版，真实逻辑；可替换为 LLM 语义抽取）
 *
 * MVP 阶段：用「技能关键词词典」在简历文本中定位技能声明句子。
 * 后续可将此函数替换为大模型抽取，接口不变，方便做实验对比（规则 vs LLM）。
 */

/** 技能 → 简历中可能出现的别名/关键词 */
const SKILL_KEYWORDS: Record<string, string[]> = {
  MySQL: ["MySQL", "mysql", "SQL", "数据库", "SQL 优化"],
  Redis: ["Redis", "redis", "缓存"],
  Java: ["Java", "java"],
  "Spring Boot": ["Spring", "SpringBoot", "Spring Boot"],
  React: ["React", "react"],
  Vue: ["Vue", "vue"],
  TypeScript: ["TypeScript", "TS", "typescript"],
  "Node.js": ["Node.js", "Node", "node"],
  Python: ["Python", "python"],
  "REST API": ["REST", "RESTful", "接口", "API"],
  Docker: ["Docker", "容器化"],
  Git: ["Git", "git", "版本控制"],
  数据库设计: ["数据库设计", "表设计", "数据建模", "ER 图"],
  Go: ["Go", "Golang", "golang"],
  Linux: ["Linux", "linux"],
};

/** 抽取某关键词所在的句子 */
function extractSentence(text: string, index: number): string {
  const start = Math.max(0, text.lastIndexOf("\n", index) + 1);
  const end = text.indexOf("\n", index + 1);
  return text.slice(start, end === -1 ? text.length : end).trim();
}

/** 从简历文本解析出技能声明列表 */
export function parseResume(resumeText: string): SkillClaim[] {
  const claims: SkillClaim[] = [];
  const seen = new Set<string>();

  for (const [skill, keywords] of Object.entries(SKILL_KEYWORDS)) {
    if (seen.has(skill)) continue;
    for (const kw of keywords) {
      const idx = resumeText.indexOf(kw);
      if (idx === -1) continue;
      claims.push({
        skill,
        claimText: extractSentence(resumeText, idx),
      });
      seen.add(skill);
      break;
    }
  }
  return claims;
}

/** 脱敏：替换邮箱/手机号/身份证等敏感信息（MVP 阶段的隐私保护） */
export function maskResumeText(text: string): string {
  return text
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[邮箱已脱敏]")
    .replace(/\b1[3-9]\d{9}\b/g, "[手机号已脱敏]")
    .replace(/\b\d{17}[\dXx]\b/g, "[身份证已脱敏]");
}
