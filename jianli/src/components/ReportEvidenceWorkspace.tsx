"use client";

import type { ReactNode } from "react";
import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { effectiveReportStatus, reportStatusTone } from "@/lib/evidence-workspace";
import { validatedGrowthAdvice } from "@/lib/analysis-status";
import { compactSourceLabel, sourceLocationId } from "@/lib/source-label";
import { requirementConclusion, savedRequirementAction, type WorkspaceFilter } from "@/lib/report-workspace";
import { readableSoleReportSource } from "@/lib/source-limits";
import EvidenceLink from "./EvidenceLink";
import ReportRequirementReader from "./ReportRequirementReader";

export default function ReportEvidenceWorkspace({ report, children, overview, selectedRequirementId, onRequirementChange, filter, onFilterChange }: { report: MatchReport; children: ReactNode; overview?: ReactNode; selectedRequirementId?: string | null; onRequirementChange?: (id: string | null) => void; filter?: WorkspaceFilter; onFilterChange?: (filter: WorkspaceFilter) => void }) {
  return <ReportRequirementReader items={report.items} overview={overview} selectedRequirementId={selectedRequirementId} onRequirementChange={onRequirementChange} filter={filter} onFilterChange={onFilterChange}>{children}</ReportRequirementReader>;
}

export function RequirementActionPanel({ report, item, explanationVisible = false, explanationPanel, sourcePanel }: {
  report: MatchReport; item: ReportItem; explanationVisible?: boolean;
  explanationPanel?: ReactNode; sourcePanel?: ReactNode;
}) {
  const tone = reportStatusTone(item);
  const supported = tone === "supported";
  const actionable = tone === "gap";
  const action = savedRequirementAction(report, item);
  const advice = validatedGrowthAdvice(report, item);
  const explanation = requirementConclusion(item);
  const gap = advice?.gap || item.evidenceLevelGap?.trim();
  const conclusion = actionable ? gap || action?.evidenceGap?.trim() || explanation : explanation;
  const adviceSources = new Set(action?.citationIds ?? []);
  const openSource = sourcePanel ? readableSoleReportSource(report, item) : undefined;
  const inlineSources = new Set(explanationVisible ? item.aiCitationIds : []);
  const citationSources = item.evidenceList.map((source, index) => ({ source, index })).filter(({ source }) =>
    source !== openSource && (!source.citationId || !inlineSources.has(source.citationId)));
  return <div className={`requirement-document ${supported ? "requirement-with-source" : ""} ${item.evidenceList.length ? "requirement-has-sources" : ""}`} aria-label={`${item.skill}的判断与来源`}>
    <div className="requirement-reading-copy min-w-0 space-y-4">
    {explanationPanel}
    {!explanationVisible && <div><h4 className="text-base font-semibold text-slate-900">{supported ? "判断依据" : actionable ? "当前缺口" : "当前需核对"}</h4>
      {/[0-9a-f]{8}-[0-9a-f-]{27,}/i.test(conclusion || "") ? <details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-brand-ink">查看保存的缺口与材料定位原文</summary><p className="mt-2 whitespace-pre-wrap break-words leading-7 text-slate-700">{conclusion}</p></details> : <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">{conclusion || "这项要求尚无已保存的判断说明，请核对岗位原文与材料来源。"}</p>}
    </div>}
    {effectiveReportStatus(item) === "unsupported" && <p className="text-sm leading-6 text-slate-700">规则暂未支持，请人工核对岗位要求和已保存材料。</p>}
    {!report.aiFallbackUsed && item.aiStatus && !["validated", "not_used", "not_requested", "rules_only", "skipped"].includes(item.aiStatus) && <p className="text-sm leading-6 text-amber-900">本项保留规则判断，AI 解释未采用。</p>}
    {citationSources.length > 0 && <nav className="requirement-citation-links" aria-label="本项引用">{citationSources.map(({ source, index }) => <EvidenceLink key={sourceLocationId(item.requirementId, source, index)} targetId={sourceLocationId(item.requirementId, source, index)} className="report-citation-chip">{source.citationId && adviceSources.has(source.citationId) && <span className="sr-only">建议依据：</span>}{compactSourceLabel(source, report.materials).fileName} · {source.lineStart}–{source.lineEnd}行 ↗</EvidenceLink>)}</nav>}
    </div>
    {sourcePanel && <div className="requirement-source-context min-w-0">{sourcePanel}</div>}
  </div>;
}
