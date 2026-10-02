import Link from "next/link";
import type { GrowthTask } from "@/lib/api/domain";
import { GROWTH_CHANGES } from "@/lib/growth-workflow";
import { careerPlanHref } from "@/lib/recommendation-selection";
import { enterpriseQuestionReview } from "@/lib/enterprise-question-review";
import ReportItemExplanation from "./ReportItemExplanation";

export default function GrowthComparison({ task }: { task: GrowthTask }) {
  const comparison = task.comparison;
  if (!comparison) return null;
  const resume = task.materials.find(material => material.kind === "resume")?.id;
  const projects = task.materials.filter(material => material.kind === "project").map(material => material.id);
  return <section className="panel space-y-4">
    <h2 className="text-lg font-semibold">4. 与任务固定基准逐项对比</h2>
    <p className="text-sm">变化背景：{comparison.contextChanges.map(k => GROWTH_CHANGES[k] || k).join("、") || "没有已记录的背景变化"}</p>
    {comparison.items.map(item => <article id={`growth-requirement-${item.requirementId}`} key={item.requirementId} className="scroll-mt-24 space-y-3 rounded-xl border p-4 text-sm">
      <h3 className="font-semibold">{item.title}{item.requirementId === task.requirementId ? " · 本次补证重点" : ""}</h3>
      {task.enterpriseReply && item.requirementId === task.requirementId && (() => {
        const review = enterpriseQuestionReview(item);
        return <div className="space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/50 p-3 leading-6">
          <h4 className="font-semibold">企业问题与新报告核对 · 待人工确认</h4>
          <blockquote className="whitespace-pre-wrap break-words">{task.enterpriseReply.text}</blockquote>
          <p>本次新展示的个人作品证据条目：{review.personalEvidenceCount} 条；第三方参考条目：{review.referenceEvidenceCount} 条。下方可逐条打开新报告引用。</p>
          {review.personalEvidenceCount === 0 && <p className="text-amber-800">本次对比未显示新增个人作品证据条目；原有证据和材料仍需核对。</p>}
          <p className="whitespace-pre-wrap break-words">新报告记录的仍缺项：{review.remainingGap || "未记录具体缺口，不能据此认定企业问题已解决。"}</p>
          {review.criterionChanged && <p className="text-amber-800">岗位要求已变化或该项不在新版报告中，不能把两轮解释直接当作同一问题的回答。</p>}
          <p className="text-xs text-slate-600">这些是报告展示变化，不是对企业的自动回复或通过结论；请结合原问题、材料原文和本人贡献人工核对。</p>
        </div>;
      })()}
      <p>证据等级：{item.baseLevel == null ? "未评级" : `${item.baseLevel}/5`} → {item.targetLevel == null ? "未评级" : `${item.targetLevel}/5`}；{item.changes.map(k => GROWTH_CHANGES[k] || k).join("、") || "无已记录变化"}</p>
      <ReportItemExplanation item={item} baseLabel="任务基准" />
      {item.changes.includes("requirement") && <p>原要求：{item.baseRequirement?.title || "未记录"} · 权重{item.baseRequirement?.weight ?? "未记录"} → 当前要求：{item.targetRequirement?.title || "已移除"} · 权重{item.targetRequirement?.weight ?? "未记录"}</p>}
      {[["新增展示", item.addedEvidence, task.targetReportId], ["不再展示", item.removedEvidence, task.baseReportId]].map(([label, rows, report]) => <div key={String(label)}>
        <p>{String(label)}：{(rows as typeof item.addedEvidence).length}条</p>
        <ul>{(rows as typeof item.addedEvidence).map((source, index) => <li key={index} className="break-all">
          <Link className="text-indigo-700 underline" href={`/reports/${report}${source.citationId ? `#citation-${source.citationId}` : `#requirement-${item.requirementId}`}`}>{source.filePath} · 第{source.lineStart}—{source.lineEnd}行</Link>
          {source.provenance === "reference" && <p className="text-xs text-amber-800">第三方参考，不构成个人实践证明。</p>}
          <pre className="my-2 whitespace-pre-wrap break-words rounded bg-slate-50 p-2 text-xs">{source.snippet}</pre>
        </li>)}</ul>
      </div>)}
    </article>)}
    <ul className="space-y-1 text-xs leading-6 text-amber-800">{comparison.limitations.map(v => <li key={v}>{v}</li>)}</ul>
    {resume && <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm leading-6"><p className="font-medium">继续核对职业方向</p><p>使用本次新报告的材料版本预填职业规划；先核对版本并单独同意 AI 外发，生成后才会与上次保存的规划比较。岗位要求变化与材料变化需分别解读。</p><Link className="mt-2 inline-block text-indigo-700 underline" href={careerPlanHref(resume, projects)}>用本次材料查看职业规划变化 →</Link></div>}
    <Link className="text-sm text-indigo-700 underline" href={`/jobs/${task.jobId}`}>核对岗位当前要求与后续分析</Link>
  </section>;
}
