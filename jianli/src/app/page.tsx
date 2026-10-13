import Link from "next/link";
import { HEATMAP_DEMO, DEMO_LABELS, demoCellClass } from "@/lib/heatmap-demo";

const heroActions = "btn min-h-[44px] flex-1 px-5 sm:flex-none";
const quietActions = "btn-secondary min-h-[44px] flex-1 px-5 sm:flex-none";
const studentEntry = "flex min-h-[44px] flex-1 items-center justify-center rounded-lg border border-slate-300 bg-white px-5 text-sm font-medium text-slate-700 hover:bg-slate-50";
const enterpriseEntry = "flex min-h-[44px] flex-1 items-center justify-center rounded-lg border border-indigo-200 bg-indigo-50 px-5 text-sm font-medium text-indigo-800 hover:bg-indigo-100";
const demoAction = "btn mt-4 min-h-[44px] w-full self-start px-5 sm:w-auto";
const steps: [string, string][] = [
  ["01 · 整理材料", "上传简历、项目和作品，核对解析文本，选定本轮要参与匹配的版本。"],
  ["02 · 对照岗位", "按方向、城市和工作类型筛选岗位，对选定材料发起一次匹配分析。"],
  ["03 · 核对证据", "逐条查看要求对应的材料片段、行号与规则说明，保存报告再来对照。"],
];

export default function HomePage() {
  return <div className="space-y-8">
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
        <div className="rounded-2xl border border-indigo-100 bg-white p-5 shadow-sm sm:p-6" aria-label="预设合成材料支持状态预览">
          <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold">Python 后端 · 岗位对照</p><span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs text-indigo-700">合成预览</span></div>
          <p className="mt-2 text-xs leading-5 text-slate-500">先看要求，再看材料支持了什么</p>
          <dl className="mt-5 space-y-3">{HEATMAP_DEMO[0].dimensions.map(d => <div key={d.requirementId} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-slate-50/70 p-3"><dt className="text-sm text-slate-700">{d.title}</dt><dd className={`rounded-md border px-2.5 py-1 text-xs font-medium ${demoCellClass(d.verdict)}`}>{DEMO_LABELS[d.verdict]}</dd></div>)}</dl>
          <p className="mt-4 border-t border-slate-100 pt-3 text-xs leading-5 text-slate-500">预设状态，不含真实材料，不调用模型。缺材料不代表没有能力。</p>
        </div>
      </div>
    </section>

    <section aria-labelledby="choose-route" className="space-y-3">
      <h2 id="choose-route" className="px-1 text-sm font-semibold text-slate-500">选择你的路线</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <article className="panel flex flex-col">
          <h3 className="text-lg font-semibold">我是学生</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">准备材料、对照岗位要求、核对证据片段，按同一版本保留可以复核的匹配报告。</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link href="/jobs" className={studentEntry}>查看岗位</Link>
            <Link href="/portfolio" className={studentEntry}>整理材料</Link>
          </div>
        </article>
        <article className="panel flex flex-col">
          <h3 className="text-lg font-semibold">我是企业招聘方</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">发布与管理岗位，按岗位要求对照候选人材料；当前需要企业账号登录后使用。</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link href="/jobs/manage" className={enterpriseEntry}>岗位管理</Link>
          </div>
        </article>
      </div>
    </section>

    <section className="panel" aria-labelledby="three-steps">
      <h2 id="three-steps" className="text-lg font-semibold">三步完成一次核对</h2>
      <ol className="mt-4 grid gap-4 md:grid-cols-3">
        {steps.map(([title, description]) => <li key={title} className="rounded-xl bg-slate-50 p-4">
          <h3 className="text-sm font-semibold text-indigo-700">{title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </li>)}
      </ol>
    </section>

    <section className="panel" aria-labelledby="demo-entry">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="demo-entry" className="text-lg font-semibold">先看合成示例</h2>
        <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">合成演示材料</span>
      </div>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">无需登录；3 位虚构候选人对 4 项岗位要求，可直接体验筛选、候选人切换与岗位要求雷达。</p>
      <Link href="/demo/heatmap" className={demoAction}>打开热力图交互示例</Link>
      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs leading-6 text-slate-500">
        <li>人物、经历和指标均为合成，不代表任何真实求职者。</li>
        <li>不会创建真实投递、不会调用网站模型，也不产生真实评分。</li>
      </ul>
      <p className="mt-3 text-xs leading-6 text-slate-500">合成示例只用于了解界面；对你自己材料的分析需要在登录后对真实材料发起。</p>
    </section>

    <aside className="rounded-xl border border-slate-200 bg-white p-5 text-sm leading-6 text-slate-600">
      AI 负责证据解释与逐项初评，本地规则负责检索边界、引用校验和评级上限；模型断链、限流、超时或输出未通过校验时会保留本地兜底报告。材料有证据支持不等于个人能力认证，未找到证据也不等于没有能力。
    </aside>
  </div>;
}
