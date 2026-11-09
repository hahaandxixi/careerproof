import Link from "next/link";
import SourceCoverageDemo from "@/components/SourceCoverageDemo";
import DemoCaseGallery from "@/components/DemoCaseGallery";
import StickyRail from "@/components/StickyRail";
import samples from "./samples.json";
import coverage from "./coverage.json";

export default function DemoPage() {
  return <div className="case-library-page">
    <header className="case-library-heading">
      <div><p className="workspace-meta">案例库</p><h1 className="page-title">用一套完整材料，走完一次证据核对</h1><p className="reading-copy">按方向浏览案例，下载或导入到自己的材料库走一遍核对流程。所有人物、经历和指标均为虚构，示例内容不证明个人能力或真实运行结果。</p></div>
      <div className="case-library-entry"><Link href="/portfolio" className="btn-secondary">进入我的材料</Link></div>
    </header>
    <div className="case-library-layout">
      <DemoCaseGallery samples={samples} />
      <StickyRail>
        <section className="case-library-notes">
          <div className="case-library-note"><h2>用一套材料走完核对</h2><ol className="case-guide-steps"><li><strong>下载或导入</strong><span>下载单个文件，或把整套材料导入自己的账号。</span></li><li><strong>查看解析</strong><span>到“我的材料”确认 TXT/ZIP 已解析完成。</span></li><li><strong>选择岗位</strong><span>材料完成后，用岗位要求生成匹配报告。</span></li></ol><p>导入需登录学生账号，同名且已完成的材料不会重复覆盖；代码不会执行，导入也不会自动生成报告或投递。</p></div>
          <details className="case-guide-technical"><summary>规则覆盖与来源演示（技术详情）</summary><p>当前静态规则覆盖 {coverage.reduce((sum, row) => sum + row.supported.length, 0)}/45 项要求；未覆盖项需人工核对，不把静态覆盖当作完整能力验证。</p><div className="overflow-x-auto"><table><thead><tr><th>岗位</th><th>规则覆盖</th><th>暂不支持</th></tr></thead><tbody>{coverage.map(row => <tr key={row.job}><td>{row.job}</td><td>{row.supported.length}/5</td><td>{row.unsupported.join("、") || "无"}</td></tr>)}</tbody></table></div><SourceCoverageDemo /></details>
          <details className="case-guide-enterprise"><summary>了解企业如何核对材料</summary><p>企业查看的是你确认授权时的报告快照，不代表录用结果。</p><Link href="/demo/heatmap">体验候选人材料对照</Link><Link href="/demo/enterprise-scenario">查看受控合成 A/B 与 C 隔离场景</Link></details>
        </section>
      </StickyRail>
    </div>
  </div>;
}
