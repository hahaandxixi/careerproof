"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { reportUploadHref } from "@/lib/report-follow-up";

export default function ReportFollowUpActions({ reportId, requirementId, text, projectVersionId }: { reportId: string; requirementId: string; text: string; projectVersionId?: string }) {
  const [status, setStatus] = useState<"idle" | "copying" | "copied" | "manual">("idle");
  const generation = useRef(0);
  useEffect(() => {
    generation.current += 1; setStatus("idle");
    return () => { generation.current += 1; };
  }, [reportId, requirementId, text]);
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
  return <div className="space-y-3" aria-label="在自己的开发环境补证">
    <div className="flex flex-wrap gap-3">
      <button type="button" className="btn-secondary min-h-11" disabled={status === "copying"} onClick={() => void copy()}>{status === "copying" ? "正在复制…" : "复制补证建议"}</button>
      <Link className="btn inline-flex min-h-11 items-center" href={reportUploadHref(reportId, requirementId, projectVersionId)}>完成后上传新版材料</Link>
    </div>
    <p role="status" className="text-xs leading-6 text-indigo-800">{status === "copied" ? "已复制补证建议，可粘贴到自己的笔记或开发工具。" : status === "manual" ? "浏览器未能复制，请在下方手动选择并复制。" : status === "copying" ? "正在写入剪贴板…" : ""}</p>
    {status === "manual" && <label className="block text-sm text-slate-700">可手动复制的补证建议<textarea readOnly className="field mt-2 min-h-48" value={text} onFocus={event => event.currentTarget.select()} /></label>}
  </div>;
}
