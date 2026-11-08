import IdentityName from "./IdentityName";
import type { MatchReport } from "@/lib/api/domain";
import { boundaryFixtureJob, displayJobTitle } from "@/lib/demo-display-identity.js";
import { reportReadingStatus } from "@/lib/report-display";

/** Identity shared by all report sections; it must stay outside the hidden panels. */
export default function ReportPaperHeader({ report }: { report: MatchReport }) {
  const status = reportReadingStatus(report);
  const boundaryFixture = boundaryFixtureJob(report.jobId);
  return <header className="report-paper-heading" aria-labelledby="report-title">
    {boundaryFixture && <p className="report-fixture-notice" role="note"><strong>历史规则核验夹具</strong> · 本报告用于“不支持评估”边界核对，不作为默认岗位样本；原始报告与投递快照保持不变。</p>}
    <div className="min-w-0">
      <p className="workspace-meta">岗位匹配报告</p>
      <h1 id="report-title" className="page-title break-words">{displayJobTitle(report.jobTitle, report.jobId)}</h1>
      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
        <span><IdentityName name={report.candidateName} identityId={report.candidateId}/></span>
        <span aria-hidden="true">·</span>
        <time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time>
      </p>
    </div>
    <p className="report-paper-status">{status.label}</p>
  </header>;
}
