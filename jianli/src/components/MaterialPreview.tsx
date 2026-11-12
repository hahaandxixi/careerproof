"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { ResumePreview, ProjectFileSummary, ProjectFileContent } from "@/lib/api/domain";
import { displayMaterialTitle } from "@/lib/demo-display-identity.js";
import { ErrorNotice } from "./AccessGate";
import VisualEvidencePanel from "./VisualEvidencePanel";

const SECTION_LABEL: Readonly<Record<string, string>> = {
  page: "PDF 文本",
  ocr_page: "页面 OCR 文本",
  document: "文档正文",
  ocr_image: "图片 OCR 文本",
};

const RESUME_STATUS: Readonly<Record<string, string>> = {
  pending: "等待解析",
  running: "正在解析",
  failed: "解析失败",
  cancelled: "解析已取消",
};

function ResumeContent({ resume }: { resume: ResumePreview }) {
  const ready = resume.status === "completed";
  const failed = resume.status === "failed";
  return <article className="workspace-sheet mx-auto max-w-4xl px-6 py-5 lg:px-8">
    <header className="border-b border-slate-200 pb-4">
      <h1 className="page-title [overflow-wrap:anywhere]">{displayMaterialTitle(resume.title, resume.id)}</h1>
      <p className="mt-2 text-sm leading-6 text-slate-600 [overflow-wrap:anywhere]">
        第 {resume.versionNumber} 版 <span aria-hidden="true">·</span> {resume.originalFilename ?? "原文件名未记录"}
      </p>
      {!ready && <p role={failed ? "alert" : "status"} className={`mt-2 text-sm ${failed ? "text-rose-700" : "text-slate-600"}`}>
        {RESUME_STATUS[resume.status] ?? "解析状态待确认"}
      </p>}
    </header>
    {resume.sections.length ? <div className="divide-y divide-slate-200" aria-label="解析内容">
      {resume.sections.map(section => <section className="py-4" key={section.id}>
        <h2 className="mb-2 text-sm font-semibold text-slate-600">
          {SECTION_LABEL[section.sectionType] ?? "解析文本"}
          {section.pageNumber != null && ` · 第 ${section.pageNumber} 页`}
        </h2>
        <p className="whitespace-pre-wrap text-base leading-7 text-slate-800 [overflow-wrap:anywhere]">{section.content}</p>
      </section>)}
    </div> : <p className="pt-4 text-sm text-slate-600">
      {ready ? "此版本没有提取到可预览的文字。" : "此版本暂没有可预览的文字。"}
    </p>}
  </article>;
}

export default function MaterialPreview({ id, kind, initialFileId, initialLineStart, initialLineEnd, reportReturnHref }: { id: string; kind: "resume" | "project"; initialFileId?: string; initialLineStart?: number; initialLineEnd?: number; reportReturnHref?: string }) {
  const [resume, setResume] = useState<{ requestedId: string; data: ResumePreview } | null>(null);
  const [files, setFiles] = useState<ProjectFileSummary[]>([]);
  const [selected, setSelected] = useState<ProjectFileContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState("");
  const [error, setError] = useState("");
  const [fileError, setFileError] = useState("");
  const [revision, setRevision] = useState(0);
  const [fileRequest, setFileRequest] = useState<{ fileId: string; seq: number } | null>(null);
  useEffect(() => {
    let current = true;
    setLoading(true); setError(""); setSelected(null); setFileError("");
    // A pending file request belongs to the previous context. Clearing it revokes that
    // request (its cleanup flips `current`), and the file-level loading indicator must be
    // reset here too: the revoked request's own `finally` never runs, so without this the
    // previous "正在加载文件…" would survive into a material that has no file selected.
    setFileRequest(null);
    setFileLoading("");
    const load = kind === "resume" ? api.previewResume(id).then(data => { if (current) setResume({ requestedId: id, data }); }) : api.listProjectFiles(id).then(value => {
      if (!current) return;
      setFiles(value);
      if (initialFileId && value.some(file => file.id === initialFileId)) selectFile(initialFileId);
    });
    load.catch(reason => { if (current) setError(errorMessage(reason)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [kind, id, initialFileId, revision]);
  function selectFile(fileId: string) {
    // 每次点击都生成新请求对象：重复点击同一文件也会重新加载。
    setFileRequest(previous => ({ fileId, seq: (previous?.seq ?? 0) + 1 }));
  }
  useEffect(() => {
    if (!fileRequest) return;
    let current = true;
    setFileLoading(fileRequest.fileId); setFileError(""); setSelected(null);
    void api.getProjectFile(fileRequest.fileId)
      .then(value => { if (current) setSelected(value); })
      .catch(reason => { if (current) setFileError(errorMessage(reason)); })
      .finally(() => { if (current) setFileLoading(""); });
    return () => { current = false; };
  }, [fileRequest]);
  useEffect(() => {
    if (selected?.id !== initialFileId || !Number.isInteger(initialLineStart) || (initialLineStart ?? 0) < 1) return;
    document.getElementById(`source-line-${initialLineStart}`)?.scrollIntoView({ block: "center" });
  }, [selected, initialFileId, initialLineStart]);
  return <div className="space-y-6">
    {reportReturnHref && <nav aria-label="返回">
      <Link href={reportReturnHref} className="btn-secondary btn-compact">← {reportReturnHref.includes("#report-materials") ? "返回报告材料" : "返回报告 · 这项要求"}</Link>
    </nav>}
    {kind === "project" && <div><h1 className="text-2xl font-bold">项目 / 作品文本预览</h1><p className="mt-2 text-sm leading-6 text-slate-500">核对系统实际读取到的内容。扫描件与图片由本地 OCR 提取文字，识别结果需对照原图。</p></div>}
    {kind === "resume" && (loading || error) && <h1 className="text-2xl font-bold">简历解析预览</h1>}
    {!loading && !error && kind === "project" && <VisualEvidencePanel key={id} versionId={id} />}
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {loading && <p className="text-sm text-slate-500">加载解析结果…</p>}
    {!loading && !error && kind === "resume" && resume?.requestedId === id && <ResumeContent resume={resume.data} />}
    {!loading && !error && kind === "project" && <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]"><section className="panel"><h2 className="font-semibold">已解析文件（{files.length}）</h2><ul className="mt-4 max-h-[65vh] space-y-2 overflow-auto">{files.map(file => <li key={file.id}><button className={`w-full rounded-lg p-2 text-left text-xs transition ${selected?.id === file.id || fileLoading === file.id ? "bg-indigo-50 text-indigo-700" : "bg-slate-50 hover:bg-slate-100"}`} onClick={() => selectFile(file.id)}><span className="block break-all font-medium">{file.relativePath}</span><span className="mt-1 block text-slate-500">{file.lineCount} 行 · {(file.sizeBytes / 1024).toFixed(1)} KB</span></button></li>)}</ul>{!files.length && <p className="mt-3 text-sm text-slate-500">暂无已解析文件。</p>}</section><section className="panel min-w-0">{fileError && <ErrorNotice message={fileError} />}{fileLoading && <p role="status" className="text-sm text-slate-500">正在加载文件…</p>}{selected ? <><h2 className="break-all text-sm font-semibold">{selected.relativePath}</h2><pre className="mt-4 max-h-[65vh] overflow-auto rounded-xl bg-slate-50 p-3 text-xs leading-6"><code>{selected.content.split("\n").map((line, index) => <span key={index} id={`source-line-${index + 1}`} className={`block ${selected.id === initialFileId && Number.isInteger(initialLineStart) && Number.isInteger(initialLineEnd) && index + 1 >= (initialLineStart ?? 0) && index + 1 <= (initialLineEnd ?? 0) ? "rounded bg-amber-100" : ""}`}>{`${String(index + 1).padStart(4)}  ${line}`}</span>)}</code></pre></> : !fileLoading && !fileError && <p className="text-sm text-slate-500">选择文件查看静态文本，不执行上传内容。</p>}</section></div>}
  </div>;
}
