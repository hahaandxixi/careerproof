"use client";
import { useState } from "react";
import { displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import IdentityName from "./IdentityName";
import type { MatchReport } from "@/lib/api/domain";
import { evidenceWorkspace, evidenceWorkspaceSummary } from "@/lib/evidence-workspace";
import { initialReportRequirement } from "@/lib/report-reader";
import type { WorkspaceFilter } from "@/lib/report-workspace";
import { reportModeLabel, reportSummaryText } from "@/lib/report-display";
import EvidenceLink from "./EvidenceLink";

export default function ReportOverview({ report, role, workbench = false }: { report: MatchReport; role?: string; workbench?: boolean }) {
  const first = report.items.find(item => item.requirementId === initialReportRequirement(report.items));
  const states = evidenceWorkspace(report.items);
  const counts = { resume: report.materials.filter(m => m.kind === "resume").length, personal: report.materials.filter(m => m.kind === "project" && m.materialRole !== "reference").length, reference: report.materials.filter(m => m.materialRole === "reference").length };
  const identity = role === "student" ? "学生" : role === "enterprise" ? "企业" : role === "admin" ? "管理员" : "当前账号";
  const [filter, setFilter] = useState<WorkspaceFilter | null>(null);
  const claimed = report.items.filter(item => item.verdict === "claimed_only").length;
  const unsupported = report.items.filter(item => item.verdict === "unsupported").length;
  const segments: { key: WorkspaceFilter; label: string; count: number; tone: string }[] = [
    { key: "supported", label: "有证据支持", count: states.supported.length, tone: "supported" },
    { key: "partial", label: "部分支持", count: states.partial.length, tone: "partial" },
    { key: "gaps", label: "待补或仅声明", count: states.gaps.length, tone: "gap" },
    { key: "other", label: "暂不支持或需复核", count: states.other.length, tone: "other" },
  ];
  const choose = (next: WorkspaceFilter | null) => {
    setFilter(next);
    window.dispatchEvent(new CustomEvent("careerproof:filter-requirements", { detail: { filter: next ?? "all" } }));
  };
  if (workbench) return <section className="report-overview min-w-0 space-y-3" aria-label="本报告证据状态摘要">
    <div className="report-overview-heading flex flex-wrap items-end justify-between gap-3">
      <div><h2 className="report-overview-title">材料支持状态</h2><p className="report-overview-caption">按已保存判断归类，每项要求只归入一类；点击查看对应要求。</p></div>
      <button type="button" className={`report-status-all ${filter === null ? "is-active" : ""}`} aria-pressed={filter === null} onClick={() => choose(null)}>全部 {report.items.length}</button>
    </div>
    <div className="report-status-bar" aria-hidden="true">
      {segments.filter(segment => segment.count > 0).map(segment => <span key={segment.key} data-tone={segment.tone} style={{ flexGrow: segment.count }} />)}
    </div>
    <div className="report-status-grid" role="group" aria-label="按已保存的材料支持状态筛选">
      {segments.map(segment => <button key={segment.key} type="button" className={`report-status-item ${filter === segment.key ? "is-active" : ""}`} aria-pressed={filter === segment.key} data-tone={segment.tone} onClick={() => choose(segment.key)}>
        <span className="report-status-name">{segment.label}</span><strong>{segment.count}</strong><span className="report-status-unit">项</span>
      </button>)}
    </div>
    <p className="report-status-detail">待补材料 {states.gaps.length - claimed} 项 · 仅简历声明 {claimed} 项 · 暂不支持 {unsupported} 项 · 合计 {report.items.length} 项要求。</p>
    <div className="report-overview-tools flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-slate-600">
      {role === "student" && <EvidenceLink targetId="report-supplement" className="inline-flex min-h-9 items-center font-medium text-[#1d4a40] underline">查看补证建议（{states.gaps.length + states.partial.length}）</EvidenceLink>}
      {role === "student" && <EvidenceLink targetId="report-sharing" className="inline-flex min-h-9 items-center font-medium text-[#1d4a40] underline">前往投递授权</EvidenceLink>}
      {role === "student" && <EvidenceLink targetId="report-comparison" className="inline-flex min-h-9 items-center font-medium text-[#1d4a40] underline">版本对比</EvidenceLink>}
      <EvidenceLink targetId="report-materials" className="inline-flex min-h-9 min-w-0 items-center break-words text-slate-700 underline" aria-label="查看本报告材料版本">{report.materials.map(m=>`${displayMaterialTitle(m.title, m.id)} v${m.versionNumber}`).join(" · ")||"历史记录未保存材料版本"}</EvidenceLink>
      <EvidenceLink targetId="report-analysis" className="inline-flex min-h-9 items-center text-[#1d4a40] underline">分析详情</EvidenceLink>
    </div>
  </section>;
  return <section className="panel min-w-0 space-y-3" aria-labelledby="report-title">
    <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
      <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{identity}查看</span>
      {reportModeLabel(report) && <span className="rounded-full border border-[#c8d8d0] bg-[#e7efe9] px-3 py-1 text-[#173c34]">{reportModeLabel(report)}</span>}
    </div>
    <div><h1 id="report-title" className="page-title">岗位匹配报告</h1><p className="mt-2 break-words text-lg font-semibold text-slate-900"><IdentityName name={report.candidateName} identityId={report.candidateId}/> · {displayJobTitle(report.jobTitle, report.jobId)}</p></div>
    <dl className="grid gap-3 text-sm sm:grid-cols-2">
      <div><dt className="text-xs text-slate-600">生成时间</dt><dd className="mt-1 text-slate-900"><time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time></dd></div>
      <div className="min-w-0"><dt className="text-xs text-slate-600">固定材料版本</dt><dd className="mt-1 break-words text-slate-900">{report.materials.length ? [counts.resume && `${counts.resume} 份简历`, counts.personal && `${counts.personal} 份个人作品`, counts.reference && `${counts.reference} 份第三方参考`].filter(Boolean).join(" · ") + "（本次固定版本）" : "历史报告未记录材料版本"}<EvidenceLink targetId="report-materials" className="ml-2 inline-block text-[#1d4a40] underline">核对材料</EvidenceLink></dd></div>
    </dl>
    <div className="surface-muted rounded-xl p-4"><h2 className="text-sm font-semibold text-slate-900">这份材料说明了什么</h2><p className="mt-2 text-sm leading-7 text-slate-800">{evidenceWorkspaceSummary(report.items)}</p><details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-[#1d4a40]">查看原报告摘要</summary><p className="mt-2 whitespace-pre-wrap break-words leading-7 text-slate-700">{reportSummaryText(report.summary)}</p></details></div>
    {first && <EvidenceLink targetId={`requirement-${first.requirementId}`} className="btn min-h-11 max-w-full whitespace-normal break-words text-left">先核对「{first.requirementTitle}」 →</EvidenceLink>}
  </section>;
}
