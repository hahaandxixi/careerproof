"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { ProjectFileSummary, ProjectFileContent } from "@/lib/api/domain";
import { ErrorNotice } from "./AccessGate";
import VisualEvidencePanel from "./VisualEvidencePanel";

export default function MaterialPreview({ id, initialFileId, initialLineStart, initialLineEnd, reportReturnHref }: { id: string; initialFileId?: string; initialLineStart?: number; initialLineEnd?: number; reportReturnHref?: string }) {
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
    api.listProjectFiles(id).then(value => {
      if (!current) return;
      setFiles(value);
      if (initialFileId && value.some(file => file.id === initialFileId)) selectFile(initialFileId);
    }).catch(reason => { if (current) setError(errorMessage(reason)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [id, initialFileId, revision]);
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
    <div><h1 className="text-2xl font-bold">项目 / 作品文本预览</h1><p className="mt-2 text-sm leading-6 text-slate-500">核对系统实际读取到的内容。扫描件与图片由本地 OCR 提取文字，识别结果需对照原图。</p></div>
    {!loading && !error && <VisualEvidencePanel key={id} versionId={id} />}
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {loading && <p className="text-sm text-slate-500">加载解析结果…</p>}
    {!loading && !error && <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]"><section className="panel"><h2 className="font-semibold">已解析文件（{files.length}）</h2><ul className="mt-4 max-h-[65vh] space-y-2 overflow-auto">{files.map(file => <li key={file.id}><button className={`w-full rounded-lg p-2 text-left text-xs transition ${selected?.id === file.id || fileLoading === file.id ? "bg-indigo-50 text-indigo-700" : "bg-slate-50 hover:bg-slate-100"}`} onClick={() => selectFile(file.id)}><span className="block break-all font-medium">{file.relativePath}</span><span className="mt-1 block text-slate-500">{file.lineCount} 行 · {(file.sizeBytes / 1024).toFixed(1)} KB</span></button></li>)}</ul>{!files.length && <p className="mt-3 text-sm text-slate-500">暂无已解析文件。</p>}</section><section className="panel min-w-0">{fileError && <ErrorNotice message={fileError} />}{fileLoading && <p role="status" className="text-sm text-slate-500">正在加载文件…</p>}{selected ? <><h2 className="break-all text-sm font-semibold">{selected.relativePath}</h2><pre className="mt-4 max-h-[65vh] overflow-auto rounded-xl bg-slate-50 p-3 text-xs leading-6"><code>{selected.content.split("\n").map((line, index) => <span key={index} id={`source-line-${index + 1}`} className={`block ${selected.id === initialFileId && Number.isInteger(initialLineStart) && Number.isInteger(initialLineEnd) && index + 1 >= (initialLineStart ?? 0) && index + 1 <= (initialLineEnd ?? 0) ? "rounded bg-amber-100" : ""}`}>{`${String(index + 1).padStart(4)}  ${line}`}</span>)}</code></pre></> : !fileLoading && !fileError && <p className="text-sm text-slate-500">选择文件查看静态文本，不执行上传内容。</p>}</section></div>}
  </div>;
}
