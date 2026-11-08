"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { HEATMAP_DEMO, DEMO_LABELS, demoCellClass } from "@/lib/heatmap-demo";

const SCENARIOS = ["岗位匹配", "补证建议", "版本对比"];
const requirements = HEATMAP_DEMO[0].dimensions;

export default function HomeScenarioPreview() {
  const [active, setActive] = useState(0);
  const id = useId();
  const gap = requirements.find(item => item.verdict === "gap");
  const panels = [
    <dl key="matching" className="divide-y divide-slate-200">
      {requirements.map(item => <div key={item.requirementId} className="flex flex-wrap items-center justify-between gap-2 py-3">
        <dt className="text-base text-slate-700">{item.title}</dt>
        <dd className={`rounded border px-2 py-1 text-xs font-medium ${demoCellClass(item.verdict)}`}>{DEMO_LABELS[item.verdict]}</dd>
      </div>)}
    </dl>,
    <div key="follow-up" className="space-y-2 py-2 text-sm leading-6 text-slate-700">
      <p className="font-semibold">当前缺口 · {gap?.title}</p>
      <ol className="list-decimal space-y-1 pl-5">
        <li>检查当前项目版本是否已有测试和运行记录。</li>
        <li>补齐缺失的用例，保留能定位到具体版本的执行记录。</li>
        <li>上传新版，选择该版本重新分析。</li>
      </ol>
    </div>,
    <div key="versions" className="space-y-2 py-2 text-sm leading-6 text-slate-700">
      <dl className="divide-y divide-slate-200">
        <div className="grid grid-cols-[4rem_1fr] gap-2 py-2"><dt className="font-semibold">V1</dt><dd>项目实现，缺少测试运行记录。</dd></div>
        <div className="grid grid-cols-[4rem_1fr] gap-2 py-2"><dt className="font-semibold">V2</dt><dd>补充测试与执行记录，待核对新增引用。</dd></div>
      </dl>
      <p className="text-slate-600">对比的是材料证据变化。旧报告和原投递保留原版本。</p>
    </div>,
  ];

  return <section aria-labelledby={`${id}-title`} className="home-sample">
    <div className="flex flex-wrap items-center justify-between gap-x-4">
      <h2 id={`${id}-title`} className="section-title">Python 后端 · 岗位证据</h2>
      <Link href="/demo/heatmap" className="scenario-comparison-entry">查看完整对照 →</Link>
    </div>
    <div role="tablist" aria-label="切换功能场景" className="flex flex-wrap gap-x-5 border-b border-slate-200">
      {SCENARIOS.map((label, index) => <button key={label} type="button" role="tab" id={`${id}-tab-${index}`} aria-selected={active === index} aria-controls={`${id}-panel-${index}`} tabIndex={active === index ? 0 : -1}
        className={`min-h-11 border-b-2 px-1 text-sm ${active === index ? "border-[#1d4a40] font-semibold text-[#173c34]" : "border-transparent text-slate-600 hover:text-[#1d4a40]"}`}
        onClick={() => setActive(index)} onKeyDown={event => {
          const count = SCENARIOS.length;
          const next = event.key === "ArrowRight" ? (index + 1) % count : event.key === "ArrowLeft" ? (index + count - 1) % count : event.key === "Home" ? 0 : event.key === "End" ? count - 1 : null;
          if (next !== null) { event.preventDefault(); setActive(next); document.getElementById(`${id}-tab-${next}`)?.focus(); }
        }}>{label}</button>)}
    </div>
    <div className="grid min-w-0">
      {panels.map((panel, index) => <div key={SCENARIOS[index]} role="tabpanel" className={`col-start-1 row-start-1 min-w-0 ${active === index ? "" : "invisible"}`} id={`${id}-panel-${index}`} aria-labelledby={`${id}-tab-${index}`} aria-hidden={active !== index} inert={active !== index} tabIndex={active === index ? 0 : -1}>{panel}</div>)}
    </div>
    <details className="border-t border-slate-200 pt-2 text-sm text-slate-600"><summary className="disclosure">数据说明</summary><p className="pt-1 leading-6">当前为交互样例，使用虚构资料，不调用模型。</p></details>
  </section>;
}

