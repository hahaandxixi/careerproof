import Link from "next/link";
import type { MatchReport } from "@/lib/api/domain";
import { evidenceWorkspace } from "@/lib/evidence-workspace";

export default function ReportEvidenceWorkspace({ report }: { report: MatchReport }) {
  const state = evidenceWorkspace(report.items);
  return <section aria-labelledby="evidence-workspace-title" className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 id="evidence-workspace-title" className="text-lg font-semibold">我的缺口补证工作台</h2><p className="mt-1 text-sm text-slate-600">从当前报告的一条缺口出发，补齐材料，再核对新报告的逐项变化。</p></div>
      <Link href="#report-comparison" className="btn-secondary min-h-11">查看版本变化 →</Link>
    </div>
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <div className="panel min-w-0 space-y-5">
        <div><h3 className="font-semibold">当前材料支持状态</h3><dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[["有证据支持", state.supported.length], ["部分支持", state.partial.length], ["待补材料", state.gaps.length], ["未覆盖或需复核", state.other.length]].map(([label, count]) => <div key={label} className="rounded-xl bg-slate-50 p-3"><dt className="text-xs leading-5 text-slate-600">{label}</dt><dd className="mt-1 text-2xl font-semibold text-indigo-700">{count}</dd></div>)}
        </dl><p className="mt-3 text-xs leading-6 text-slate-600">按报告已保存状态展示，不汇总能力总分；未覆盖和已驳回或修正项需单独核对。</p></div>
        <div className="space-y-3"><h3 className="font-semibold">优先补齐的证据</h3>
          {state.priorities.length === 0 ? <p className="text-sm leading-6 text-slate-600">当前没有标记为缺口或部分支持的要求。有证据支持仍需人工核对；请继续查看下方逐项证据与复核状态。</p> : state.priorities.slice(0, 3).map(item => <article key={item.requirementId} className="rounded-xl border border-slate-200 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2"><h4 className="min-w-0 break-words font-medium">{item.requirementTitle}</h4><span className="rounded-full bg-amber-50 px-3 py-1 text-xs text-amber-900">{item.verdict === "partial" ? "部分证据支持" : item.verdict === "claimed_only" ? "仅简历声明" : "材料待补充"}</span></div>
            <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-600">{item.evidenceLevelGap || item.explanation || "请核对原要求与来源材料，再确定补证交付物。"}</p>
            <div className="mt-3 flex flex-wrap gap-3"><Link className="btn min-h-11" href={`#growth-${item.requirementId}`}>从这条缺口开始补证 →</Link><Link className="inline-flex min-h-11 items-center text-sm text-indigo-700 underline" href={`#requirement-${item.requirementId}`}>核对来源与逐项解释</Link></div>
          </article>)}
          {state.priorities.length > 3 && <p className="text-xs text-slate-600">优先展示岗位权重最高的 3 项，全部 {state.priorities.length} 项仍保留在下方逐项证据中。</p>}
        </div>
      </div>
      <aside className="panel min-w-0 space-y-5" aria-label="补证步骤与投递边界">
        <h3 className="font-semibold">一个缺口，一条闭环</h3><ol className="space-y-4 text-sm">
          {[["确认缺口", "核对原岗位要求、证据与解释。"], ["补证并上传新版", "进入补证任务，上传材料并保存版本选择。"], ["生成新报告", "主动发起分析，再逐项核对材料与解释变化。"]].map(([title, detail], index) => <li key={title} className="flex gap-3"><span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-indigo-700">{index + 1}</span><div><p className="font-medium">{title}</p><p className="mt-1 leading-6 text-slate-600">{detail}</p></div></li>)}
        </ol>
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4"><h4 className="text-sm font-semibold text-indigo-900">新版材料不会覆盖原投递</h4><p className="mt-2 text-xs leading-6 text-indigo-900">已投递时，企业查看的是投递当时的固定报告快照。补证任务和新报告不会自动替换该快照，也不会自动向企业发送内容。</p></div>
        <Link className="btn-secondary min-h-11" href="/growth">查看我的补证任务 →</Link>
      </aside>
    </div>
  </section>;
}
