import type { ReportItem } from "@/lib/api/domain";
import { coverageDisplay } from "@/lib/source-coverage";
import EvidenceLink from "./EvidenceLink";

export default function SourceCoverage({ item }: { item: Pick<ReportItem, "evidenceList" | "functionSourceCoverage" | "fileSourceCoverage"> }) {
  if (!item.evidenceList.length) return null;
  const rows = coverageDisplay(item);
  return <section aria-label="源码联合覆盖" className="mt-4 min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
    <h4 className="font-semibold text-slate-800">源码联合覆盖</h4>
    <p className="mt-2 text-xs leading-6 text-slate-600">单个引用可能被截取；以下按同一材料版本的多个引用合并行范围，重叠行只计一次。</p>
    {!rows.length ? <p className="mt-2 text-xs leading-6 text-slate-500">本报告未记录可核对的函数或整文件覆盖范围，不能据此判断源码已展示完整。第三方参考不参与个人源码覆盖。</p> :
      <ul className="mt-3 space-y-3">{rows.map((row, index) => <li key={`${row.kind}-${row.filePath}-${row.start}-${index}`} className="min-w-0 rounded-lg bg-white p-3">
        <p className="break-all text-xs text-slate-600">{row.filePath}</p>
        <p className="mt-1 leading-6">{row.kind === "function" ? "函数原文" : "整文件原文"} · {row.verified ? `第 ${row.start}–${row.end} 行 · 已展示 ${row.covered}/${row.total} 行` : "覆盖记录与当前引用未能核对，范围待核验"}</p>
        {row.verified && <p className={`mt-1 text-xs ${row.complete ? "text-emerald-800" : "text-amber-800"}`}>{row.complete ? "这些引用已覆盖该范围的全部原文" : "这些引用尚未覆盖该范围的全部原文"}</p>}
        {!!row.citationIds.length && <div className="mt-2 flex flex-wrap gap-3">{row.citationIds.map(id => <EvidenceLink key={id} citationId={id} className="text-xs text-indigo-700 underline">查看引用 {id}</EvidenceLink>)}</div>}
      </li>)}</ul>}
    <p className="mt-3 text-xs leading-6 text-slate-500">源码展示完整不等于任务实现、运行成功或本人贡献已获证明；覆盖信息不自动提高评级。</p>
  </section>;
}
