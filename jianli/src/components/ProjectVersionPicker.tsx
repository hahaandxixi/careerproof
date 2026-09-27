"use client";

import Link from "next/link";
import { useState } from "react";
import type { ProjectHistory } from "@/lib/api/client";
import { filterMaterialProjects, toggleMaterialVersion } from "@/lib/material-picker";

export default function ProjectVersionPicker({ projects, selectedIds, onChange }: {
  projects: ProjectHistory[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const visibleProjects = filterMaterialProjects(projects, query);
  const selectableProjects = filterMaterialProjects(projects, "");
  const selected = selectableProjects.flatMap(project => project.versions
    .filter(version => selectedIds.includes(version.id)).map(version => ({ ...version, name: project.name })));

  return <section aria-label="项目或作品版本选择" className="space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm font-medium">项目或作品版本（最多 10 项，可不选）</p>
      <span className="text-xs text-slate-500">已选 {selectedIds.length}/10</span>
    </div>
    {selected.length > 0 ? <ul aria-label="已选项目版本" className="space-y-2">
      {selected.map(version => <li key={version.id} className="flex items-start justify-between gap-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm">
        <span className="min-w-0 break-words">{version.name} · 第 {version.versionNumber} 版
          <span className="mt-1 block text-xs text-slate-600">{version.originalFilename} · {version.materialRole === "reference" ? "第三方参考，不计评级" : "个人作品"}</span>
        </span>
        <button type="button" className="shrink-0 text-xs text-indigo-700 underline" aria-label={`移除 ${version.name} 第 ${version.versionNumber} 版`} onClick={() => onChange(toggleMaterialVersion(selectedIds, version.id, false))}>移除</button>
      </li>)}
    </ul> : <p className="text-xs text-slate-500">尚未选择项目；展开列表选择，不会自动加入历史版本。</p>}
    {selectableProjects.length > 0 ? <details className="rounded-xl border border-slate-200">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-indigo-700">选择或更换项目版本 · {selectableProjects.length} 个项目</summary>
      <div className="space-y-3 border-t border-slate-200 p-3">
        <label className="block text-xs text-slate-600">搜索项目名称或文件名
          <input className="field mt-1" type="search" value={query} placeholder="如：后端项目、app.zip" onChange={event => setQuery(event.target.value)} />
        </label>
        <p className="text-xs text-slate-500">展开项目查看已完成解析的版本。可选不同版本做对照；收起或搜索不会取消已选项。</p>
        {selectedIds.length >= 10 && <p role="status" className="text-xs text-amber-700">已选满 10 项，请先移除一项再添加。</p>}
        <div className="max-h-72 space-y-2 overflow-y-auto">
          {visibleProjects.map(project => <details key={project.id} className="rounded-lg bg-slate-50">
            <summary className="cursor-pointer p-3 text-sm font-medium break-words">{project.name}
              <span className="ml-2 text-xs font-normal text-slate-500">{project.versions.length} 个版本 · 已选 {project.versions.filter(version => selectedIds.includes(version.id)).length}</span>
            </summary>
            <div className="space-y-2 px-3 pb-3">
              {project.versions.map(version => <label key={version.id} className="flex items-start gap-2 rounded-lg bg-white p-2 text-sm">
                <input className="mt-1 shrink-0" type="checkbox" checked={selectedIds.includes(version.id)} disabled={!selectedIds.includes(version.id) && selectedIds.length >= 10} onChange={event => onChange(toggleMaterialVersion(selectedIds, version.id, event.target.checked))} />
                <span className="min-w-0 break-words">第 {version.versionNumber} 版 · {version.originalFilename} · {version.materialRole === "reference" ? "第三方参考，不计评级" : "个人作品"}</span>
              </label>)}
            </div>
          </details>)}
          {!visibleProjects.length && <p role="status" className="p-3 text-sm text-slate-500">没有找到已解析的匹配项目。可以更换关键词；已选材料仍保留。</p>}
        </div>
      </div>
    </details> : <p className="text-sm text-slate-500">暂无完成解析的项目或作品，可以先<Link className="text-indigo-600 underline" href="/portfolio">上传材料</Link>。</p>}
  </section>;
}
