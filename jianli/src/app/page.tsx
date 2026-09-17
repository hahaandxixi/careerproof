import Link from "next/link";

export default function HomePage() {
  return <div className="space-y-8">
    <section className="panel py-10 sm:p-12">
      <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700">真实材料 · 版本留存 · 可核对的 AI 引用</span>
      <h1 className="mt-5 max-w-3xl text-3xl font-bold leading-tight sm:text-4xl">让每一份岗位匹配，<br className="hidden sm:block" />都有可以核对的材料证据。</h1>
      <p className="mt-5 max-w-2xl leading-7 text-slate-600">关联你的简历、项目和作品，逐项查看岗位要求的支持证据。保留文件版本和分析记录，知道已有材料支持什么，以及下一步需要补充什么。</p>
      <div className="mt-7 flex flex-wrap gap-3"><Link href="/jobs" className="btn">发现适合的岗位</Link><Link href="/portfolio" className="btn-secondary">整理我的材料</Link></div>
    </section>
    <section className="grid gap-4 md:grid-cols-3">
      {[["01 · 整理材料", "上传简历和项目或作品，查看解析文本，选择要用于匹配的版本。"], ["02 · 对照岗位", "按方向、城市和工作类型筛选真实岗位，发起属于你的匹配分析。"], ["03 · 核对证据", "查看每条岗位要求对应的材料片段、行号和规则说明，保留完整报告。"]].map(([title, description]) =>
        <article key={title} className="panel"><h2 className="font-semibold">{title}</h2><p className="mt-3 text-sm leading-6 text-slate-600">{description}</p></article>)}
    </section>
    <aside className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-900">
      规则先检索并评分材料证据，AI 模型只解释候选片段并返回受校验的引用编号；模型不可用时自动保留规则报告。材料有证据支持不等于个人能力认证，未找到证据也不等于没有能力。
    </aside>
  </div>;
}
