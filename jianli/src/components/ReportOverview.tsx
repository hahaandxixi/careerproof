import type { MatchReport } from "@/lib/api/domain";
import { evidenceWorkspace, evidenceWorkspaceSummary } from "@/lib/evidence-workspace";
import { initialReportRequirement } from "@/lib/report-reader";
import { reportModeLabel, reportSummaryText } from "@/lib/report-display";
import EvidenceLink from "./EvidenceLink";

export default function ReportOverview({ report, role, workbench = false }: { report: MatchReport; role?: string; workbench?: boolean }) {
  const first = report.items.find(item => item.requirementId === initialReportRequirement(report.items));
  const states = evidenceWorkspace(report.items);
  const counts = { resume: report.materials.filter(m => m.kind === "resume").length, personal: report.materials.filter(m => m.kind === "project" && m.materialRole !== "reference").length, reference: report.materials.filter(m => m.materialRole === "reference").length };
  const identity = role === "student" ? "学生" : role === "enterprise" ? "企业" : role === "admin" ? "管理员" : "当前账号";
  if (workbench) return <section className="report-overview min-w-0 space-y-3" aria-label="岗位匹配报告" aria-labelledby="report-title">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="min-w-0"><h1 id="report-title" className="break-words text-2xl font-bold text-slate-950">{report.jobTitle}</h1>
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600"><span>{report.candidateName}</span><time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time><span className="font-medium text-indigo-800">{report.aiProvider?.startsWith("mock") ? reportModeLabel(report) : report.aiFallbackUsed ? "规则分析 · AI 已降级" : ["ai_evidence", "ai_evidence_manual"].includes(report.analysisMode) ? "AI 分析 + 规则校验" : report.analysisMode === "rules" ? "规则分析" : reportModeLabel(report)}</span></p>
      </div>
      <dl aria-label="已保存的证据状态摘要" className="grid grid-cols-3 gap-x-6 gap-y-2">
        <div><dt className="text-sm text-emerald-800">有证据支持</dt><dd className="text-2xl font-semibold tabular-nums">{states.supported.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
        <div><dt className="text-sm text-amber-800">待补材料</dt><dd className="text-2xl font-semibold tabular-nums">{states.gaps.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
        <div><dt className="text-sm text-slate-600">岗位要求</dt><dd className="text-2xl font-semibold tabular-nums">{report.items.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
      </dl>
    </div>
    {(states.partial.length > 0 || states.other.length > 0) && <p className="text-sm text-slate-600">另有 {states.partial.length} 项部分支持 · {states.other.length} 项未覆盖或需复核。</p>}
    <p className="text-sm text-slate-600">{report.materials.map(m=>`${m.title} v${m.versionNumber}`).join(" · ")||"历史记录未保存材料版本"}</p>
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-slate-600">
      <EvidenceLink targetId="report-materials" className="inline-flex min-h-9 items-center text-indigo-700 underline">材料版本</EvidenceLink>
      {role === "student" && <EvidenceLink targetId="report-comparison" className="inline-flex min-h-9 items-center font-medium text-indigo-700 underline">版本对比</EvidenceLink>}
      <EvidenceLink targetId="report-analysis" className="inline-flex min-h-9 items-center text-indigo-700 underline">分析详情</EvidenceLink>
    </div>
    {report.aiFallbackUsed && <p className="border-l-2 border-amber-400 pl-3 text-sm text-amber-900"><strong>模型已降级：</strong>模型处理或输出校验未能完成，本报告使用本地规则结果。</p>}
  </section>;
  return <section className="panel min-w-0 space-y-3" aria-labelledby="report-title">
    <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
      <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{identity}查看</span>
      <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-indigo-900">{reportModeLabel(report)}</span>
    </div>
    <div><h1 id="report-title" className="page-title">岗位匹配报告</h1><p className="mt-2 break-words text-lg font-semibold text-slate-900">{report.candidateName} · {report.jobTitle}</p></div>
    {workbench && <div>
      <dl aria-label="已保存的证据状态摘要" className="grid grid-cols-3 gap-2 border-y border-slate-100 py-3">
        <div><dt className="text-sm text-emerald-800">有证据支持</dt><dd className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{states.supported.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
        <div><dt className="text-sm text-amber-800">待补材料</dt><dd className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{states.gaps.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
        <div><dt className="text-sm text-slate-600">岗位要求</dt><dd className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{report.items.length}<span className="ml-1 text-sm font-normal">项</span></dd></div>
      </dl>
      {(states.partial.length > 0 || states.other.length > 0) && <p className="mt-2 text-sm text-slate-600">另有 {states.partial.length} 项部分支持 · {states.other.length} 项未覆盖或需复核。</p>}
    </div>}
    <dl className="grid gap-3 text-sm sm:grid-cols-2">
      <div><dt className="text-xs text-slate-600">生成时间</dt><dd className="mt-1 text-slate-900"><time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time></dd></div>
      <div className="min-w-0"><dt className="text-xs text-slate-600">固定材料版本</dt><dd className="mt-1 break-words text-slate-900">{report.materials.length ? [counts.resume && `${counts.resume} 份简历`, counts.personal && `${counts.personal} 份个人作品`, counts.reference && `${counts.reference} 份第三方参考`].filter(Boolean).join(" · ") + "（本次固定版本）" : "历史报告未记录材料版本"}<EvidenceLink targetId="report-materials" className="ml-2 inline-block text-indigo-700 underline">核对材料</EvidenceLink></dd></div>
    </dl>
    {!workbench && <div className="surface-muted rounded-xl p-4"><h2 className="text-sm font-semibold text-slate-900">这份材料说明了什么</h2><p className="mt-2 text-sm leading-7 text-slate-800">{evidenceWorkspaceSummary(report.items)}</p><details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-indigo-700">查看原报告摘要</summary><p className="mt-2 whitespace-pre-wrap break-words leading-7 text-slate-700">{reportSummaryText(report.summary)}</p></details></div>}
    {workbench && <details className="text-sm text-slate-600"><summary className="cursor-pointer py-1">查看本次材料名称与版本</summary><p className="mt-2 break-words leading-6">{report.materials.map(material => `${material.title} · 第 ${material.versionNumber} 版`).join("；")}</p></details>}
    {report.aiFallbackUsed && <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900"><strong>模型已降级：</strong>模型处理或输出校验未能完成，本报告使用本地规则结果。</p>}
    {!workbench && first && <EvidenceLink targetId={`requirement-${first.requirementId}`} className="btn min-h-11 max-w-full whitespace-normal break-words text-left">先核对「{first.requirementTitle}」 →</EvidenceLink>}
  </section>;
}
