import { sourceLabel, type SourceMaterial } from "@/lib/source-label";
import type { ReportEvidence } from "@/lib/api/domain";

export default function EvidenceSnippet({ evidence, materials = [] }: { evidence: ReportEvidence; materials?: readonly SourceMaterial[] }) {
  return <div className="min-w-0">
    <p className={`mt-2 text-xs leading-6 ${evidence.contextComplete ? "text-slate-500" : "text-amber-800"}`}>
      单个引用片段：{evidence.contextNote || "历史引用未核验上下文完整性"}
    </p>
    <pre aria-label={`原文 ${sourceLabel(evidence, materials)} 第 ${evidence.lineStart} 至 ${evidence.lineEnd} 行`}
      className="mt-3 max-h-80 max-w-full overflow-auto rounded-lg bg-slate-50 p-3 text-xs leading-6">
      <code>{evidence.snippet.split("\n").map((line, index) => <span className="block" key={index}>
        <span aria-hidden="true" className="mr-4 inline-block w-8 select-none text-right text-slate-400">{evidence.lineStart + index}</span>{line || " "}
      </span>)}</code>
    </pre>
  </div>;
}
