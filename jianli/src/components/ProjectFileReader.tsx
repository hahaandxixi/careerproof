"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { ProjectFileSummary, ProjectFileContent } from "@/lib/api/domain";
import { ErrorNotice } from "./AccessGate";

export function defaultProjectSource(files: readonly ProjectFileSummary[]) {
  return files.reduce<ProjectFileSummary | undefined>((longest, file) => {
    // The parser tags source languages, and uses Document or null for other files.
    if (!file.language || file.language === "Document" || file.sizeBytes === 0) return longest;
    return !longest || file.lineCount > longest.lineCount ? file : longest;
  }, undefined);
}

export default function ProjectFileReader({
  id, initialFileId, initialLineStart, initialLineEnd, beforeFiles, inReport = false,
}: {
  id: string;
  initialFileId?: string;
  initialLineStart?: number;
  initialLineEnd?: number;
  beforeFiles?: ReactNode;
  inReport?: boolean;
}) {
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
    setLoading(true);
    setError("");
    setSelected(null);
    setFileError("");
    // The list and its file request belong to the same fixed version.
    setFileRequest(null);
    setFileLoading("");
    api.listProjectFiles(id).then(value => {
      if (!current) return;
      setFiles(value);
      const initial = initialFileId && value.some(file => file.id === initialFileId)
        ? initialFileId : inReport ? defaultProjectSource(value)?.id : undefined;
      if (initial) selectFile(initial);
    }).catch(reason => {
      if (current) setError(errorMessage(reason));
    }).finally(() => {
      if (current) setLoading(false);
    });
    return () => { current = false; };
  }, [id, initialFileId, inReport, revision]);

  function selectFile(fileId: string) {
    setFileRequest(previous => ({ fileId, seq: (previous?.seq ?? 0) + 1 }));
  }

  useEffect(() => {
    if (!fileRequest) return;
    let current = true;
    setFileLoading(fileRequest.fileId);
    setFileError("");
    setSelected(null);
    api.getProjectFile(fileRequest.fileId).then(value => {
      if (!current) return;
      if (value.projectVersionId !== id) {
        setFileError("文件与当前项目版本不一致。");
        return;
      }
      setSelected(value);
    }).catch(reason => {
      if (current) setFileError(errorMessage(reason));
    }).finally(() => {
      if (current) setFileLoading("");
    });
    return () => { current = false; };
  }, [fileRequest, id]);

  useEffect(() => {
    if (inReport || selected?.id !== initialFileId || !Number.isInteger(initialLineStart) || (initialLineStart ?? 0) < 1) return;
    document.getElementById("source-line-" + initialLineStart)?.scrollIntoView({ block: "center" });
  }, [selected, initialFileId, initialLineStart, inReport]);

  if (error) return <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />;
  if (loading) return <p role="status" className="text-sm text-slate-500">加载解析结果…</p>;

  const Heading = inReport ? "h4" : "h2";

  return <>
    {beforeFiles}
    {!files.length && inReport
      ? <p className="reading-copy">此版本没有可读源码。</p>
      : <div className={inReport ? "fixed-project-reader" : "grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]"}>
          <section className={inReport ? "min-w-0" : "panel"} aria-label="已解析文件">
            <Heading className="font-semibold">已解析文件（{files.length}）</Heading>
            <ul className={inReport ? "fixed-project-files" : "mt-4 max-h-[65vh] space-y-2 overflow-auto"}>
              {files.map(file => {
                const active = fileRequest?.fileId === file.id;
                return <li key={file.id}>
                  <button type="button" aria-pressed={active}
                    className={"w-full rounded-lg p-2 text-left transition " + (inReport ? "text-sm " : "text-xs ") + (active ? "bg-brand-surface text-brand-hover" : "bg-slate-50 hover:bg-slate-100")}
                    onClick={() => selectFile(file.id)}>
                    <span className="block break-all font-medium">{file.relativePath}</span>
                    <span className="mt-1 block text-slate-500">{file.lineCount} 行 · {(file.sizeBytes / 1024).toFixed(1)} KB</span>
                  </button>
                </li>;
              })}
            </ul>
            {!files.length && <p className="mt-3 text-sm text-slate-500">暂无已解析文件。</p>}
          </section>
          <section className={inReport ? "min-w-0" : "panel min-w-0"} aria-label="文件内容">
            {fileError && fileRequest && <ErrorNotice message={fileError} retry={() => selectFile(fileRequest.fileId)} />}
            {fileLoading ? <p role="status" className="text-sm text-slate-500">正在加载文件…</p> : selected ? <>
              <Heading className="break-all text-sm font-semibold">{selected.relativePath}</Heading>
              <pre tabIndex={0} aria-label={selected.relativePath + " 内容"} className={inReport ? "fixed-project-code" : "mt-4 max-h-[65vh] overflow-auto rounded-xl bg-slate-50 p-3 text-xs leading-6"}>
                <code>{selected.content.split("\n").map((line, index) => {
                  const number = index + 1;
                  const highlighted = selected.id === initialFileId && Number.isInteger(initialLineStart) && Number.isInteger(initialLineEnd) && number >= (initialLineStart ?? 0) && number <= (initialLineEnd ?? 0);
                  return <span key={index} id={inReport ? undefined : "source-line-" + number} className={highlighted ? "block rounded bg-amber-100" : "block"}>{String(number).padStart(4) + "  " + line}</span>;
                })}</code>
              </pre>
            </> : !fileError && <p className="text-sm text-slate-500">{inReport ? "此版本没有可默认打开的源码，可选择其他已解析文件。" : "选择文件查看静态文本，不执行上传内容。"}</p>}
          </section>
        </div>}
  </>;
}
