import Link from "next/link";
import HomeWorkspace from "@/components/HomeWorkspace";
import { Suspense } from "react";
import HomeScenarioPreview from "@/components/HomeScenarioPreview";
import JobDiscovery from "@/components/JobDiscovery";

const routeEntry = "inline-flex min-h-11 items-center text-sm font-medium text-indigo-700 underline-offset-4 hover:underline";
const steps: [string, string][] = [
  ["整理材料", "上传简历和项目，选定材料版本。"],
  ["对照岗位", "查看岗位要求，再用所选材料分析。"],
  ["核对证据", "查看来源和缺口，补齐后比较新版。"],
];

export default function HomePage() {
  return <HomeWorkspace><div className="space-y-7">
    <section className="home-opening">
      <div className="home-copy">
        <h1><span className="block">对照岗位，</span><span className="block">看清材料能支持什么</span></h1>
        <p className="reading-copy mt-4 max-w-xl">用简历和项目对照岗位要求，查看具体来源，找到值得补充的材料。报告由你确认后再投递。</p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <a href="#technical-jobs" className="btn">浏览岗位</a>
          <Link href="/portfolio" className={routeEntry}>整理我的材料 →</Link>
        </div>
        <ol className="home-steps" aria-label="使用步骤">
          {steps.map(([title, description], index) => <li key={title}>
            <span aria-hidden="true" className="text-sm font-semibold tabular-nums text-indigo-700">0{index + 1}</span>
            <div className="flex flex-wrap items-baseline gap-x-3"><strong className="text-sm">{title}</strong><p className="workspace-meta">{description}</p></div>
          </li>)}
        </ol>
      </div>
      <HomeScenarioPreview />
    </section>

    <Suspense fallback={<p role="status" className="panel">正在读取技术岗位…</p>}><JobDiscovery compact /></Suspense>

    <aside className="border-t border-slate-200 pt-3 text-sm leading-6 text-slate-600">
      <Link href="/jobs/manage" className={routeEntry}>企业岗位管理 →</Link>
      <details className="mt-1">
        <summary className="w-fit cursor-pointer rounded py-2 text-xs text-indigo-700">分析方式与边界</summary>
        <p className="mt-1 max-w-4xl text-xs leading-6 text-slate-500">AI 负责证据解释与逐项初评，本地规则负责检索边界、引用校验和评级上限；模型断链、限流、超时或输出未通过校验时会保留本地兜底报告。材料有证据支持不等于个人能力认证，未找到证据也不等于没有能力。</p>
      </details>
    </aside>
  </div></HomeWorkspace>;
}
