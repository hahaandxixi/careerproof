import { demoJobAlias, displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import IdentityName from "./IdentityName";
import type { MatchReport } from "@/lib/api/domain";
import { evidenceWorkspace, evidenceWorkspaceSummary } from "@/lib/evidence-workspace";
import { initialReportRequirement } from "@/lib/report-reader";
import { reportModeLabel, reportReadingStatus, reportSummaryText } from "@/lib/report-display";
import EvidenceLink from "./EvidenceLink";

export default function ReportOverview({ report, role, workbench = false }: { report: MatchReport; role?: string; workbench?: boolean }) {
  const first = report.items.find(item => item.requirementId === initialReportRequirement(report.items));
  const states = evidenceWorkspace(report.items);
  const readingStatus = reportReadingStatus(report);
  const counts = { resume: report.materials.filter(m => m.kind === "resume").length, personal: report.materials.filter(m => m.kind === "project" && m.materialRole !== "reference").length, reference: report.materials.filter(m => m.materialRole === "reference").length };
  const identity = role === "student" ? "学生" : role === "enterprise" ? "企业" : role === "admin" ? "管理员" : "当前账号";
  if (workbench) return <section className="report-overview min-w-0 space-y-3" aria-label="本报告证据状态摘要">
    <div className="report-overview-heading flex flex-wrap items-center justify-between gap-4">
      <dl aria-label="已保存的证据状态摘要" className="grid grid-cols-3 gap-x-6 gap-y-2">
        <div><dt className="text-sm text-emerald-800">有证据支持</dt><dd className="text-2xl font-semibold tabular-nums">{states.supported.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
        <div><dt className="text-sm text-amber-800">待补材料</dt><dd className="text-2xl font-semibold tabular-nums">{states.gaps.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
        <div><dt className="text-sm text-slate-600">岗位要求</dt><dd className="text-2xl font-semibold tabular-nums">{report.items.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
      </dl>
    </div>
    {(states.partial.length > 0 || states.other.length > 0) && <p className="text-sm text-slate-600">另有 {states.partial.length} 项部分支持 · {states.other.length} 项未覆盖或需复核。</p>}
    <div className="report-overview-tools flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-slate-600">
      {role === "student" && <EvidenceLink targetId="report-comparison" className="inline-flex min-h-9 items-center font-medium text-[#1d4a40] underline">版本对比</EvidenceLink>}
      <EvidenceLink targetId="report-materials" className="inline-flex min-h-9 min-w-0 items-center break-words text-slate-700 underline" aria-label="查看本报告材料版本">{report.materials.map(m=>`${displayMaterialTitle(m.title, m.id)} v${m.versionNumber}`).join(" · ")||"历史记录未保存材料版本"}</EvidenceLink>
      <EvidenceLink targetId="report-analysis" className="inline-flex min-h-9 items-center text-[#1d4a40] underline">分析详情</EvidenceLink>
    </div>
    {demoJobAlias(report.jobId) && <p className="report-sample-note">演示数据 · 岗位、人物与材料均为虚构，仅用于阅读和操作体验。</p>}
    {report.aiFallbackUsed && <p className="report-result-notice" role="status"><strong>{readingStatus.label}：</strong>{readingStatus.reason}</p>}
  </section>;
  return <section className="panel min-w-0 space-y-3" aria-labelledby="report-title">
    <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
      <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{identity}查看</span>
      <span className="rounded-full border border-[#c8d8d0] bg-[#e7efe9] px-3 py-1 text-[#173c34]">{reportModeLabel(report)}</span>
    </div>
    <div><h1 id="report-title" className="page-title">岗位匹配报告</h1><p className="mt-2 break-words text-lg font-semibold text-slate-900"><IdentityName name={report.candidateName} identityId={report.candidateId}/> · {displayJobTitle(report.jobTitle, report.jobId)}</p></div>
    <dl className="grid gap-3 text-sm sm:grid-cols-2">
      <div><dt className="text-xs text-slate-600">生成时间</dt><dd className="mt-1 text-slate-900"><time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time></dd></div>
      <div className="min-w-0"><dt className="text-xs text-slate-600">固定材料版本</dt><dd className="mt-1 break-words text-slate-900">{report.materials.length ? [counts.resume && `${counts.resume} 份简历`, counts.personal && `${counts.personal} 份个人作品`, counts.reference && `${counts.reference} 份第三方参考`].filter(Boolean).join(" · ") + "（本次固定版本）" : "历史报告未记录材料版本"}<EvidenceLink targetId="report-materials" className="ml-2 inline-block text-[#1d4a40] underline">核对材料</EvidenceLink></dd></div>
    </dl>
    <div className="surface-muted rounded-xl p-4"><h2 className="text-sm font-semibold text-slate-900">这份材料说明了什么</h2><p className="mt-2 text-sm leading-7 text-slate-800">{evidenceWorkspaceSummary(report.items)}</p><details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-[#1d4a40]">查看原报告摘要</summary><p className="mt-2 whitespace-pre-wrap break-words leading-7 text-slate-700">{reportSummaryText(report.summary)}</p></details></div>
    {report.aiFallbackUsed && <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900"><strong>{readingStatus.label}：</strong>{readingStatus.reason}</p>}
    {first && <EvidenceLink targetId={`requirement-${first.requirementId}`} className="btn min-h-11 max-w-full whitespace-normal break-words text-left">先核对「{first.requirementTitle}」 →</EvidenceLink>}
  </section>;
}
