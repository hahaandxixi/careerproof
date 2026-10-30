"use client";

import { useState } from "react";
import { MATERIAL_ACCEPT, MATERIAL_CONSTRAINTS, materialFileSize, materialFileType, pickMaterialFile, type MaterialKind } from "@/lib/material-upload";

export default function MaterialFileDropzone({ id, kind, file, target, disabled = false, onChange, onError }: {
  id: string; kind: MaterialKind; file: File | null; target: string; disabled?: boolean;
  onChange: (file: File | null) => void; onError: (message: string) => void;
}) {
  const [dragging, setDragging] = useState(false);
  function choose(files: readonly File[]) {
    if (disabled) return;
    const result = pickMaterialFile(kind, files);
    onChange(result.file); onError(result.error);
  }
  return <div className={`rounded-xl border-2 border-dashed p-4 ${dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-slate-50"}`} onDragOver={event => { event.preventDefault(); if (!disabled) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); choose(Array.from(event.dataTransfer.files)); }}>
    <label htmlFor={id} className="block text-sm font-medium text-slate-800">{kind === "resume" ? "简历文件" : "项目压缩包或作品文件"}</label>
    <p className="mt-1 text-sm leading-6 text-slate-600" id={`${id}-help`}>支持拖放。{MATERIAL_CONSTRAINTS[kind]}</p>
    <input id={id} type="file" accept={MATERIAL_ACCEPT[kind]} disabled={disabled} aria-required="true" aria-describedby={`${id}-help ${id}-selected`} className="mt-3 block w-full min-w-0 text-sm text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-100 file:px-3 file:py-2 file:font-medium file:text-indigo-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-indigo-600" onChange={event => choose(Array.from(event.target.files ?? []))} />
    <div id={`${id}-selected`} className="mt-3 space-y-1 break-words text-sm leading-6 text-slate-600" aria-live="polite">
      <p>上传目标：<span className="font-medium text-slate-800">{target}</span></p>
      {file && <><p className="font-medium text-slate-900">{file.name}</p><p>{materialFileSize(file.size)} · {materialFileType(file)}</p>{/\.(pdf|png|jpe?g|webp|bmp)$/i.test(file.name)&&<p>图片及扫描件的文字识别结果需对照原图核对。</p>}</>}
    </div>
  </div>;
}
