import IdentityName from "./IdentityName";
import type { MatchReport } from "@/lib/api/domain";
import { boundaryFixtureJob, displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import { reportReadingStatus } from "@/lib/report-display";
import Link from "next/link";

/** Identity shared by all report sections; it must stay outside the hidden panels. */
export default function ReportPaperHeader({ report }: { report: MatchReport }) {
  const status = reportReadingStatus(report);
  const boundaryFixture = boundaryFixtureJob(report.jobId);
  const analysisLabel = status?.label === "AI 分析完成" ? "AI 分析" : "";
  return <header className="report-paper-heading report-command-bar" aria-labelledby="report-title">
    <Link className="review-back" href="/reports">← 我的报告</Link>
    {boundaryFixture && <p className="report-fixture-notice" role="note"><strong>历史核验资料</strong> · 本报告用于核对「暂不支持」判定的边界，不作为默认岗位样本；原始报告与投递快照保持不变。</p>}
    <div className="report-command-identity">
      <div className="min-w-0">
        <p className="workspace-meta">岗位匹配报告</p>
        <div className="report-command-title-row">
          <h1 id="report-title" className="page-title break-words">{displayJobTitle(report.jobTitle, report.jobId)}</h1>
          {status && <span className="report-status-pill">{status.label}</span>}
        </div>
        <p className="report-command-subline">
          <IdentityName name={report.candidateName} identityId={report.candidateId}/>
          <span aria-hidden="true">·</span>
          <time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time>
        </p>
      </div>
      <dl className="report-command-facts">
        {analysisLabel && <div><dt>分析来源</dt><dd>{analysisLabel}</dd></div>}
        <div><dt>要求</dt><dd>{report.items.length} 项</dd></div>
        <div><dt>固定材料</dt><dd>{report.materials.length} 份</dd></div>
      </dl>
    </div>
    <p className="report-material-line" title={report.materials.map(material => `${displayMaterialTitle(material.title, material.id)} v${material.versionNumber}`).join(" · ")}>
      <span>材料版本</span>
      {report.materials.map(material => <span key={`${material.kind}-${material.id}`} className="report-material-chip">{displayMaterialTitle(material.title, material.id)} · v{material.versionNumber}</span>)}
    </p>
  </header>;
}
