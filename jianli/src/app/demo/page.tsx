import Link from "next/link";
import SourceCoverageDemo from "@/components/SourceCoverageDemo";
import DemoCaseImport from "@/components/DemoCaseImport";
import samples from "./samples.json";
import coverage from "./coverage.json";

const asset = (filename: string) => `/demo-assets/cases/${encodeURIComponent(filename)}`;

export default function DemoPage() {
  return <div className="mx-auto max-w-4xl space-y-6">
    <header>
      <p className="text-sm font-medium text-indigo-600">合成材料 · 按职业成套测试</p>
      <h1 className="mt-2 text-3xl font-bold text-slate-900">选一个职业，用一套对应材料</h1>
      <p className="mt-3 leading-7 text-slate-600">每套都有独立编号、简历、项目或作品、人工测试步骤。先测一套；请勿将不同编号的材料混选。所有人物、经历和指标均为虚构。</p>
    </header>
    <section className="rounded-2xl border border-indigo-200 bg-indigo-50 p-6"><h2 className="text-xl font-bold">先看企业功能实例</h2><p className="mt-2 text-sm leading-6 text-slate-600">3 位虚构候选人对照 4 项岗位要求，体验热力图筛选与雷达图；不会创建真实投递或调用模型。</p><Link href="/demo/heatmap" className="btn mt-4">打开热力图交互演示 →</Link></section>
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-xl font-bold">1. 登录或注册学生账号</h2>
      <p className="mt-3 text-sm leading-7 text-slate-600">首次使用可先注册学生账号，已有账号直接登录。企业账号用于岗位管理，学生账号用于材料上传与报告测试；演示账号由负责人提供，凭据不会显示在网页上。注册和后续登录请保持同一网站地址。</p>
      <details className="mt-3 text-sm text-slate-600"><summary className="cursor-pointer">负责人：账号在哪里？</summary><p className="mt-2 leading-7">日常3000演示账号在本机 <code>backend/.tmp/demo-credentials.json</code>；3001隔离运行的企业账号在 <code>backend/.tmp/e2e/&lt;RunId&gt;.json</code> 的 <code>accounts.enterprise</code>，不要混用。自行注册的账号使用自己设置的密码；文件不会记录这类账号的密码。凭据不要截图分享或提交。</p></details>
      <Link href="/login" className="mt-4 inline-block rounded-lg bg-indigo-600 px-4 py-2 text-white">前往登录</Link>
      <Link href="/register" className="ml-4 inline-block text-sm text-indigo-600 underline">注册学生账号</Link>
    </section>
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-xl font-bold">2. 选职业，下载同编号的三个文件</h2>
      <p className="mt-3 text-sm leading-7 text-slate-600">简历 TXT 上传到简历入口，项目 ZIP 上传到项目入口，步骤 TXT 打开照着操作。项目 ZIP 不用解压，也不需要执行其中的代码。产品、运营的项目包是对应方案文档。</p>
      <p className="mt-2 text-sm leading-7 text-indigo-700">完成演示初始化后，这九套材料属于初始化时使用的学生演示账号。其他学生账号可点“导入这套材料到我的账号”，只上传本地合成文件并解析，不调用 AI；同名且完成的版本会复用。亲自测试重新上传时，在卡片名称末尾加本轮日期，避免创建同名材料。</p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {samples.map(sample => <article key={sample.caseId} className="min-w-0 rounded-xl border border-slate-200 p-4">
          <p className="text-xs font-semibold text-indigo-600">{sample.caseId} · {sample.version} · 合成测试</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-900">{sample.title}</h3>
          <p className="mt-2 text-sm text-slate-700">对应作品：{sample.projectTitle}</p>
          <p className="mt-1 text-xs text-slate-500">测试企业：CareerProof 合成演示企业</p>
          <p className="mt-2 break-words text-xs leading-6 text-slate-500">简历名称：{sample.resumeName}<br />项目名称：{sample.projectName}<br />测试岗位：{sample.jobTitle}</p>
          <div className="mt-3 flex flex-wrap gap-3 text-sm text-indigo-700">
            <a className="rounded-lg bg-indigo-50 px-3 py-2" href={asset(sample.resumeFilename)} download={sample.resumeFilename}>下载对应简历</a>
            <a className="rounded-lg bg-indigo-50 px-3 py-2" href={asset(sample.projectFilename)} download={sample.projectFilename}>下载对应项目</a>
            <a className="rounded-lg bg-indigo-50 px-3 py-2" href={asset(sample.scriptFilename)} download={sample.scriptFilename}>下载测试步骤</a>
          </div>
          {sample.caseId === "CP01" && <details className="mt-3 rounded-lg border border-indigo-200 p-3 text-sm">
            <summary className="cursor-pointer font-medium text-indigo-800">继续演示补证：下载 Redis 合成新版</summary>
            <p className="mt-2 leading-6 text-slate-600">先用首版生成报告，再从 Redis 缺口保存补证任务。将新版上传到原项目，保存新版选择后生成新报告；保留原简历，不必重新投递。</p>
            <div className="mt-3 flex flex-wrap gap-3 text-indigo-700">
              <a className="rounded-lg bg-indigo-50 px-3 py-2" href={asset("CP01-Python-Redis-synthetic-v2.zip")} download>下载补证项目 v2</a>
              <a className="rounded-lg bg-indigo-50 px-3 py-2" href={asset("CP01-Redis-补证演示步骤-v2.txt")} download>下载补证步骤</a>
            </div>
            <p className="mt-2 text-xs leading-6 text-slate-600">仅增加可引用的 Redis 读写源码，未执行代码，不证明运行成功、个人贡献或完整缓存能力。新报告不会覆盖企业原投递快照；没有升级也应照实解释。</p>
          </details>}
          <DemoCaseImport sample={sample}/>
          <p className="mt-3 text-xs leading-6 text-amber-800">应识别的边界：{sample.boundary}</p>
          <Link className="mt-3 inline-block text-sm text-indigo-600 underline" href={`/jobs?q=${encodeURIComponent(sample.jobTitle)}`}>查找对应岗位 →</Link>
        </article>)}
      </div>
    </section>
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-xl font-bold">3. 上传并选择同一套版本</h2>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-7 text-slate-600">
        <li>从顶部“学生账户”打开“个人材料”，照卡片填写简历名称和项目名称，分别上传同编号 TXT、ZIP。</li>
        <li>项目说明填写“合成静态测试作品，未执行，不代表本人贡献。”等待两份材料均解析完成。</li>
        <li>在岗位发现打开对应岗位；简历和项目都选择同编号、同版本的文件，例如 CP08 的简历只配 CP08 的数据库项目。</li>
        <li>先体验本地规则报告：不勾选外部 AI 同意，直接点击“生成我的匹配报告”，材料不会外发。需要 AI 解释时，再阅读发送范围和费用说明，明确同意后生成；职业规划和视觉观察另按各自提示确认。</li>
        <li>按需展开引用核对源码或文档，记录缺口；本人核对备注可选，不是投递前置条件。无需追求固定分数，本人采纳不是独立认证。</li>
        <li>决定投递时，在报告页阅读分享范围、勾选同意并确认投递，再从账户菜单查看“个人投递”和“通知”。生成报告不会自动投递。</li>
      </ol>
      <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900">代码和方案不等于执行成功；材料缺失不代表没有能力。AI 不可用时自动生成本地兜底报告，并明确显示降级。</p>
      <div className="mt-4 flex flex-wrap gap-5 text-sm text-indigo-600"><Link href="/portfolio" className="underline">进入个人材料</Link><Link href="/recommendations" className="underline">测试职业规划</Link></div>
    </section>
    <details className="rounded-2xl border border-slate-200 bg-white p-6">
      <summary className="cursor-pointer font-semibold">查看规则覆盖范围与源码引用演示</summary>
      <p className="mt-3 text-sm leading-7 text-slate-600">当前静态规则覆盖 {coverage.reduce((sum, row) => sum + row.supported.length, 0)}/45 项要求。未覆盖项需人工核对，不能把静态覆盖当作完整岗位能力验证。</p>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">岗位</th><th className="p-2">规则覆盖</th><th className="p-2">暂不支持</th></tr></thead><tbody>{coverage.map(row => <tr key={row.job} className="border-t border-slate-200"><td className="p-2">{row.job}</td><td className="p-2">{row.supported.length}/5</td><td className="p-2 text-slate-600">{row.unsupported.join("、") || "无"}</td></tr>)}</tbody></table></div>
      <div className="mt-5"><SourceCoverageDemo /></div>
    </details>
  </div>;
}
