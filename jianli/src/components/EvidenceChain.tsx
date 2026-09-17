import type { MatchItem } from "@/lib/types";
import VerdictBadge from "./VerdictBadge";
import EvidenceCard from "./EvidenceCard";

/**
 * 证据链单元：一条岗位要求 → 能力声明 → 代码证据（可点击展开）。
 * 使用原生 <details> 实现「点击查看依据」，无需客户端 JS。
 */
export default function EvidenceChain({ item }: { item: MatchItem }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-slate-800">{item.requirementTitle}</h3>
            <VerdictBadge verdict={item.verdict} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-600">
              技能：{item.skill}
            </span>
            {item.claimed ? (
              <span className="truncate" title={item.claimText}>
                简历声明：{item.claimText}
              </span>
            ) : (
              <span className="text-rose-500">简历未声明该技能</span>
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-sm font-semibold text-slate-700">
            {Math.round(item.score * 100)} 分
          </div>
        </div>
      </div>

      {item.evidenceList.length > 0 ? (
        <details className="mt-3 group">
          <summary className="cursor-pointer list-none text-sm font-medium text-indigo-600 hover:text-indigo-700">
            <span className="inline-flex items-center gap-1">
              <span className="transition-transform group-open:rotate-90">▸</span>
              查看 {item.evidenceList.length} 条代码证据
            </span>
          </summary>
          <div className="mt-3 space-y-2">
            {item.evidenceList.map((e, i) => (
              <EvidenceCard key={`${e.filePath}-${i}`} evidence={e} />
            ))}
          </div>
        </details>
      ) : (
        <p className="mt-3 text-xs text-slate-400">
          {item.verdict === "gap"
            ? "无代码证据，且简历未声明 —— 能力缺口"
            : "简历声明了该技能，但代码中未检索到对应证据，建议面试核实"}
        </p>
      )}
    </div>
  );
}
