import Link from "next/link";
import DemoCaseGallery from "@/components/DemoCaseGallery";
import StickyRail from "@/components/StickyRail";
import samples from "./samples.json";

export default function DemoPage() {
  return <div className="case-library-page">
    <header className="case-library-heading">
      <div><p className="workspace-meta">案例库</p><h1 className="page-title">用一套完整材料，走完一次证据核对</h1><p className="reading-copy">选择案例材料，下载或导入材料库。</p></div>
      <div className="case-library-entry"><Link href="/portfolio" className="btn-secondary">进入我的材料</Link></div>
    </header>
    <div className="case-library-layout">
      <DemoCaseGallery samples={samples} />
      <StickyRail>
        <section className="case-library-notes">
          <div className="case-library-note"><h2>用一套材料走完核对</h2><ol className="case-guide-steps"><li><strong>下载或导入</strong><span>下载单个文件，或把整套材料导入自己的账号。</span></li><li><strong>查看解析</strong><span>到“我的材料”确认 TXT/ZIP 已解析完成。</span></li><li><strong>选择岗位</strong><span>材料完成后，用岗位要求生成匹配报告。</span></li></ol><p>导入需登录学生账号，同名且已完成的材料不会重复覆盖；代码不会执行，导入也不会自动生成报告或投递。</p></div>
        </section>
      </StickyRail>
    </div>
  </div>;
}
