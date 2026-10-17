"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { ReportSummary } from "@/lib/api/domain";
import { useAuth } from "./AuthProvider";
import { ErrorNotice } from "./AccessGate";
import ListPagination from "./ListPagination";
import type { Page } from "@/lib/api/domain";

export default function ReportList() {
  const { user } = useAuth();
  const [data, setData] = useState<Page<ReportSummary> | null>(null);
  const reports = data?.items;
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let current = true;
    setError(""); setLoading(true); setData(null);
    api.listReports(page, 20).then(value => { if (current) { if (value.page !== page) setPage(value.page); else setData(value); } })
      .catch(reason => { if (current) setError(errorMessage(reason)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [revision, page, user?.id]);
  return <div className="space-y-6"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-sm text-indigo-600">持久保存 · 固定材料版本</p><h1 className="mt-1 text-3xl font-bold">匹配报告</h1></div><div className="flex flex-wrap gap-3">{user?.role === "student" && <Link className="btn-secondary" href="/applications">我的投递进度</Link>}<Link className="btn-secondary" href="/jobs">浏览岗位</Link></div></div>
    {error && <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />}
    {loading && <p role="status" className="text-sm text-slate-500">正在加载报告…</p>}
    {!loading && !error && reports?.length === 0 && <div className="panel py-10 text-center text-slate-500">{page > 1 ? "没有更多报告，可以返回上一页。" : "还没有匹配报告。选择一个岗位，用已上传的材料生成报告，再决定是否投递。"}{page === 1 && <Link className="mt-4 block text-indigo-700 underline" href="/jobs">去选择岗位 →</Link>}</div>}
    <div className="space-y-3" aria-busy={loading}>{reports?.map(report => <Link href={`/reports/${report.id}`} key={report.id} className="panel flex flex-wrap items-center justify-between gap-4 transition hover:border-indigo-300"><div className="min-w-0 flex-1"><h2 className="font-semibold">{report.jobTitle}</h2><p className="mt-1 text-xs text-slate-500">{report.candidateName} · {new Date(report.createdAt).toLocaleString("zh-CN")}</p><p className="mt-3 line-clamp-2 text-sm text-slate-600">{report.summary.replace("分数为材料支持度，不是能力或录用结论。", "评级描述材料证据，不是能力或录用结论。").replace("暂不支持评估且不计分", "暂不支持评估且不评级")}</p></div><div className="shrink-0 text-right"><strong className="text-sm text-indigo-600">查看逐项评级 →</strong><p className="mt-1 text-xs text-slate-500">实践证据与缺口</p></div></Link>)}</div>
    {data && <ListPagination label="报告分页" value={data} busy={loading} onPage={setPage} />}
  </div>;
}
