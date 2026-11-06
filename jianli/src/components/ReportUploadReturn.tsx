"use client";

import { displayJobTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import type { UploadedMaterial } from "@/lib/material-upload";
import { reportFollowUpContext } from "@/lib/report-follow-up";

export default function ReportUploadReturn({ uploaded, onMaterials }: { uploaded?: UploadedMaterial | null; onMaterials?: (materials: MatchReport["materials"] | undefined) => void }) {
  const query = useSearchParams();
  const context = reportFollowUpContext(query);
  const growthTask = query.get("growthTask");
  const reportId = context?.reportId, requirementId = context?.requirementId;
  const [entry, setEntry] = useState<{ reportId: string; report: MatchReport | null; error: string } | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!reportId || !requirementId || growthTask) return;
    let active = true;
    setEntry(null);
    void api.getReport(reportId).then(report => {
      if (active) setEntry({ reportId, report, error: "" });
    }).catch(reason => {
      if (active) setEntry({ reportId, report: null, error: errorMessage(reason) });
    });
    return () => { active = false; };
  }, [reportId, requirementId, growthTask, revision]);
  const current = context && !growthTask && entry?.reportId === reportId ? entry : null;
  const report = current?.report;
  const item = report?.items.find(value => value.requirementId === requirementId);
  const materials = item ? report?.materials : undefined;
  useEffect(() => { onMaterials?.(materials); }, [materials, onMaterials]);
  // The existing growth-task return path keeps its original fixed-baseline contract.
  if (!context || growthTask) return null;
  return <section className="material-followup space-y-3 text-sm" aria-label="补证材料上传与报告接续">
    <h2 className="font-semibold text-slate-950">补证来自这份报告</h2>
    {!current ? <p role="status">正在核对原报告的补证上下文…</p> : current.error ? <div role="alert"><p>原报告暂不可读取：{current.error}</p><button type="button" className="btn-secondary mt-2" onClick={() => setRevision(value => value + 1)}>重试读取原报告</button></div> : !item ? <p role="alert">原报告中未找到对应要求。请从报告重新进入；不会根据链接关联材料。</p> : <>
      <p className="break-words font-medium text-slate-900">{item.requirementTitle}</p>
      <p className="break-words text-slate-600">{displayJobTitle(report!.jobTitle, report!.jobId)}</p>
      <p className="leading-6 text-slate-600">上传新版后，原报告仍引用当时的版本。</p>
      {uploaded && <p role="status" className="leading-6 text-[#173c34]">本次上传已保存，请确认处理完成。之后进入原岗位，明确选择需要分析的简历与项目版本，再主动生成新报告；上传不会自动选择或分析。</p>}
      <div className="flex flex-wrap gap-x-3">
        <Link className="action-link" href={`/reports/${reportId}#requirement-${requirementId}`}>返回原报告这项要求</Link>
        <Link className="action-link" href={`/jobs/${report!.jobId}`}>到原岗位选择版本并重新分析</Link>
      </div>
      <p className="text-xs leading-6 text-slate-600">新报告可读取与同岗位上一份报告的逐项对比；如期间生成过其他报告，请核对实际基准。企业固定快照不会自动更新，AI 外发仍需单独同意。</p>
    </>}
  </section>;
}
