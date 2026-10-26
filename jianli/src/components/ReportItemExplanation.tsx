import type { ReportComparison } from "@/lib/api/domain";
import { displayFilePathText } from "@/lib/display-path";

export default function ReportItemExplanation({ item, baseLabel = "基准报告", targetLabel = "目标报告" }: {
  item: ReportComparison["items"][number]; baseLabel?: string; targetLabel?: string;
}) {
  const sides = [
    { label: baseLabel, explanation: item.baseExplanation, gap: item.baseInformationGap,
      suggestion: item.baseSuggestion, plan: item.baseTaskPlan,
      planWarning: item.baseTaskPlanWarning, current: false },
    { label: targetLabel, explanation: item.targetExplanation, gap: item.targetInformationGap,
      suggestion: item.targetSuggestion, plan: item.targetTaskPlan,
      planWarning: item.targetTaskPlanWarning, current: true },
  ];
  return <div className="grid gap-3 sm:grid-cols-2">
    {sides.map(side => <div key={side.label} className={`space-y-2 rounded-lg p-3 ${side.current ? "bg-indigo-50" : "bg-slate-50"}`}>
      <p className="font-medium">{side.label}</p>
      <p className="whitespace-pre-wrap break-words">{displayFilePathText(side.explanation || "未记录解释或无此要求")}</p>
      <p className="break-words text-amber-800">缺口：{displayFilePathText(side.gap || "未记录")}</p>
      <p className="whitespace-pre-wrap break-words">补证建议：{displayFilePathText(side.suggestion || "未记录可采用的 AI 建议，请到报告核对状态")}</p>
      {side.planWarning && <p role="alert" className="rounded border border-amber-300 bg-amber-50 p-2 text-amber-900">{side.planWarning} 已隐藏为可采用任务草稿，请重新核对交付物。</p>}
      {side.plan && <details className="rounded-lg border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer font-medium">查看这次执行草稿</summary>
        <p className="mt-2 break-words">交付物：{side.plan.deliverable}</p>
        <p className="mt-2">执行步骤</p>
        <ol className="list-decimal space-y-1 break-words pl-5">{side.plan.steps.map((step, index) => <li key={index}>{step}</li>)}</ol>
        <p className="mt-2">核验条件</p>
        <ul className="list-disc space-y-1 break-words pl-5">{side.plan.acceptanceChecks.map((check, index) => <li key={index}>{check}</li>)}</ul>
      </details>}
    </div>)}
  </div>;
}
