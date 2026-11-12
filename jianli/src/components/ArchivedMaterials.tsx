"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { displayMaterialTitle } from "@/lib/demo-display-identity.js";

type ArchivedItem = { id: string; name: string; kind: "resume" | "project" };

export default function ArchivedMaterials({ onRestore }: { onRestore: () => void }) {
  const [items, setItems] = useState<ArchivedItem[]>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const restoring = useRef(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const [resumes, projects] = await Promise.all([api.listResumes(true), api.listProjects(true)]);
      setItems([
        ...resumes.filter(item => item.isArchived).map(item => ({ id: item.id, name: item.title, kind: "resume" as const })),
        ...projects.filter(item => item.isArchived).map(item => ({ id: item.id, name: item.name, kind: "project" as const })),
      ]);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function restore(item: ArchivedItem) {
    if (restoring.current) return;
    restoring.current = true;
    setBusy(true);
    setError("");
    try {
      await api.archiveMaterial(item.kind, item.id, false);
      setItems(current => current?.filter(value => value.id !== item.id || value.kind !== item.kind));
      onRestore();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      restoring.current = false;
      setBusy(false);
    }
  }

  return <div className="space-y-2 py-3 text-sm">
    {busy && <p role="status" className="text-slate-600">{items ? "正在恢复材料…" : "正在读取归档材料…"}</p>}
    {error && <div className="flex flex-wrap items-center gap-2">
      <p role="alert" className="text-rose-700">{error}</p>
      {!items && <button type="button" className="btn-secondary" onClick={() => void load()}>重试读取</button>}
    </div>}
    {!!items?.length && <>
      <p className="text-slate-600">已归档 {items.length} 项</p>
      <ul className="divide-y divide-slate-200">
        {items.map(item => <li key={item.kind + ":" + item.id} className="flex items-center justify-between gap-3 py-2">
          <span className="min-w-0 break-words">{displayMaterialTitle(item.name, item.id)} <span className="text-slate-600">· {item.kind === "resume" ? "简历" : "项目"}</span></span>
          <button type="button" className="btn-secondary shrink-0" disabled={busy} onClick={() => void restore(item)}>恢复到材料库</button>
        </li>)}
      </ul>
    </>}
    {items?.length === 0 && !busy && !error && <p className="text-slate-600">暂无归档材料。</p>}
  </div>;
}
