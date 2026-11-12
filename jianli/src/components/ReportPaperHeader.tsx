import IdentityName from "./IdentityName";
import type { MatchReport } from "@/lib/api/domain";
import { displayJobTitle } from "@/lib/demo-display-identity.js";
import { reportReadingStatus } from "@/lib/report-display";
import Link from "next/link";
import type { ReactNode } from "react";
import ReportMaterialVersions from "./ReportMaterialVersions";

/** Identity shared by all report sections; it must stay outside the hidden panels. */
export default function ReportPaperHeader({ report, backHref = "/reports", versionTools }: { report: MatchReport; backHref?: string; versionTools?: ReactNode }) {
  const status = reportReadingStatus(report);
  return <header className="report-paper-heading report-command-bar" aria-labelledby="report-title">
    <Link className="review-back" href={backHref}>← 我的报告</Link>
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
      <ReportMaterialVersions materials={report.materials} />
    </div>
    {versionTools}
  </header>;
}
