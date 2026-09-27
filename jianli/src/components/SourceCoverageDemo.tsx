import type { ReportEvidence } from "@/lib/api/domain";
import EvidenceSnippet from "./EvidenceSnippet";
import SourceCoverage from "./SourceCoverage";
import EvidenceAnchorRestore from "./EvidenceAnchorRestore";

// Static synthetic source ranges demonstrate the UI, never an AI result or an executed project.
const sourceLines = Array.from({ length: 45 }, (_, index) => index === 0
  ? "def synthetic_example():" : `    # synthetic source line ${index + 1}`);
const evidence = (start: number, end: number, citationId: string): ReportEvidence => ({
  citationId, provenance: "portfolio", contextComplete: false,
  contextNote: "本片段只展示 40 行；其余原文可在另一条引用中查看。",
  functionLineStart: 1, functionLineEnd: 45, sourceLineCount: 45,
  skill: "Python", evidenceType: "synthetic_demo", filePath: "synthetic-version/example.py",
  lineStart: start, lineEnd: end, snippet: sourceLines.slice(start - 1, end).join("\n"),
  strength: "demo", explanation: "静态合成展示，未经模型评估，也未执行代码。", contentHash: "synthetic-demo-only",
  projectFileId: null, projectVersionId: "synthetic-version", sourceId: null,
});
const evidenceList = [evidence(1, 40, "demo-E1"), evidence(6, 45, "demo-E2")];
const item = { evidenceList,
  functionSourceCoverage: [{ file_path: "synthetic-version/example.py", function_line_start: 1, function_line_end: 45,
    covered_line_count: 45, fully_covered: true, citation_ids: ["demo-E1", "demo-E2"] }],
  fileSourceCoverage: [{ file_path: "synthetic-version/example.py", source_line_count: 45,
    covered_line_count: 45, fully_covered: true, citation_ids: ["demo-E1", "demo-E2"] }],
};

export default function SourceCoverageDemo() {
  return <section className="rounded-2xl border border-slate-200 bg-white p-6" aria-labelledby="coverage-demo-heading">
    <EvidenceAnchorRestore />
    <h2 id="coverage-demo-heading" className="text-xl font-bold">如何核对多个引用是否补齐源码？</h2>
    <p className="mt-3 text-sm leading-7 text-slate-600">以下为静态合成示例，不调用模型，不是学生报告。两条引用各展示 40 行，重叠后共覆盖 45 行；点击引用会展开原文。</p>
    <SourceCoverage item={item} />
    <details className="mt-4"><summary className="cursor-pointer text-sm font-medium text-indigo-700">展开合成来源证据</summary>
      <div className="mt-3 space-y-3">{evidenceList.map(entry => <div key={entry.citationId} id={`citation-${entry.citationId}`} className="min-w-0 scroll-mt-24 rounded-lg border border-slate-200 p-3">
        <p className="text-sm font-medium">{entry.citationId} · 第 {entry.lineStart}–{entry.lineEnd} 行</p>
        <EvidenceSnippet evidence={entry} />
      </div>)}</div>
    </details>
  </section>;
}
