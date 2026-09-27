import Link from "next/link";
import SourceCoverageDemo from "@/components/SourceCoverageDemo";
import samples from "./samples.json";
import coverage from "./coverage.json";

export default function DemoPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <p className="text-sm font-medium text-indigo-600">合成材料 · 本地演示</p>
        <h1 className="mt-2 text-3xl font-bold text-slate-900">从样例到证据报告</h1>
        <p className="mt-3 text-slate-600">先使用学生账号完成上传与分析。企业账号用于查看和管理预置岗位。</p>
      </header>
      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-bold">1. 登录演示账号</h2>
        <p className="mt-2 text-sm text-slate-500">账号须由本地初始化脚本创建；仅供合成材料测试，不存放个人资料，不用于公开部署。</p>
        <p className="mt-4 text-sm leading-7 text-slate-700">运行 <code>Start-Demo.ps1</code> 后，在本机打开 <code>backend/.tmp/demo-credentials.json</code> 查看学生与企业邮箱及密码。凭据不会写入代码仓库，也不会显示在网页上。若使用自定义的 <code>DEMO_*</code> 环境变量，请使用你配置的账号。</p>
        <Link href="/login" className="mt-4 inline-block rounded-lg bg-indigo-600 px-4 py-2 text-white">前往登录</Link>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-bold">2. 下载并上传样例</h2>
        <div className="mt-4 flex flex-wrap gap-3 text-sm text-indigo-700">
          <a href="/demo-assets/student-resume.txt" download className="rounded-lg bg-indigo-50 px-4 py-2">下载合成简历 TXT</a>
          <a href="/demo-assets/evidence-api.zip" download className="rounded-lg bg-indigo-50 px-4 py-2">下载基础项目 ZIP</a>
          <a href="/demo-assets/evidence-function-call.zip" download className="rounded-lg bg-indigo-50 px-4 py-2">下载补检索专项 ZIP</a>
          <a href="/demo-assets/software-backend-job.md" download className="rounded-lg bg-indigo-50 px-4 py-2">下载岗位说明</a>
        </div>
        <p className="mt-4 text-sm leading-7 text-slate-600">进入「我的材料」，在简历入口选择 TXT，在项目入口选择 ZIP。填写名称后分别提交，等待解析完成。ZIP 不用解压，最大 30MB。当前使用点击选择文件上传。</p>
        <p className="mt-3 text-sm leading-7 text-slate-600">填写示例：简历名称「合成学生简历」；项目名称「任务管理 API（合成演示）」；项目说明「合成测试项目，包含 Python、FastAPI、PostgreSQL 和 pytest 片段，用于测试证据匹配。运行情况和作者贡献未经核验。」</p>
        <p className="mt-3 rounded-lg bg-indigo-50 p-3 text-sm leading-6 text-indigo-900">补检索专项 ZIP 用于「Python 受控补检索（合成验收）」岗位：模型可在本次选定的材料版本中有限补检索，每次最多新增一条引用；不保证能找到新证据。真实重跑会消耗模型额度，普通功能体验优先使用基础项目 ZIP。</p>
        <Link href="/portfolio" className="mt-3 inline-block text-indigo-600 underline">进入我的材料</Link>
      </section>
      <SourceCoverageDemo />
      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-bold">各职业的对照材料</h2>
        <p className="mt-3 text-sm leading-7 text-slate-600">下列每个方向都有简历 TXT 和作品 TXT。作品文件上传到「项目压缩包或作品文档」入口，不要传到简历入口。它们是含有缺口的文档样例，不是完整工程或满分标准答案。</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {samples.map(sample => (
            <article key={sample.slug} className="rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900">{sample.title}</h3>
              <p className="mt-2 text-sm text-slate-600">{sample.boundary}</p>
              <p className="mt-2 text-xs leading-6 text-slate-500">简历名称：{sample.title}合成简历<br />项目名称：{sample.title}合成练习<br />项目说明：合成测试作品，内容及未完成项见文档，不代表真实经历。</p>
              <div className="mt-3 flex flex-wrap gap-4 text-sm text-indigo-700">
                <a download href={`/demo-assets/roles/${sample.slug}-resume.txt`}>下载简历 TXT</a>
                <a download href={`/demo-assets/roles/${sample.slug}-project.txt`}>下载作品 TXT</a>
                {["devops", "dba"].includes(sample.slug) && <a download href={`/demo-assets/roles/${sample.slug}-project.zip`}>下载工程 ZIP（优先测试）</a>}
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-bold">3. 选择岗位并核对报告</h2>
        <p className="mt-3 text-sm leading-7 text-amber-900">当前规则共覆盖 {coverage.reduce((sum, row) => sum + row.supported.length, 0)}/45 项要求。下面展示可评估范围，未覆盖项需要人工审阅；规则覆盖仅代表有静态检测项，不代表能完整验证岗位能力。运维和 DBA 优先上传工程 ZIP，脚本均未执行。</p>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">岗位</th><th className="p-2">规则覆盖</th><th className="p-2">暂不支持</th></tr></thead><tbody>{coverage.map(row => <tr key={row.job} className="border-t border-slate-200"><td className="p-2">{row.job}</td><td className="p-2">{row.supported.length}/5</td><td className="p-2 text-slate-600">{row.unsupported.join("、") || "无"}</td></tr>)}</tbody></table></div>
        <p className="mt-3 text-sm leading-7 text-slate-600">在岗位列表搜索「合成演示」，打开「Python 后端开发实习生（合成演示）」，选择刚上传的简历和项目版本，开始匹配。查看任务进度，完成后逐项打开证据引用，保存人工复核，再刷新确认报告仍可找回。</p>
        <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900">样例包含 Python、FastAPI、PostgreSQL 和 pytest 相关片段；Redis 只有简历声明，不应出现虚构的实现证据。代码片段不等于运行成功或本人贡献的证明。系统始终按 AI 链路发起分析；模型断链、限流、超时或输出校验失败时才自动生成本地兜底报告。</p>
        <p className="mt-3 text-sm leading-7 text-slate-600">可测试 9 个方向：Python 后端、前端、软件测试、数据分析、产品助理、用户运营、自动化运维、数据库 DBA、数据工程。使用同一份简历和同一个项目版本分别匹配，比较证据与缺口；现有 ZIP 是后端样例，不是所有岗位的合格样例。使用 PostgreSQL 不等于具备备份恢复能力，包含 Dockerfile 也不等于生产运维经验。</p>
        <Link href="/jobs" className="mt-4 inline-block text-indigo-600 underline">进入岗位列表</Link>
      </section>
    </div>
  );
}
