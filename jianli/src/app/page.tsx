import Link from "next/link";
import HomeWorkspace from "@/components/HomeWorkspace";
import { Suspense } from "react";
import HomeScenarioPreview from "@/components/HomeScenarioPreview";
import JobDiscovery from "@/components/JobDiscovery";

const routeEntry = "inline-flex min-h-11 items-center text-sm font-medium text-[#1d4a40] underline-offset-4 hover:underline";
const entries: [string, string, string][] = [
  ["01", "整理材料", "上传简历与项目，固定本次版本。"],
  ["02", "对照岗位", "从岗位要求进入材料证据阅读。"],
  ["03", "按需补证", "只有真实缺口才上传新版，再确认分析。"],
];

export default function HomePage() {
  return <HomeWorkspace><div className="home-v2">
    <section className="home-hero">
      <div className="home-hero-copy">
        <p className="workspace-meta">CareerProof · 材料证据工作台</p>
        <h1><span>把岗位要求，</span><span className="home-hero-accent">落到可核对的材料上。</span></h1>
        <p className="reading-copy">先看岗位要求，再看到简历和项目里的具体来源、缺口与版本。报告由你确认后才投递，AI 状态与已投递快照如实保留。</p>
        <div className="home-hero-actions">
          <a href="#technical-jobs" className="btn">从岗位开始</a>
          <Link href="/portfolio" className={routeEntry}>整理我的材料 <span aria-hidden="true">→</span></Link>
          <Link href="/demo" className={routeEntry}>浏览案例材料 <span aria-hidden="true">→</span></Link>
        </div>
        <ol className="home-entry-list" aria-label="从材料到报告">
          {entries.map(([number, title, description]) => <li key={number}>
            <span className="home-entry-number" aria-hidden="true">{number}</span>
            <div><strong>{title}</strong><p>{description}</p></div>
          </li>)}
        </ol>
      </div>
      <div className="home-hero-preview">
        <div className="home-preview-head"><span>阅读关系预览</span><span className="home-example-tag">合成示例</span></div>
        <HomeScenarioPreview />
        <p className="home-example-note">示例内容使用虚构岗位与材料，用于说明信息层级；不构成个人结果或能力证明。</p>
      </div>
    </section>

    <Suspense fallback={<p role="status" className="panel">正在读取技术岗位…</p>}><JobDiscovery compact /></Suspense>

    <aside className="home-boundary">
      <Link href="/jobs/manage" className={routeEntry}>企业岗位管理 →</Link>
      <details>
        <summary>分析方式与边界</summary>
        <p>AI 负责证据解释与逐项初评，本地规则负责检索边界、引用校验和评级上限；模型断链、限流、超时或输出未通过校验时会保留本地兜底报告。材料有证据支持不等于个人能力认证，未找到证据也不等于没有能力。</p>
      </details>
    </aside>
  </div></HomeWorkspace>;
}

