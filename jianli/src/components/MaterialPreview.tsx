"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { ResumePreview, ProjectFileSummary, ProjectFileContent } from "@/lib/api/domain";
import { ErrorNotice } from "./AccessGate";
import VisualEvidencePanel from "./VisualEvidencePanel";

export default function MaterialPreview({ id, kind, initialFileId, initialLineStart, initialLineEnd }: { id: string; kind: "resume" | "project"; initialFileId?: string; initialLineStart?: number; initialLineEnd?: number }) {
  const [resume, setResume] = useState<ResumePreview | null>(null);
  const [files, setFiles] = useState<ProjectFileSummary[]>([]);
  const [selected, setSelected] = useState<ProjectFileContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState("");
  const [error, setError] = useState("");
  const [fileError, setFileError] = useState("");
  const [revision, setRevision] = useState(0);
  const fileRequest = useRef(0);
  useEffect(() => {
    let current = true;
    setLoading(true); setError(""); setSelected(null); setFileError("");
    const load = kind === "resume" ? api.previewResume(id).then(value => { if (current) setResume(value); }) : api.listProjectFiles(id).then(value => {
      if (!current) return;
      setFiles(value);
      if (initialFileId && value.some(file => file.id === initialFileId)) void selectFile(initialFileId);
    });
    load.catch(reason => { if (current) setError(errorMessage(reason)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; fileRequest.current++; };
  }, [kind, id, initialFileId, revision]);
  async function selectFile(fileId: string) {
    const request = ++fileRequest.current;
    setFileLoading(fileId); setFileError(""); setSelected(null);
    try { const value = await api.getProjectFile(fileId); if (request === fileRequest.current) setSelected(value); }
    catch (reason) { if (request === fileRequest.current) setFileError(errorMessage(reason)); }
    finally { if (request === fileRequest.current) setFileLoading(""); }
  }
  useEffect(() => {
    if (selected?.id !== initialFileId || !Number.isInteger(initialLineStart) || (initialLineStart ?? 0) < 1) return;
    document.getElementById(`source-line-${initialLineStart}`)?.scrollIntoView({ block: "center" });
  }, [selected, initialFileId, initialLineStart]);
  return <div className="space-y-6">
    <Link href="/portfolio" className="text-sm text-indigo-600">← 我的材料</Link>
    <div><h1 className="text-2xl font-bold">{kind === "resume" ? "简历解析预览" : "项目 / 作品文本预览"}</h1><p className="mt-2 text-sm leading-6 text-slate-500">核对系统实际读取到的内容。扫描件与图片由本地 OCR 提取文字，识别结果需对照原图。</p></div>
    {!loading && !error && kind === "project" && <VisualEvidencePanel key={id} versionId={id} />}
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {loading && <p className="text-sm text-slate-500">加载解析结果…</p>}
    {!loading && !error && kind === "resume" && <div className="space-y-4">{resume?.sections.length ? resume.sections.map((section, index) => <section className="panel" key={section.id}><h2 className="mb-3 text-sm font-medium">内容段落 {index + 1}{section.pageNumber != null ? ` · 第 ${section.pageNumber} 页` : ""}</h2><pre className="overflow-auto whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">{section.content}</pre></section>) : <p className="panel text-sm text-slate-500">暂无可预览的文字，请在材料列表确认解析是否完成。</p>}</div>}
    {!loading && !error && kind === "project" && <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]"><section className="panel"><h2 className="font-semibold">已解析文件（{files.length}）</h2><ul className="mt-4 max-h-[65vh] space-y-2 overflow-auto">{files.map(file => <li key={file.id}><button className={`w-full rounded-lg p-2 text-left text-xs transition ${selected?.id === file.id || fileLoading === file.id ? "bg-indigo-50 text-indigo-700" : "bg-slate-50 hover:bg-slate-100"}`} onClick={() => void selectFile(file.id)}><span className="block break-all font-medium">{file.relativePath}</span><span className="mt-1 block text-slate-500">{file.lineCount} 行 · {(file.sizeBytes / 1024).toFixed(1)} KB</span></button></li>)}</ul>{!files.length && <p className="mt-3 text-sm text-slate-500">暂无已解析文件。</p>}</section><section className="panel min-w-0">{fileError && <ErrorNotice message={fileError} />}{fileLoading && <p role="status" className="text-sm text-slate-500">正在加载文件…</p>}{selected ? <><h2 className="break-all text-sm font-semibold">{selected.relativePath}</h2><pre className="mt-4 max-h-[65vh] overflow-auto rounded-xl bg-slate-50 p-3 text-xs leading-6"><code>{selected.content.split("\n").map((line, index) => <span key={index} id={`source-line-${index + 1}`} className={`block ${selected.id === initialFileId && Number.isInteger(initialLineStart) && Number.isInteger(initialLineEnd) && index + 1 >= (initialLineStart ?? 0) && index + 1 <= (initialLineEnd ?? 0) ? "rounded bg-amber-100" : ""}`}>{`${String(index + 1).padStart(4)}  ${line}`}</span>)}</code></pre></> : !fileLoading && !fileError && <p className="text-sm text-slate-500">选择文件查看静态文本，不执行上传内容。</p>}</section></div>}
  </div>;
}
