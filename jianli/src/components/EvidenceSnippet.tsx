"use client";
import { useRef, useState } from "react";
import { sourceLabel, type SourceMaterial } from "@/lib/source-label";
import type { ReportEvidence } from "@/lib/api/domain";

export default function EvidenceSnippet({ evidence, materials = [], showContextNote = true }: { evidence: ReportEvidence; materials?: readonly SourceMaterial[]; showContextNote?: boolean }) {
  const [wrap, setWrap] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [copy, setCopy] = useState("");
  const expandButton = useRef<HTMLButtonElement>(null);
  return <div className="min-w-0">
    {showContextNote && <p className={`mt-2 text-sm leading-6 ${evidence.contextComplete ? "text-slate-500" : "text-amber-800"}`}>
      单个引用片段：{evidence.contextNote || "历史引用未核验上下文完整性"}
    </p>}
    <div className="mt-2 flex flex-wrap items-center gap-2"><button type="button" className="btn-quiet" aria-pressed={wrap} onClick={()=>setWrap(value=>!value)}>换行</button><button ref={expandButton} type="button" className="btn-quiet" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?"收起阅读":"展开阅读"}</button><button type="button" className="btn-quiet" onClick={async()=>{try{await navigator.clipboard.writeText(evidence.snippet);setCopy("已复制原文");}catch{setCopy("复制失败，请重试");}}}>复制原文</button><span role="status" className="text-sm text-slate-600">{copy}</span></div>
    <pre aria-label={`原文 ${sourceLabel(evidence, materials)} 第 ${evidence.lineStart} 至 ${evidence.lineEnd} 行`}
      className={`mt-2 ${expanded?"":"max-h-80"} max-w-full overflow-auto rounded-lg bg-slate-50 p-3 text-sm leading-6`}>
      <code>{evidence.snippet.split("\n").map((line, index) => <span className={`flex ${wrap?"min-w-0":"min-w-max"}`} key={index}>
        <span aria-hidden="true" className="mr-4 inline-block w-8 shrink-0 select-none text-right text-slate-400">{evidence.lineStart + index}</span><span className={wrap?"min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]":"whitespace-pre"}>{line || " "}</span>
      </span>)}</code>
    </pre>
    {expanded&&<button type="button" className="btn-quiet mt-2" onClick={()=>{setExpanded(false);expandButton.current?.focus();}}>收起并返回引用</button>}
  </div>;
}
