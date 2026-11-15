"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { reportUploadHref } from "@/lib/report-follow-up";

export function CopySupplementAdvice({ text, scope, subject = "补证建议" }: { text: string; scope: string; subject?: string }) {
  const [status, setStatus] = useState<"idle" | "copying" | "copied" | "manual">("idle");
  const generation = useRef(0);
  useEffect(() => {
    generation.current += 1; setStatus("idle");
    return () => { generation.current += 1; };
  }, [scope, text]);
  async function copy() {
    const ticket = ++generation.current;
    setStatus("copying");
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(text);
      if (ticket === generation.current) setStatus("copied");
    } catch {
      if (ticket === generation.current) setStatus("manual");
    }
  }
  return <>
    <button type="button" className="btn-secondary min-h-11" disabled={status === "copying"} onClick={() => void copy()}>{status === "copying" ? "正在复制…" : `复制${subject}`}</button>
    <p role="status" className={status === "idle" ? "sr-only" : "text-sm leading-6 text-[#173c34]"}>{status === "copied" ? `已复制${subject}。` : status === "manual" ? "浏览器未能复制，请在下方手动复制。" : status === "copying" ? "正在复制…" : ""}</p>
    {status === "manual" && <label className="block basis-full text-sm text-slate-700">{`可手动复制的${subject}`}<textarea readOnly className="field mt-2 min-h-48" value={text} onFocus={event => event.currentTarget.select()} /></label>}
  </>;
}

export default function ReportFollowUpActions({ reportId, requirementId, text, projectVersionId }: { reportId: string; requirementId: string; text: string | null; projectVersionId?: string }) {
  return <div className="flex flex-wrap items-center gap-3" aria-label="在自己的开发环境补证">
    {text && <CopySupplementAdvice scope={`${reportId}:${requirementId}`} text={text} />}
    <Link className="btn inline-flex min-h-11 items-center" href={reportUploadHref(reportId, requirementId, projectVersionId)}>{projectVersionId ? "上传新版材料" : "添加项目材料"}</Link>
  </div>;
}
