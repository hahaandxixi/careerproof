"use client";

import Link from "next/link";
import type { ApplicationView } from "@/lib/api/client";
import CandidatePairComparison from "@/components/CandidatePairComparison";
import { comparableApplicationGroup } from "@/lib/application-comparison";

const material = { kind: "project", id: "project-scenario", title: "受控合成清洗脚本", versionNumber: 1, contentHash: "scenario" };
const source = (path: string, snippet: string) => ({
  citationId: "SCENARIO-1", functionLineStart: null, functionLineEnd: null, sourceLineCount: 2,
  provenance: "portfolio", contextComplete: true, contextNote: "", projectVersionId: "project-scenario",
  contentHash: "scenario", skill: "Python", evidenceType: "code", filePath: path, lineStart: 1, lineEnd: 2,
  snippet, strength: "strong", explanation: "受控合成来源",
});
const items = [
  { requirementId: "r-python", requirementTitle: "使用 Python 清洗输入数据", skill: "Python", verdict: "supported", finalScore: 1, evidenceList: [source("pipeline.py", "def clean(rows):\n    return [row.strip() for row in rows]")], aiStatus: "validated", aiCitationIds: ["SCENARIO-1"], aiExplanation: "受控合成 A/B 均有可定位实现。", confirmationStatus: "pending", weight: 1, formulaVersion: "v1", evidenceLevel: 3, evidenceLevelLabel: "任务实现", evidenceLevelSource: "rules", evidenceLevelVersion: "v1" },
  { requirementId: "r-sql", requirementTitle: "使用 SQL 核查异常结果", skill: "SQL", verdict: "claimed_only", finalScore: 0.3, evidenceList: [], aiStatus: "validated", aiCitationIds: [], aiExplanation: "仅简历声明。", confirmationStatus: "pending", weight: 1, formulaVersion: "v1", evidenceLevel: 1, evidenceLevelLabel: "基础线索", evidenceLevelSource: "rules", evidenceLevelVersion: "v1" },
];
const dimensions = [
  { requirementId: "r-python", title: "使用 Python 清洗输入数据", skill: "Python", score: 1, verdict: "supported", weight: 1, evidenceLevel: 3, evidenceLevelSource: "rules", evidenceLevelVersion: "v1", formulaVersion: "v1" },
  { requirementId: "r-sql", title: "使用 SQL 核查异常结果", skill: "SQL", score: 0.3, verdict: "claimed_only", weight: 1, evidenceLevel: 1, evidenceLevelSource: "rules", evidenceLevelVersion: "v1", formulaVersion: "v1" },
];
const report = (id: string) => ({
  id, summary: "受控合成报告", createdAt: "2026-11-08T00:00:00Z", analysisMode: "rules", aiFallbackUsed: false,
  aiProvider: null, aiModel: null, items: items.map(item => ({ ...item })), materials: [material],
  evidenceContextVersion: "source-context-v2", confirmationStatus: "pending",
});
const candidate = (id: string, name: string, overrides: Partial<ApplicationView> = {}): ApplicationView => ({
  id, jobId: "scenario-job", jobTitle: "受控合成 · 数据工程实习生", companyName: "受控合成企业",
  candidateId: `candidate-${id}`, candidateName: name, reportId: `report-${id}`, status: "viewed",
  createdAt: "2026-11-08T00:00:00Z", overallScore: 1, consentVersion: "synthetic", replyKind: null,
  replyText: null, replyReferences: [], comparisonBasis: "scenario-basis", fixedRequirementBasisComplete: true,
  events: [], dimensions: dimensions.map(value => ({ ...value })), report: report(`report-${id}`) as never,
  ...overrides,
});
const A = candidate("a", "受控候选人甲");
const B = candidate("b", "受控候选人乙");
const C = candidate("c", "受控候选人丙", { comparisonBasis: "different-basis" });
const D = candidate("d", "受控候选人丁", { fixedRequirementBasisComplete: false });
const E = candidate("e", "受控候选人戊", { dimensions: [{ ...dimensions[0], title: "不同要求轴", weight: 2 }] });
const ALL = [A, B, C, D, E];
const grouping = comparableApplicationGroup(ALL);
const comparableIds = new Set(grouping.comparable.map(item => item.id));
const reasons: Record<string, string> = {
  c: "不同比较依据",
  d: "缺少完整固定要求",
  e: "相同 basis 但要求轴不同",
};
const exclusionReason = (item: ApplicationView) => {
  if (item.fixedRequirementBasisComplete !== true) return "缺少完整固定要求";
  if (!item.comparisonBasis || item.comparisonBasis !== A.comparisonBasis) return "不同比较依据";
  return "相同 basis 但要求轴不同";
};

export default function EnterpriseScenarioPage() {
  return <div className="mx-auto max-w-6xl space-y-5">
    <header className="space-y-2">
      <Link href="/demo" className="btn-secondary btn-compact">← 返回案例库</Link>
      <p className="workspace-meta">受控合成场景 · 不是真实投递数据</p>
      <h1 className="page-title">企业审阅台 · A/B 可比与 C/D/E 自动分组</h1>
      <p className="reading-copy">输入 [A,B,C,D,E] 经过生产使用的 <code>comparableApplicationGroup</code> 分组：只有 A/B 同依据且要求轴完整，保留在可比组；C 不同依据、D 缺少依据、E 相同 basis 但轴不同，自动进入隔离区。</p>
      <p className="text-sm text-slate-600" role="status">可比组 {grouping.comparable.length} 人 · 隔离组 {grouping.excluded.length} 人</p>
    </header>
    {grouping.comparable.length >= 2
      ? <CandidatePairComparison candidates={[grouping.comparable[0], grouping.comparable[1]]} busy={false} onOpen={() => {}} />
      : <p className="panel text-sm text-slate-600">没有两名同依据且要求轴完整的候选人，不渲染 A/B 同尺度对照。</p>}
    <section className="enterprise-uncomparable-list panel space-y-3" aria-label="受控合成 C/D/E 自动隔离">
      <div className="review-section-heading"><div><h2 className="section-title">其他报告 · 逐份核对</h2><p className="text-sm text-slate-600">以下候选人由同一生产分组函数排除，不进入上方 A/B 差异图或雷达。</p></div></div>
      <ul className="divide-y divide-[#e0dbcd] border-y border-[#e0dbcd]">
        {grouping.excluded.map(item => <li key={item.id} className="space-y-1 py-3">
          <p className="font-semibold">{item.candidateName} · {comparableIds.has(item.id) ? "可比组" : exclusionReason(item)}</p>
          <p className="text-sm text-slate-600">固定材料：受控合成清洗脚本 v1 · 依据：{item.comparisonBasis || "未记录"}</p>
          <p className="text-sm text-slate-600">要求轴：{item.dimensions.map(d => `${d.title}（权重${d.weight}）`).join("、") || "未记录"}</p>
        </li>)}
      </ul>
    </section>
    <p className="text-xs text-slate-500">受控场景标记：{Object.keys(reasons).join(" / ")}。本页不写入数据库，不代表真实投递结果。</p>
  </div>;
}
