import EvidenceLink from "./EvidenceLink";
import type { MatchReport } from "@/lib/api/domain";

const SOURCE_LABELS = {
  ai_suggestion: "AI 证据建议",
  rules: "本地规则提示",
  review: "人工复核后",
} as const;

export default function ActionPlan({ actions }: { actions: MatchReport["actionPlan"] }) {
  if (!actions?.length) return null;

  return <section className="panel" aria-labelledby="action-plan-heading">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 id="action-plan-heading" className="text-lg font-semibold">下一步补证计划</h2>
        <p className="mt-2 text-sm text-slate-600">按岗位权重、当前证据等级排序；建议文字来自经校验的 AI 输出或本地规则。</p>
      </div>
      <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700">优先处理 {actions.length} 项</span>
    </div>
    <ol className="mt-4 space-y-3">
      {actions.map((action, index) => <li key={action.requirementId} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white">{index + 1}</span>
          <a href={`#requirement-${action.requirementId}`} className="font-medium text-indigo-700 underline">{action.requirementTitle}</a>
          <span className="rounded-full bg-white px-2 py-1 text-xs text-slate-600">{SOURCE_LABELS[action.source]}</span>
        </div>
        <p className="mt-2 text-xs text-slate-500">{action.skill} · 岗位权重 {action.weight}/5 · 当前证据{action.currentLevel == null ? "未评级" : `${action.currentLevel}/5`}</p>
        <p className="mt-3 text-sm leading-6"><strong>建议行动：</strong>{action.action}</p>
        {action.evidenceGap && <p className="mt-1 text-sm leading-6 text-slate-600"><strong>对应缺口：</strong>{action.evidenceGap}</p>}
        {action.citationIds.length > 0 && <div className="mt-2 flex flex-wrap gap-2 text-xs text-indigo-700">{action.citationIds.map(citation => <EvidenceLink key={citation} citationId={citation} className="underline">查看引用 {citation}</EvidenceLink>)}</div>}
      </li>)}
    </ol>
    <p className="mt-3 text-xs leading-5 text-slate-500">这是一份材料完善顺序，不是能力认证或提级保证；新增材料仍需重新分析与人工核对。</p>
  </section>;
}
