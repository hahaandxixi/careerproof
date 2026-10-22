"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { ProjectHistory, ResumeHistory } from "@/lib/api/client";
import { growthUploadReturnHref, materialVersionTime, uploadedMaterialFromQuery, type UploadedMaterial } from "@/lib/material-upload";
import ResumeVersionPicker from "./ResumeVersionPicker";
import ProjectVersionPicker from "./ProjectVersionPicker";

export default function GrowthUploadReturn({ uploaded }: { uploaded?: UploadedMaterial | null }) {
  const id = useSearchParams().get("growthTask");
  if (!id || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) return null;
  return <aside className="panel space-y-2 border-indigo-200 text-sm"><p>正在为补证任务准备材料。给原项目上传具名新版，旧材料与企业投递不被覆盖；解析完成后回任务明确选择版本。</p>{uploaded && <p role="status" className="text-indigo-800">本次上传已保存。回到任务后会提示对应版本；仍需自行选择并确认保存，不会自动生成报告。</p>}<Link className="text-indigo-700 underline" href={growthUploadReturnHref(id, uploaded)}>返回补证任务并读取材料 →</Link></aside>;
}

// Search parameters are navigation hints, never selection or permission data.
// Render the hint only after matching it against the current user's API list.
export function GrowthMaterialReview({ resumes, projects, resumeId, projectIds, onResumeChange, onProjectsChange }: {
  resumes: ResumeHistory[]; projects: ProjectHistory[]; resumeId: string; projectIds: string[];
  onResumeChange: (id: string) => void; onProjectsChange: (ids: string[]) => void;
}) {
  const uploaded = uploadedMaterialFromQuery(useSearchParams());
  const source = uploaded?.kind === "resume"
    ? resumes.find(value => value.versions.some(version => version.id === uploaded.versionId))
    : uploaded?.kind === "project" ? projects.find(value => value.versions.some(version => version.id === uploaded.versionId)) : null;
  const version = source?.versions.find(value => value.id === uploaded?.versionId);
  const selected = uploaded?.kind === "resume" ? resumeId === uploaded.versionId : !!uploaded && projectIds.includes(uploaded.versionId);
  return <>
    {uploaded && <aside className="space-y-2 rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-sm" aria-label="刚上传的补证版本">
      {source && version ? <><p className="break-words font-medium text-indigo-900">刚上传：{"title" in source ? source.title : source.name} · 第 {version.versionNumber} 版 · {version.originalFilename}</p>{materialVersionTime(version.createdAt) && <p className="text-xs text-slate-600"><time dateTime={version.createdAt}>上传于 {materialVersionTime(version.createdAt)}</time></p>}<p className="leading-6 text-slate-700">{version.status === "completed" ? selected ? "已加入当前选择；请核对下方已保存记录，再确认保存。" : "解析已完成，尚未加入当前选择。请在下方明确选择，核对后保存。" : version.status === "failed" || version.status === "cancelled" ? "该版本未完成解析，暂不可选择。请回材料中心查看原因或重试。" : "该版本正在处理，暂不可选择。处理完成后点击“读取已保存任务”刷新材料。"}</p></> : <p className="leading-6 text-slate-700">尚未在当前账号材料列表中找到返回的版本。请读取已保存任务；页面不会根据链接自动关联材料。</p>}
    </aside>}
    <ResumeVersionPicker resumes={resumes} selectedId={resumeId} onChange={onResumeChange} />
    <ProjectVersionPicker projects={projects} selectedIds={projectIds} onChange={onProjectsChange} highlightedVersionId={uploaded?.kind === "project" && version ? uploaded.versionId : undefined} />
  </>;
}
