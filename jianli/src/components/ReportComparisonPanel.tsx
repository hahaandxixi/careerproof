"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { MatchReport, ReportComparison } from "@/lib/api/domain";
import ReportComparisonView from "./ReportComparisonView";

export default function ReportComparisonPanel({ reportId, revision }: { reportId: string; revision: string }) {
  const generation = useRef(0);
  const [value, setValue] = useState<{ comparison: ReportComparison; base: MatchReport; current: MatchReport } | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { generation.current += 1; setValue(null); setLoaded(false); setError(""); setBusy(false);
    return () => { generation.current += 1; };
  }, [reportId, revision]);
  async function load() {
    const requestGeneration = generation.current;
    setBusy(true); setError("");
    try {
      const comparison = await api.previousComparison(reportId);
      if (requestGeneration !== generation.current) return;
      const reports = comparison ? await Promise.all([api.getReport(comparison.baseId), api.getReport(comparison.targetId)]) : null;
      if (requestGeneration === generation.current) {
        setValue(comparison && reports ? { comparison, base: reports[0], current: reports[1] } : null);
        setLoaded(true);
      }
    }
    catch (reason) { if (requestGeneration === generation.current) setError(errorMessage(reason)); }
    finally { if (requestGeneration === generation.current) setBusy(false); }
  }
  return <section className="panel min-w-0 space-y-4">
    <div><h2 className="font-semibold">证据变化与补证进度</h2><p className="mt-2 text-sm text-slate-600">与同一岗位最近一份更早的报告比较；读取已有结果，不调用模型。</p></div>
    <button className="btn-secondary" disabled={busy} onClick={load}>{busy ? "读取对比…" : "与上一份报告对比"}</button>
    {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
    {loaded && !value && <p className="text-sm text-slate-500">尚无同一岗位的更早报告。完成补证并重新分析后，可以在新报告中查看变化。</p>}
    {value && <ReportComparisonView key={`${value.comparison.baseId}:${value.comparison.targetId}`} value={value.comparison} base={value.base} current={value.current} />}
  </section>;
}
