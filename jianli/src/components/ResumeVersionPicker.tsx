"use client";

import Link from "next/link";
import { useId, useRef, useState } from "react";
import type { ResumeHistory } from "@/lib/api/client";
import { filterResumeMaterials, resumeDisplayCategory } from "@/lib/resume-picker";
import cases from "@/app/demo/samples.json";

const DEMO_TITLES = cases.map(item => item.resumeName);
const GROUPS = [
  { key: "personal", label: "我的其他简历" },
  { key: "demo", label: "职业测试简历 · CP01—CP09" },
  { key: "history", label: "历史验收材料 · 按名称归类" },
] as const;

export default function ResumeVersionPicker({ resumes, selectedId, onChange }: {
  resumes: ResumeHistory[];
  selectedId: string;
  onChange: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [includeHistory, setIncludeHistory] = useState(false);
  const chooser = useRef<HTMLDetailsElement>(null);
  const radioName = useId();
  const all = filterResumeMaterials(resumes, "", true, DEMO_TITLES);
  const visible = filterResumeMaterials(resumes, query, includeHistory, DEMO_TITLES);
  const selectedResume = all.find(resume => resume.versions.some(version => version.id === selectedId));
  const selected = selectedResume?.versions.find(version => version.id === selectedId);
  const historyCount = all.filter(resume => resumeDisplayCategory(resume.title, DEMO_TITLES) === "history").length;

  function choose(id: string) {
    onChange(id);
    if (chooser.current) {
      chooser.current.open = false;
      chooser.current.querySelector("summary")?.focus();
    }
  }

  return <section aria-label="简历版本选择" className="space-y-3">
    <p className="text-sm font-medium">简历版本（选择一份）</p>
    {selected && selectedResume ? <div aria-label="已选简历版本" className="flex items-start justify-between gap-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm">
      <span className="min-w-0 break-words">{selectedResume.title} · 第 {selected.versionNumber} 版
        <span className="mt-1 block text-xs text-slate-600">{selected.originalFilename} · {selected.materialRole === "reference" ? "第三方参考，不计评级" : "个人作品"}</span>
      </span>
      <button type="button" className="shrink-0 text-xs text-indigo-700 underline" onClick={() => onChange("")}>取消选择</button>
    </div> : <p className="text-xs text-slate-500">尚未选择简历；请展开并选择已完成解析的版本，不会自动加入历史材料。</p>}
    {all.length ? <details ref={chooser} className="rounded-xl border border-slate-200">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-indigo-700">{selected ? "更换简历版本" : "选择简历版本"} · {all.length} 份简历</summary>
      <div className="space-y-3 border-t border-slate-200 p-3">
        <label className="block text-xs text-slate-600">搜索简历名称或文件名
          <input className="field mt-1" type="search" value={query} placeholder="如：CP08、数据库、简历.docx" onChange={event => setQuery(event.target.value)} />
        </label>
        {historyCount > 0 && <label className="flex items-start gap-2 text-xs leading-6 text-slate-600">
          <input className="mt-1 shrink-0" type="checkbox" checked={includeHistory} onChange={event => setIncludeHistory(event.target.checked)} />
          <span>显示历史验收材料（{historyCount} 份）；搜索时也会查找这些材料。</span>
        </label>}
        <p className="text-xs leading-6 text-slate-500">选择简历后，再选择同一编号的测试项目。搜索、收起或隐藏历史材料不会更改已选版本。</p>
        {!all.some(resume => resume.category === "demo") && <p className="text-xs leading-6 text-slate-500">当前账号尚无预置职业测试简历。可在<Link href="/demo" className="text-indigo-700 underline">演示指南</Link>下载一套，上传到当前账号；预置材料仅属于初始化时使用的学生演示账号。</p>}
        <div className="max-h-72 space-y-3 overflow-y-auto">
          {GROUPS.map(group => {
            const rows = visible.filter(resume => resume.category === group.key);
            if (group.key === "demo") rows.sort((left, right) => left.title.localeCompare(right.title));
            return rows.length ? <section key={group.key} aria-label={group.label} className="space-y-2">
              <h3 className="text-xs font-semibold text-slate-500">{group.label} · {rows.length} 份</h3>
              {rows.map(resume => <div key={resume.id} className="rounded-lg bg-slate-50 p-3">
                <p className="break-words text-sm font-medium">{resume.title}</p>
                {resume.versions.length === 1 ? renderVersion(resume.versions[0], resume.title) : <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-indigo-700">展开 {resume.versions.length} 个版本{resume.versions.some(version => version.id === selectedId) ? " · 包含已选版本" : ""}</summary>
                  <div className="mt-2 space-y-2">{resume.versions.map(version => renderVersion(version, resume.title))}</div>
                </details>}
              </div>)}
            </section> : null;
          })}
          {!visible.length && <p role="status" className="p-3 text-sm text-slate-500">没有找到匹配的已解析简历。试试其他关键词或显示历史验收材料；已选版本仍保留。</p>}
        </div>
      </div>
    </details> : <p className="text-sm text-amber-700">还没有可用简历，请先<Link href="/portfolio" className="underline">上传并完成解析</Link>。</p>}
  </section>;

  function renderVersion(version: ResumeHistory["versions"][number], title: string) {
    return <label key={version.id} className="mt-2 flex cursor-pointer items-start gap-2 rounded-lg bg-white p-2 text-sm">
      <input className="mt-1 shrink-0" type="radio" name={radioName} aria-label={`${title} 第 ${version.versionNumber} 版 ${version.originalFilename ?? ""}`} checked={selectedId === version.id} onChange={() => choose(version.id)} />
      <span className="min-w-0 break-words">第 {version.versionNumber} 版 · {version.originalFilename}
        <span className="block text-xs text-slate-500">{version.materialRole === "reference" ? "第三方参考，不计评级" : "个人作品"}</span>
      </span>
    </label>;
  }
}
