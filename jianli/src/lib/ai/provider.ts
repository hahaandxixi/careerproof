import type { MatchResult } from "../types";

/**
 * 大模型抽象层（可替换适配器）
 *
 * 说明：本项目的「可追溯匹配 + 代码证据」核心链路完全由确定性规则实现，
 * 不依赖大模型，因此结果可复现、可解释。这里只把「结论生成」这类
 * 自然语言润色环节抽象成大模型接口，便于后续接入真实模型做实验对比。
 */

export interface AiProvider {
  name: string;
  /** 把匹配结果润色成一段人话结论（可换成真实 LLM） */
  summarizeMatch(
    result: MatchResult,
    jobTitle: string,
    candidateName: string
  ): Promise<string>;
}

/** Mock 实现：规则生成结论，无网络、无密钥，开箱即用 */
export class MockAiProvider implements AiProvider {
  name = "mock";

  async summarizeMatch(
    result: MatchResult,
    jobTitle: string,
    candidateName: string
  ): Promise<string> {
    const verified = result.items.filter((i) => i.verdict === "verified").length;
    const claimed = result.items.filter((i) => i.verdict === "claimed_only").length;
    const gaps = result.items.filter((i) => i.verdict === "gap").length;

    const parts: string[] = [
      `${candidateName} 对「${jobTitle}」岗位的匹配度为 ${result.overallScore} 分。`,
    ];
    if (verified > 0) {
      parts.push(`${verified} 项要求能直接从项目代码中找到证据支撑，可信度较高。`);
    }
    if (claimed > 0) {
      parts.push(`${claimed} 项仅在简历中声明、暂未在代码中验证，建议在面试中重点核实。`);
    }
    if (gaps > 0) {
      parts.push(`另有 ${gaps} 项能力存在明显缺口，与岗位要求不匹配。`);
    }
    return parts.join("");
  }
}

let provider: AiProvider | null = null;

/** 获取当前 AI Provider（MVP 返回 mock；接入真实模型时在此替换） */
export function getAiProvider(): AiProvider {
  if (!provider) provider = new MockAiProvider();
  return provider;
}
