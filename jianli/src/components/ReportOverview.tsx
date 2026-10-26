import type { MatchReport } from "@/lib/api/domain";
import { evidenceWorkspaceSummary } from "@/lib/evidence-workspace";
import { initialReportRequirement } from "@/lib/report-reader";
import { reportModeLabel, reportSummaryText } from "@/lib/report-display";
import EvidenceLink from "./EvidenceLink";

export default function ReportOverview({ report, role, workbench = false }: { report: MatchReport; role?: string; workbench?: boolean }) {
  const first = report.items.find(item => item.requirementId === initialReportRequirement(report.items));
  const counts = { resume: report.materials.filter(m => m.kind === "resume").length, personal: report.materials.filter(m => m.kind === "project" && m.materialRole !== "reference").length, reference: report.materials.filter(m => m.materialRole === "reference").length };
  const identity = role === "student" ? "学生" : role === "enterprise" ? "企业" : role === "admin" ? "管理员" : "当前账号";
  return <section className="panel min-w-0 space-y-3" aria-labelledby="report-title">
    <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
      <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{identity}查看</span>
      <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-indigo-900">{reportModeLabel(report)}</span>
    </div>
    <div><h1 id="report-title" className="page-title">岗位匹配报告</h1><p className="mt-2 break-words text-lg font-semibold text-slate-900">{report.candidateName} · {report.jobTitle}</p></div>
    <dl className="grid gap-3 text-sm sm:grid-cols-2">
      <div><dt className="text-xs text-slate-600">生成时间</dt><dd className="mt-1 text-slate-900"><time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time></dd></div>
      <div className="min-w-0"><dt className="text-xs text-slate-600">固定材料版本</dt><dd className="mt-1 break-words text-slate-900">{report.materials.length ? [counts.resume && `${counts.resume} 份简历`, counts.personal && `${counts.personal} 份个人作品`, counts.reference && `${counts.reference} 份第三方参考`].filter(Boolean).join(" · ") + "（本次固定版本）" : "历史报告未记录材料版本"}<EvidenceLink targetId="report-materials" className="ml-2 inline-block text-indigo-700 underline">核对材料</EvidenceLink></dd></div>
    </dl>
    {!workbench && <div className="surface-muted rounded-xl p-4"><h2 className="text-sm font-semibold text-slate-900">这份材料说明了什么</h2><p className="mt-2 text-sm leading-7 text-slate-800">{evidenceWorkspaceSummary(report.items)}</p><details className="mt-2 text-sm"><summary className="cursor-pointer py-1 text-indigo-700">查看原报告摘要</summary><p className="mt-2 whitespace-pre-wrap break-words leading-7 text-slate-700">{reportSummaryText(report.summary)}</p></details></div>}
    {workbench && <p className="break-words text-xs leading-6 text-slate-600">{report.materials.map(material => `${material.title} · 第 ${material.versionNumber} 版`).join("；")}</p>}
    {report.aiFallbackUsed && <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900"><strong>模型已降级：</strong>模型处理或输出校验未能完成，本报告使用本地规则结果。</p>}
    {!workbench && first && <EvidenceLink targetId={`requirement-${first.requirementId}`} className="btn min-h-11 max-w-full whitespace-normal break-words text-left">先核对「{first.requirementTitle}」 →</EvidenceLink>}
    <p className="text-xs leading-6 text-slate-600">逐项证据等级描述材料支持情况，不汇总能力总分。补证或上传新版不会替换本报告及已投递的固定快照。</p>
  </section>;
}
