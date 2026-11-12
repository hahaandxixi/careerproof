"use client";

import { displayJobTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import type { UploadedMaterial } from "@/lib/material-upload";
import { reportFollowUpContext, reportJobHref, reportReanalysisHref } from "@/lib/report-follow-up";

export default function ReportUploadReturn({ uploaded, onMaterials }: { uploaded?: UploadedMaterial | null; onMaterials?: (materials: MatchReport["materials"] | undefined) => void }) {
  const query = useSearchParams();
  const context = reportFollowUpContext(query);
  const growthTask = query.get("growthTask");
  const sourceProjectVersion = query.get("sourceProjectVersion");
  const reportId = context?.reportId, requirementId = context?.requirementId;
  const [entry, setEntry] = useState<{ reportId: string; report: MatchReport | null; error: string } | null>(null);
  const [revision, setRevision] = useState(0);
  const [uploadState, setUploadState] = useState<{ key: string; ready: boolean; message: string; projectVersionIds?: string[] } | null>(null);
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
  useEffect(() => {
    if (!uploaded || !report) { setUploadState(null); return; }
    const key = `${report.id}:${uploaded.kind}:${uploaded.versionId}`;
    // A previous version's completion is never assumed while the new upload is
    // still being checked. Bind every result to this exact report/kind/version.
    setUploadState({ key, ready: false, message: "正在核对本次上传状态…" });
    let active = true, timer: ReturnType<typeof setTimeout> | undefined, attempts = 0;
    const check = async () => {
      attempts += 1;
      try {
        const [resumes, projects] = await Promise.all([api.listResumes(), api.listProjects()]);
        if (!active) return;
        const source = uploaded.kind === "resume"
          ? resumes.find(value => value.versions.some(version => version.id === uploaded.versionId))
          : projects.find(value => value.versions.some(version => version.id === uploaded.versionId));
        const version = source?.versions.find(value => value.id === uploaded.versionId);
        if (!source || !version) {
          setUploadState({ key, ready: false, message: "当前账号材料列表中尚未找到本次上传版本，尚不能重新分析。" });
        } else if (version.status !== "completed") {
          setUploadState({ key, ready: false, message: version.status === "failed" || version.status === "cancelled" ? "本次上传处理失败或已取消，暂不能重新分析。请先修正或重新上传。" : "本次上传仍在处理中；处理完成后再回来确认版本。" });
          if (version.status !== "failed" && version.status !== "cancelled" && attempts < 60) timer = setTimeout(check, 1800);
        } else {
          setUploadState({
            key, ready: true, message: "本次上传已处理完成。",
            projectVersionIds: uploaded.kind === "project" ? source.versions.map(value => value.id) : undefined,
          });
        }
      } catch {
        if (active) {
          setUploadState({ key, ready: false, message: "暂时无法核对本次上传状态，请刷新材料列表后重试。" });
          if (attempts < 60) timer = setTimeout(check, 1800);
        }
      }
    };
    void check();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [uploaded, report]);
  const uploadKey = uploaded && report ? `${report.id}:${uploaded.kind}:${uploaded.versionId}` : "";
  const currentUploadState = uploadState?.key === uploadKey ? uploadState : null;
  const reanalysisHref = uploaded && report && currentUploadState?.ready
    ? reportReanalysisHref(report, uploaded, currentUploadState.projectVersionIds
      ? { versionIds: currentUploadState.projectVersionIds, sourceVersionId: sourceProjectVersion }
      : undefined, requirementId)
    : null;
  // The existing growth-task return path keeps its original fixed-baseline contract.
  if (!context || growthTask) return null;
  return <section className="material-followup space-y-3 text-sm" aria-label="补证材料上传与报告接续">
    <h2 className="font-semibold text-slate-950">补证来自这份报告</h2>
    {!current ? <p role="status">正在核对原报告的补证上下文…</p> : current.error ? <div role="alert"><p>原报告暂不可读取：{current.error}</p><button type="button" className="btn-secondary mt-2" onClick={() => setRevision(value => value + 1)}>重试读取原报告</button></div> : !item ? <p role="alert">原报告中未找到对应要求。请从报告重新进入；不会根据链接关联材料。</p> : <>
      <p className="break-words font-medium text-slate-900">{item.requirementTitle}</p>
      <p className="break-words text-slate-600">{displayJobTitle(report!.jobTitle, report!.jobId)}</p>
      <p className="leading-6 text-slate-600">上传新版后，原报告仍引用当时的版本。</p>
      {uploaded && <p role="status" className={`leading-6 ${currentUploadState?.ready ? "text-[#173c34]" : "text-amber-900"}`}>{currentUploadState?.message || "正在核对本次上传状态…"}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Link className="action-link" href={`/reports/${reportId}#requirement-${requirementId}`}>返回原报告这项要求</Link>
        {reanalysisHref
          ? <Link className="btn inline-flex min-h-11 items-center" href={reanalysisHref}>使用新版材料重新分析 →</Link>
          : <Link className="action-link" href={reportJobHref(report!, requirementId)}>到原岗位手动选择版本</Link>}
      </div>
      <p className="text-xs leading-6 text-slate-600">{reanalysisHref ? "将预选本次上传版本，请在原岗位核对后主动分析。" : "在原岗位选择要使用的版本。"}原报告保留为对比基准。</p>
    </>}
  </section>;
}
