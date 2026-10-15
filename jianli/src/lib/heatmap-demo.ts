import type { ApplicationView } from "./api/client.ts";
import { heatmapCellClass } from "./heatmap-cell.js";
import { VERDICT_LABELS } from "./verdict-display.js";
export const DEMO_REQUIREMENTS = [
  { id: "demo-python", title: "Python 数据处理", skill: "Python" },
  { id: "demo-sql", title: "SQL 聚合查询", skill: "SQL" },
  { id: "demo-test", title: "自动化测试", skill: "pytest" },
  { id: "demo-contribution", title: "本人贡献记录", skill: "贡献记录" },
];
const rows = [
  // Preset interface examples use the current rule scale; these are not generated reports.
  { name: "合成候选人 A", values: [["supported", 65], ["partial", 40], ["gap", 0], ["claimed_only", 10]] },
  { name: "合成候选人 B", values: [["partial", 40], ["supported", 65], ["supported", 65], ["gap", 0]] },
  { name: "合成候选人 C", values: [["claimed_only", 10], ["gap", 0], ["unsupported", null], ["partial", 40]] },
];
export const HEATMAP_DEMO: ApplicationView[] = rows.map((row, index) => ({
  id: `demo-application-${index}`, jobId: "demo-job", jobTitle: "Python 后端开发（合成示例）", companyName: "合成演示企业", candidateName: row.name,
  reportId: `demo-report-${index}`, status: "submitted", createdAt: "2026-10-12T00:00:00Z", overallScore: null,
  consentVersion: "synthetic-demo-only", replyKind: null, replyText: null, replyReferences: [], events: [], comparisonBasis: "synthetic-fixed-v1",
  dimensions: row.values.map(([verdict, score], i) => ({ requirementId: DEMO_REQUIREMENTS[i].id, title: DEMO_REQUIREMENTS[i].title, skill: DEMO_REQUIREMENTS[i].skill,
    verdict: String(verdict), score: score as number | null, weight: 1, evidenceLevel: null, evidenceLevelSource: null, evidenceLevelVersion: null, formulaVersion: "synthetic-only" })),
}));
export const DEMO_LABELS = Object.fromEntries(
  Object.entries(VERDICT_LABELS).filter(([verdict]) => verdict !== "verified"),
);
export function demoCellClass(verdict: string) {
  return heatmapCellClass(verdict);
}
