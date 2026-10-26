"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { HEATMAP_DEMO, DEMO_LABELS, demoCellClass } from "@/lib/heatmap-demo";

const SCENARIOS = ["岗位匹配", "补证建议", "版本对比"];
export default function HomeScenarioPreview() {
  const [active, setActive] = useState(0);
  const id = useId();
  return <section className="min-w-0 rounded-2xl border border-indigo-100 bg-white p-4 shadow-sm sm:p-5" aria-label="合成示例预览">
    <div role="tablist" aria-label="选择示例场景" className="grid grid-cols-3 gap-1 rounded-xl border border-indigo-100 bg-slate-50 p-1">
      {SCENARIOS.map((label, index) => <button key={label} type="button" role="tab" id={`${id}-tab-${index}`} aria-selected={active === index} aria-controls={`${id}-panel-${index}`} tabIndex={active === index ? 0 : -1}
        className={`min-h-11 rounded-lg px-1 text-xs font-medium sm:text-sm ${active === index ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-indigo-700"}`}
        onClick={() => setActive(index)} onKeyDown={event => {
          const next = event.key === "ArrowRight" ? (active + 1) % 3 : event.key === "ArrowLeft" ? (active + 2) % 3 : event.key === "Home" ? 0 : event.key === "End" ? 2 : null;
          if (next !== null) { event.preventDefault(); setActive(next); document.getElementById(`${id}-tab-${next}`)?.focus(); }
        }}>{label}</button>)}
    </div>
    <div className="mb-4 mt-5 flex items-start justify-between gap-3"><div><h2 className="text-base font-semibold text-slate-950">{active === 0 ? "Python 后端 · 岗位对照" : active === 1 ? "从缺口，到明确的下一步" : "保留旧版，再看新材料"}</h2><p className="mt-1 text-xs leading-5 text-slate-500">{active === 0 ? "先看要求，再看材料支持了什么" : active === 1 ? "建议在你熟悉的开发环境中完成改进" : "概念示意，不是已生成的报告结果"}</p></div><span className="shrink-0 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">合成预览</span></div>
    {SCENARIOS.map((label, index) => <div key={label} role="tabpanel" id={`${id}-panel-${index}`} aria-labelledby={`${id}-tab-${index}`} hidden={active !== index} tabIndex={0}>
      {index === 0 ? <dl className="space-y-2">{HEATMAP_DEMO[0].dimensions.map(d => <div key={d.requirementId} className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-slate-50 p-3"><dt className="text-sm text-slate-700">{d.title}</dt><dd className={`rounded-md border px-2.5 py-1 text-xs font-medium ${demoCellClass(d.verdict)}`}>{DEMO_LABELS[d.verdict]}</dd></div>)}</dl> : index === 1 ? <ol className="space-y-3 text-sm text-slate-700">{[
        ["先核对已有工程", "源码或测试可能已经存在，先查文件与版本，不重复补交。"],
        ["补上直接证据", "若确有缺口，在外部开发环境完善实现与对应验证，保留可定位的材料。"],
        ["完成后上传新版材料", "回到材料页上传，明确选版，再主动重新分析；不用先创建补证任务。"],
      ].map(([title, detail], i) => <li key={title} className="flex gap-3 rounded-xl bg-slate-50 p-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">{i + 1}</span><div><strong className="font-semibold">{title}</strong><p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p></div></li>)}</ol> : <div className="space-y-3"><div className="grid gap-3 sm:grid-cols-2"><div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="text-xs font-semibold text-slate-500">旧版 · 示意</p><p className="mt-2 text-sm font-medium">只提交了经历说明</p><p className="mt-2 text-xs leading-5 text-slate-500">旧报告和原投递保留原材料。</p></div><div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4"><p className="text-xs font-semibold text-indigo-700">新版 · 示意</p><p className="mt-2 text-sm font-medium">增加源码与测试材料</p><p className="mt-2 text-xs leading-5 text-slate-600">重新分析后，逐项核对引用与缺口；不保证等级上升。</p></div></div><p className="rounded-xl bg-slate-50 p-3 text-xs leading-6 text-slate-600">材料版本、来源片段和人工核对，让变化可以追溯。上传输出记录不等于平台独立执行，也不能证明本人贡献。</p></div>}
    </div>)}
    <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-xs leading-5"><p className="text-slate-500">预设合成示意 · 不调用真实 AI · 缺材料不代表没有能力</p><Link href="/demo/heatmap" className="inline-flex min-h-11 items-center font-medium text-indigo-700 underline">体验完整示例 →</Link></div>
  </section>;
}
