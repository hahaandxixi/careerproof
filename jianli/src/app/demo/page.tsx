import Link from "next/link";
import DemoCaseGallery from "@/components/DemoCaseGallery";
import StickyRail from "@/components/StickyRail";
import samples from "./samples.json";

export default function DemoPage() {
  return <div className="case-library-page">
    <header className="case-library-heading">
      <h1 className="page-title">材料库</h1>
      <div className="case-library-entry"><Link href="/portfolio" className="btn-secondary">进入我的材料</Link></div>
    </header>
    <div className="case-library-layout">
      <DemoCaseGallery samples={samples} />
      <StickyRail>
        <section className="case-library-notes">
          <div className="case-library-note"><h2>材料使用说明</h2><p>这些材料可用于练习岗位核对。导入需登录求职者账号，已导入的同一版本会保留。代码不会执行，报告和投递由你发起。</p></div>
        </section>
      </StickyRail>
    </div>
  </div>;
}
