import Link from "next/link";
import HomeWorkspace from "@/components/HomeWorkspace";
import { Suspense } from "react";
import HomeScenarioPreview from "@/components/HomeScenarioPreview";
import JobDiscovery from "@/components/JobDiscovery";

const heroActions = "btn min-h-[44px] flex-1 px-5 sm:flex-none";
const quietActions = "btn-secondary min-h-[44px] flex-1 px-5 sm:flex-none";
const routeEntry = "inline-flex min-h-11 items-center text-sm font-medium text-indigo-700 underline-offset-4 hover:underline";
const steps: [string, string][] = [
  ["01 · 整理材料", "上传简历和项目，核对解析结果，明确选版。"],
  ["02 · 对照岗位", "查看岗位要求，用选定材料主动发起分析。"],
  ["03 · 核对证据", "定位来源、理解缺口，完善后上传新版再比较。"],
];

export default function HomePage() {
  return <HomeWorkspace><div className="space-y-6 sm:space-y-7">
    <section className="panel overflow-hidden bg-gradient-to-br from-indigo-50 via-white to-white py-8 sm:p-10">
      <div className="grid items-center gap-8 lg:grid-cols-[1.3fr_1fr]">
        <div>
          <p className="inline-flex rounded-full border border-indigo-100 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700">CareerProof · 从你的材料出发</p>
          <h1 className="mt-5 text-3xl font-bold leading-tight tracking-tight sm:text-4xl">让你的经历，<br /><span className="text-indigo-600">成为看得见的证据。</span></h1>
          <p className="mt-5 max-w-xl text-sm leading-7 text-slate-600 sm:text-base">上传材料，对照岗位，找到值得补充的一项。查看来源、保留版本，再由你决定是否投递。</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/jobs" className={heroActions}>发现适合的岗位</Link>
            <Link href="/demo/heatmap" className={quietActions}>先看交互示例</Link>
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-500">示例无需登录；正式报告只在你确认后向企业投递。</p>
        </div>
        <HomeScenarioPreview />
      </div>
    </section>

    <Suspense fallback={<p role="status" className="panel">正在读取技术岗位…</p>}><JobDiscovery compact /></Suspense>

    <section aria-labelledby="choose-route" className="rounded-xl border border-slate-200 bg-white px-4 py-2 sm:px-5">
      <h2 id="choose-route" className="sr-only">选择你的路线</h2>
      <div className="grid divide-y divide-slate-100 sm:grid-cols-2 sm:divide-y-0">
        <div className="flex flex-wrap items-center gap-x-5">
          <span className="text-sm font-semibold text-slate-700">学生</span>
          <Link href="/portfolio" className={routeEntry}>整理材料 →</Link>
          <Link href="/jobs" className="inline-flex min-h-11 items-center text-sm text-slate-600 underline-offset-4 hover:text-indigo-700 hover:underline">查看岗位</Link>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 sm:justify-end">
          <span className="text-sm font-semibold text-slate-700">企业</span>
          <Link href="/jobs/manage" className={routeEntry}>岗位管理 →</Link>
        </div>
      </div>
    </section>

    <section className="space-y-3" aria-labelledby="three-steps">
      <h2 id="three-steps" className="text-lg font-semibold">三步完成一次核对</h2>
      <ol className="grid gap-4 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-3 sm:gap-5 sm:p-5">
        {steps.map(([title, description], index) => <li key={title} className={index ? "min-w-0 border-t border-slate-100 pt-3 sm:border-l sm:border-t-0 sm:pl-5 sm:pt-0" : "min-w-0"}>
          <h3 className="text-sm font-semibold text-indigo-700">{title}</h3>
          <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
        </li>)}
      </ol>
    </section>

    <aside className="border-t border-slate-200 pt-3 text-sm leading-6 text-slate-600">
      <p>AI 帮你解释材料，结论需核对来源；模型不可用时会保留规则结果。</p>
      <details className="mt-1">
        <summary className="w-fit cursor-pointer rounded py-2 text-xs text-indigo-700">分析方式与边界</summary>
        <p className="mt-1 max-w-4xl text-xs leading-6 text-slate-500">AI 负责证据解释与逐项初评，本地规则负责检索边界、引用校验和评级上限；模型断链、限流、超时或输出未通过校验时会保留本地兜底报告。材料有证据支持不等于个人能力认证，未找到证据也不等于没有能力。</p>
      </details>
    </aside>
  </div></HomeWorkspace>;
}
