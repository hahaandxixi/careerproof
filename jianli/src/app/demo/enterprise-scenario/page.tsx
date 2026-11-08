"use client";

import Link from "next/link";
import type { ApplicationView } from "@/lib/api/client";
import CandidatePairComparison from "@/components/CandidatePairComparison";

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
const report = (id: string, candidateName: string) => ({
  id, summary: "受控合成报告", createdAt: "2026-11-08T00:00:00Z", analysisMode: "rules", aiFallbackUsed: false,
  aiProvider: null, aiModel: null, items: items.map(item => ({ ...item })), materials: [material],
  evidenceContextVersion: "source-context-v2", confirmationStatus: "pending",
});
const candidate = (id: string, name: string, basis: string): ApplicationView => ({
  id, jobId: "scenario-job", jobTitle: "受控合成 · 数据工程实习生", companyName: "受控合成企业",
  candidateId: `candidate-${id}`, candidateName: name, reportId: `report-${id}`, status: "viewed",
  createdAt: "2026-11-08T00:00:00Z", overallScore: 1, consentVersion: "synthetic", replyKind: null,
  replyText: null, replyReferences: [], comparisonBasis: basis, fixedRequirementBasisComplete: true,
  events: [], dimensions: dimensions.map(value => ({ ...value })), report: report(`report-${id}`, name) as never,
});
const A = candidate("a", "受控候选人甲", "scenario-basis");
const B = candidate("b", "受控候选人乙", "scenario-basis");
const C = { ...candidate("c", "受控候选人丙", "different-basis"), dimensions: [{ ...dimensions[0], requirementId: "r-other", title: "其他口径的测试要求" }] };

export default function EnterpriseScenarioPage() {
  return <div className="mx-auto max-w-6xl space-y-5">
    <header className="space-y-2">
      <Link href="/demo" className="btn-secondary btn-compact">← 返回案例库</Link>
      <p className="workspace-meta">受控合成场景 · 不是真实投递数据</p>
      <h1 className="page-title">企业审阅台 · A/B 可比与 C 隔离</h1>
      <p className="reading-copy">该页使用真实 <code>CandidatePairComparison</code> 组件和固定合成数据验证：A/B 同依据可对照；C 依据不同，只做逐份核对，不进入同尺度图表。</p>
    </header>
    <CandidatePairComparison candidates={[A, B]} busy={false} onOpen={() => {}} />
    <section className="enterprise-uncomparable-list panel space-y-3" aria-label="受控合成 C 隔离">
      <div className="review-section-heading"><div><h2 className="section-title">其他报告 · 逐份核对</h2><p className="text-sm text-slate-600">受控候选人丙使用不同比较依据，保留在独立区域，不参与上方 A/B 差异图和雷达。</p></div></div>
      <p className="font-semibold">{C.candidateName} · {C.dimensions[0].title}</p>
      <p className="text-sm text-slate-600">固定材料：受控合成清洗脚本 v1 · 依据：different-basis</p>
    </section>
  </div>;
}
