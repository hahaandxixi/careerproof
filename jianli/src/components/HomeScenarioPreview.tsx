"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { HEATMAP_DEMO, DEMO_LABELS, demoCellClass } from "@/lib/heatmap-demo";

const SCENARIOS = ["岗位匹配", "补证建议", "版本对比"];
const INTERVAL = 5_000;

export default function HomeScenarioPreview() {
  const [active, setActive] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [playing, setPlaying] = useState(true);
  const [pageVisible, setPageVisible] = useState(true);
  const [resetKey, setResetKey] = useState(0);
  const id = useId();
  const canPlay = playing && !hovered && !focused && pageVisible;
  const gap = HEATMAP_DEMO[0].dimensions.find(item => item.verdict === "gap");

  useEffect(() => {
    const updateVisibility = () => setPageVisible(document.visibilityState !== "hidden");
    updateVisibility();
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  useEffect(() => {
    if (!canPlay) return;
    const timer = setTimeout(() => setActive(value => (value + 1) % SCENARIOS.length), INTERVAL);
    return () => clearTimeout(timer);
  }, [active, canPlay, resetKey]);

  function select(index: number) {
    setActive((index + SCENARIOS.length) % SCENARIOS.length);
    // Choosing the current slide must restart the interval too.
    setResetKey(value => value + 1);
  }

  return <section className="min-w-0 rounded-2xl border border-indigo-100 bg-white p-4 shadow-sm sm:p-5" aria-label="合成示例预览" aria-roledescription="轮播图"
    onPointerEnter={event => { if (event.pointerType !== "touch") setHovered(true); }}
    onPointerLeave={() => setHovered(false)} onFocusCapture={() => setFocused(true)}
    onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false); }}>
    <div role="tablist" aria-label="选择示例场景" className="grid grid-cols-3 gap-1 rounded-xl border border-indigo-100 bg-slate-50 p-1">
      {SCENARIOS.map((label, index) => <button key={label} type="button" role="tab" id={`${id}-tab-${index}`} aria-selected={active === index} aria-controls={`${id}-panel-${index}`} tabIndex={active === index ? 0 : -1}
        className={`min-h-11 rounded-lg px-1 text-xs font-medium sm:text-sm ${active === index ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-indigo-700"}`}
        onClick={() => select(index)} onKeyDown={event => {
          const next = event.key === "ArrowRight" ? (active + 1) % 3 : event.key === "ArrowLeft" ? (active + 2) % 3 : event.key === "Home" ? 0 : event.key === "End" ? 2 : null;
          if (next !== null) { event.preventDefault(); select(next); document.getElementById(`${id}-tab-${next}`)?.focus(); }
        }}>{label}</button>)}
    </div>
    <div className="mt-3 flex items-center justify-between gap-3"><p className="text-xs text-slate-500">从材料，到可以核对的变化</p><span className="shrink-0 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">合成预览</span></div>
    {/* Invisible grid items still size the track; wrapped copy never gets clipped. */}
    <div className="scenario-stage mt-3" aria-live={canPlay ? "off" : "polite"} aria-atomic="true">
      {SCENARIOS.map((label, index) => <div key={label} role="tabpanel" className="scenario-slide" id={`${id}-panel-${index}`} aria-labelledby={`${id}-tab-${index}`} aria-hidden={active !== index} inert={active !== index} data-active={active === index} tabIndex={active === index ? 0 : -1}>
        {index === 0 ? <>
          <h2 className="text-base font-semibold text-slate-950">Python 后端 · 岗位对照</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">先看要求，再看材料支持了什么</p>
          <dl className="mt-3 space-y-1.5">{HEATMAP_DEMO[0].dimensions.map(item => <div key={item.requirementId} className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-slate-50 p-2.5"><dt className="text-sm text-slate-700">{item.title}</dt><dd className={`rounded-md border px-2.5 py-1 text-xs font-medium ${demoCellClass(item.verdict)}`}>{DEMO_LABELS[item.verdict]}</dd></div>)}</dl>
        </> : index === 1 ? <>
          <h2 className="text-base font-semibold text-slate-950">把缺口变成明确的下一步</h2>
          <div className="mb-2 mt-2 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2"><p className="text-xs text-amber-800">当前缺口 · {gap?.title ?? "待核对材料"}</p><p className="mt-1 text-xs leading-5 text-slate-600">先检查已有工程，不重复补交已经存在的证据。</p></div>
          <ol className="space-y-2">{[
            ["核对已有工程", "检查源码、测试与对应版本。"],
            ["在外部补充直接证据", "确有缺口时，完善实现与验证。"],
            ["完成后上传新版材料", "明确选版、主动分析；不用先创建补证任务。"],
          ].map(([title, detail], step) => <li key={title} className="flex gap-3"><span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-indigo-100 bg-indigo-50 text-xs font-semibold text-indigo-700">{step + 1}</span><div className="min-w-0"><h3 className="text-sm font-medium text-slate-800">{title}</h3><p className="mt-0.5 text-xs leading-5 text-slate-500">{detail}</p></div></li>)}</ol>
        </> : <>
          <h2 className="text-base font-semibold text-slate-950">保留 V1，再核对 V2</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">材料对比示意，不是已生成的报告</p>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-3"><p className="text-xs font-semibold text-slate-500">V1 · 原材料</p><div aria-hidden="true" className="mb-3 mt-3 space-y-1.5"><div className="h-1.5 w-4/5 rounded bg-slate-200"/><div className="h-1.5 w-3/5 rounded bg-slate-200"/></div><p className="text-sm font-medium text-slate-700">经历说明</p><p className="mt-2 text-xs leading-5 text-slate-500">旧报告与原投递继续保留。</p></div>
            <div className="min-w-0 rounded-xl border border-indigo-200 bg-indigo-50 p-3"><p className="text-xs font-semibold text-indigo-700">V2 · 新增材料</p><div className="mb-3 mt-3 flex flex-wrap gap-1"><span className="rounded bg-white px-1.5 py-0.5 text-xs text-indigo-700">＋源码</span><span className="rounded bg-white px-1.5 py-0.5 text-xs text-indigo-700">＋测试</span></div><p className="text-sm font-medium text-slate-800">明确选版后分析</p><p className="mt-2 text-xs leading-5 text-slate-600">核对新增引用，不保证等级上升。</p></div>
          </div>
          <p className="mt-3 rounded-xl border border-slate-100 px-3 py-2 text-xs leading-5 text-slate-600"><strong className="font-medium text-indigo-700">来源可追溯</strong> · 保留材料版本与原文片段。上传记录不等于平台独立执行，也不能证明本人贡献。</p>
        </>}
      </div>)}
    </div>
    <div className="mt-3 grid grid-cols-[2.5rem_minmax(0,1fr)_2.5rem_2.5rem] items-center gap-1">
      <button type="button" aria-label="上一个场景" onClick={() => select(active - 1)} className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-indigo-700 hover:bg-indigo-50"><svg aria-hidden="true" viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m12 5-5 5 5 5"/></svg></button>
      <div className="flex items-center justify-center" role="group" aria-label="轮播进度">{SCENARIOS.map((label, index) => <button key={label} type="button" aria-label={`切换到${label}`} aria-pressed={active === index} aria-controls={`${id}-panel-${index}`} onClick={() => select(index)} className="flex h-10 w-8 items-center justify-center rounded-md"><span aria-hidden="true" className={`h-1.5 rounded-full ${active === index ? "w-6 bg-indigo-600" : "w-1.5 bg-slate-300"}`}/></button>)}</div>
      <button type="button" aria-label="下一个场景" onClick={() => select(active + 1)} className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-indigo-700 hover:bg-indigo-50"><svg aria-hidden="true" viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m8 5 5 5-5 5"/></svg></button>
      <button type="button" onClick={() => setPlaying(value => !value)} aria-label={playing ? "暂停自动轮播" : "启用自动轮播"} className="min-h-10 rounded text-xs text-indigo-700 underline underline-offset-4">{playing ? "暂停" : "播放"}</button>
    </div>
    <span className="sr-only">{active + 1} / 3 · {canPlay ? "每 5 秒自动切换" : "已暂停自动切换"}</span>
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-xs leading-5"><p className="text-slate-500">不调用真实 AI · 缺材料不代表没有能力</p><Link href="/demo/heatmap" className="inline-flex min-h-11 items-center font-medium text-indigo-700 underline">体验完整示例 →</Link></div>
  </section>;
}
