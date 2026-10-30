"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { GrowthTask, PrivateAnswerDraft } from "@/lib/api/domain";
import { useAuth } from "./AuthProvider";
import ListPagination from "./ListPagination";
import GrowthComparison from "./GrowthComparison";

// Compatibility for saved task URLs. This surface only reads existing records.
export default function GrowthHistory({ id }: { id?: string }) {
  const { user } = useAuth();
  return <History key={`${user?.id}:${id}`} id={id} />;
}

function History({ id }: { id?: string }) {
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.listGrowthTasks>> | null>(null);
  const [task, setTask] = useState<GrowthTask | null>(null);
  const [draft, setDraft] = useState<PrivateAnswerDraft | null>(null);
  const [error, setError] = useState("");
  const [draftError, setDraftError] = useState("");
  const [busy, setBusy] = useState(true);
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    let generation = 0;
    const read = () => {
      const ticket = ++generation;
      setTask(null); setResult(null); setDraft(null); setError(""); setDraftError("");
      const isHidden = document.visibilityState === "hidden";
      setHidden(isHidden); setBusy(!isHidden);
      if (isHidden) return;
      const operation = id ? api.growthTask(id).then(value => setTaskIfCurrent(value)) : api.listGrowthTasks(page, 20).then(value => { if (ticket === generation) setResult(value); });
      function setTaskIfCurrent(value: GrowthTask) {
        if (ticket !== generation) return;
        setTask(value);
        void api.getAnswerDraft(value.id).then(value => { if (ticket === generation) setDraft(value); }).catch(reason => { if (ticket === generation) setDraftError(errorMessage(reason)); });
      }
      void operation.catch(reason => { if (ticket === generation) setError(errorMessage(reason)); }).finally(() => { if (ticket === generation) setBusy(false); });
    };
    read(); document.addEventListener("visibilitychange", read);
    return () => { ++generation; document.removeEventListener("visibilitychange", read); };
  }, [id, page, revision]);
  if (hidden) return null;
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="page-title">历史补证记录</h1><button type="button" className="btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>刷新</button></div>
    <p className="text-sm text-slate-600">只读记录。继续完善材料，请从报告进入上传。</p>
    <Link className="btn-secondary" href="/reports">我的报告</Link>
    {busy && <p role="status">正在读取…</p>}{error && <p role="alert" className="text-rose-700">{error}</p>}
    {result && <><ul className="space-y-3">{result.items.map(value => <li className="panel" key={value.id}><Link className="font-medium text-indigo-700" href={`/growth/${value.id}`}>{value.requirementTitle}</Link><p className="mt-1 text-sm text-slate-600">{value.jobTitle} · {new Date(value.createdAt).toLocaleString("zh-CN")}</p></li>)}</ul>{result.total === 0 && <p>暂无历史记录。</p>}{result.unavailableCount > 0 && <p role="status" className="text-amber-800">本页 {result.unavailableCount} 条记录暂不可读，可刷新重试。</p>}<ListPagination label="历史补证分页" value={result} busy={busy} onPage={setPage} /></>}
    {task && <>
      <section className="panel space-y-3"><h2 className="text-lg font-semibold">{task.requirementTitle}</h2><p>{task.jobTitle}</p><p className="whitespace-pre-wrap">{task.gap}</p><p className="whitespace-pre-wrap">{task.originalAction}</p><Link className="btn-secondary" href={`/reports/${task.baseReportId}#requirement-${task.requirementId}`}>原报告</Link>{task.targetReportId && <Link className="btn-secondary ml-3" href={`/reports/${task.targetReportId}`}>后续报告</Link>}
        {task.actionNeedsRecheck && <p role="alert" className="text-amber-800">原建议需重新核对。{task.taskPlanWarning}</p>}
        <details><summary className="cursor-pointer py-2">保存的计划与材料</summary><p>{task.plan.deliverable}</p><ol className="list-decimal pl-5">{task.plan.steps.map((step, i) => <li key={i}>{step}</li>)}</ol><ul className="mt-2 list-disc pl-5">{task.plan.acceptanceChecks.map((check, i) => <li key={i}>{check}</li>)}</ul><ul className="mt-3 space-y-2">{task.materials.map(material => <li key={material.id}><Link className="text-indigo-700" href={`/materials/${material.kind}/${material.id}`}>{material.title} · 第 {material.versionNumber} 版</Link></li>)}</ul></details>
      </section>
      {task.comparison && <GrowthComparison task={task} />}
      {draft && <details className="panel"><summary className="cursor-pointer">已保存的私人草稿</summary><p className="mt-3 whitespace-pre-wrap">{draft.text}</p></details>}
      {draftError && <p role="alert" className="text-rose-700">私人草稿暂不可读：{draftError}</p>}
      {task.analysisError && <p role="alert" className="text-rose-700">当时分析未完成：{task.analysisError}</p>}
    </>}
  </div>;
}
