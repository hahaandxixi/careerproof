import Link from "next/link";
import SourceCoverageDemo from "@/components/SourceCoverageDemo";
import DemoCaseGallery from "@/components/DemoCaseGallery";
import StickyRail from "@/components/StickyRail";
import samples from "./samples.json";
import coverage from "./coverage.json";

export default function DemoPage() {
  return <div className="case-library-page">
    <header className="case-library-heading">
      <div><p className="workspace-meta">案例库 · 合成材料</p><h1 className="page-title">用一套完整材料，走完一次证据核对</h1><p className="reading-copy">按方向浏览案例，查看材料组成，下载或导入到自己的材料库。所有人物、经历和指标均为虚构；示例企业与指标不证明个人能力或真实运行结果。</p></div>
      <div className="case-library-entry"><Link href="/portfolio" className="btn-secondary">进入我的材料</Link><Link href="/demo/heatmap" className="btn-secondary">查看热力图示例</Link></div>
    </header>
    <div className="case-library-layout">
      <DemoCaseGallery samples={samples} />
      <StickyRail>
        <section className="case-library-notes">
          <div className="case-library-note"><h2>案例库与个人材料库不同</h2><p>案例库是可下载的合成测试材料；个人材料库只保存你自己上传的简历和项目版本。导入不会生成 AI 报告或投递。</p></div>
          <details><summary>首次使用与导入规则</summary><p>登录学生账号后，可把整套材料导入自己的账号；同名且已完成的材料不会重复覆盖。TXT/ZIP 分别解析完成后再去岗位页选择；代码不会执行。</p></details>
          <details><summary>规则覆盖与来源演示</summary><p>当前静态规则覆盖 {coverage.reduce((sum, row) => sum + row.supported.length, 0)}/45 项要求；未覆盖项需人工核对，不把静态覆盖当作完整能力验证。</p><div className="overflow-x-auto"><table><thead><tr><th>岗位</th><th>规则覆盖</th><th>暂不支持</th></tr></thead><tbody>{coverage.map(row => <tr key={row.job}><td>{row.job}</td><td>{row.supported.length}/5</td><td>{row.unsupported.join("、") || "无"}</td></tr>)}</tbody></table></div><SourceCoverageDemo /></details>
        </section>
      </StickyRail>
    </div>
  </div>;
}
