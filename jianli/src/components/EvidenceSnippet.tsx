"use client";
import { useRef, useState } from "react";
import { sourceLabel, type SourceLocation, type SourceMaterial } from "@/lib/source-label";
import type { ReportEvidence } from "@/lib/api/domain";

type SnippetSource = SourceLocation & Pick<ReportEvidence, "lineStart" | "lineEnd" | "snippet">
  & Partial<Pick<ReportEvidence, "contextComplete" | "contextNote">>;

export default function EvidenceSnippet({ evidence, materials = [], showContextNote = true, theme = "light" }: { evidence: SnippetSource; materials?: readonly SourceMaterial[]; showContextNote?: boolean; theme?: "light" | "dark" }) {
  const [wrap, setWrap] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [copy, setCopy] = useState("");
  const expandButton = useRef<HTMLButtonElement>(null);
  return <div className={`min-w-0 evidence-snippet${theme === "dark" ? " evidence-reader-dark" : ""}`}>
    {showContextNote && <p className={`mt-2 text-sm leading-6 ${evidence.contextComplete ? "text-slate-500" : "text-amber-800"}`}>
      单个引用片段：{evidence.contextNote || "历史引用未核验上下文完整性"}
    </p>}
    <div className="evidence-code-shell">
      <div className="evidence-code-bar">
        <div className="evidence-code-actions">
          <button type="button" className="btn-quiet" aria-pressed={wrap} onClick={()=>setWrap(value=>!value)}>{wrap ? "换行：开" : "换行：关"}</button>
          <button ref={expandButton} type="button" className="btn-quiet" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?"收起阅读":"展开阅读"}</button>
          <button type="button" className="btn-quiet" onClick={async()=>{try{await navigator.clipboard.writeText(evidence.snippet);setCopy("已复制原文");}catch{setCopy("复制失败，请重试");}}}>复制原文</button>
          <span role="status" className="evidence-code-status">{copy}</span>
        </div>
      </div>
      <pre tabIndex={0} aria-label={`原文 ${sourceLabel(evidence, materials)} 第 ${evidence.lineStart} 至 ${evidence.lineEnd} 行`}
        className={`evidence-code ${expanded?"":"max-h-80"} max-w-full overflow-auto`}>
        <code>{evidence.snippet.split("\n").map((line, index) => <span className={`flex ${wrap?"min-w-0":"min-w-max"}`} key={index}>
          <span aria-hidden="true" className="mr-4 inline-block w-8 shrink-0 select-none text-right text-slate-400">{evidence.lineStart + index}</span><span className={wrap?"min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]":"whitespace-pre"}>{line || " "}</span>
        </span>)}</code>
      </pre>
      {expanded&&<button type="button" className="btn-quiet evidence-code-collapse" onClick={()=>{setExpanded(false);expandButton.current?.focus();}}>收起并返回引用</button>}
    </div>
  </div>;
}
