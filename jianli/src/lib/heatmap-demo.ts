import type { ApplicationView } from "./api/client.ts";
export const DEMO_REQUIREMENTS = [
  { id: "demo-python", title: "Python 数据处理", skill: "Python" },
  { id: "demo-sql", title: "SQL 聚合查询", skill: "SQL" },
  { id: "demo-test", title: "自动化测试", skill: "pytest" },
  { id: "demo-contribution", title: "本人贡献记录", skill: "贡献记录" },
];
const rows = [
  { name: "合成候选人 A", values: [["supported", 85], ["partial", 55], ["gap", 0], ["claimed_only", 20]] },
  { name: "合成候选人 B", values: [["partial", 45], ["supported", 80], ["supported", 75], ["gap", 0]] },
  { name: "合成候选人 C", values: [["claimed_only", 20], ["gap", 0], ["unsupported", null], ["partial", 40]] },
];
export const HEATMAP_DEMO: ApplicationView[] = rows.map((row, index) => ({
  id: `demo-application-${index}`, jobId: "demo-job", jobTitle: "Python 后端开发（合成示例）", companyName: "合成演示企业", candidateName: row.name,
  reportId: `demo-report-${index}`, status: "submitted", createdAt: "2026-10-12T00:00:00Z", overallScore: null,
  consentVersion: "synthetic-demo-only", replyKind: null, replyText: null, replyReferences: [], events: [], comparisonBasis: "synthetic-fixed-v1",
  dimensions: row.values.map(([verdict, score], i) => ({ requirementId: DEMO_REQUIREMENTS[i].id, title: DEMO_REQUIREMENTS[i].title, skill: DEMO_REQUIREMENTS[i].skill,
    verdict: String(verdict), score: score as number | null, weight: 1, evidenceLevel: null, evidenceLevelSource: null, evidenceLevelVersion: null, formulaVersion: "synthetic-only" })),
}));
export const DEMO_LABELS: Record<string, string> = { supported: "有证据", partial: "部分支持", claimed_only: "仅自述", gap: "缺材料", unsupported: "不可评" };
export function demoCellClass(verdict: string) {
  return ({ supported: "bg-emerald-100 text-emerald-900", partial: "bg-indigo-50 text-indigo-900", claimed_only: "bg-amber-50 text-amber-900", gap: "bg-white text-slate-700", unsupported: "bg-slate-100 text-slate-600" } as Record<string, string>)[verdict] ?? "bg-slate-100 text-slate-600";
}
