import type { CodeEvidence, EvidenceStrength } from "@/lib/types";
import { displayFilePath, displayFilePathText } from "@/lib/display-path";

const STRENGTH_LABEL: Record<EvidenceStrength, { text: string; color: string }> = {
  high: { text: "强证据", color: "text-emerald-600" },
  medium: { text: "中证据", color: "text-sky-600" },
  low: { text: "弱证据", color: "text-slate-500" },
};

export default function EvidenceCard({ evidence }: { evidence: CodeEvidence }) {
  const s = STRENGTH_LABEL[evidence.strength];
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono text-xs text-slate-500">{displayFilePath(evidence.filePath)}</span>
        <span className={`text-xs font-medium ${s.color}`}>{s.text}</span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
          {evidence.evidenceType}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">{displayFilePathText(evidence.explanation)}</p>
      <pre className="evidence-snippet mt-2 overflow-x-auto rounded bg-slate-50 p-2">
        <code>{evidence.snippet}</code>
      </pre>
    </div>
  );
}
