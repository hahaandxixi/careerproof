export const FLOW_STEPS = [
  { key: "materials", label: "准备材料", href: "/portfolio" },
  { key: "recommendations", label: "选择岗位", href: "/jobs" },
  { key: "matching", label: "查看匹配", href: "/reports" },
  { key: "growth", label: "补充材料", href: "/portfolio" },
  { key: "application", label: "确认投递", href: null },
] as const;

export type FlowStepKey = typeof FLOW_STEPS[number]["key"];

// These are locations, not a completion ledger. No saved state is inferred.
export function studentFlowLocation(pathname: string, role?: string, search = "", hash = ""): FlowStepKey | null {
  if (role !== "student") return null;
  if (/^\/reports\/[^/]+$/.test(pathname)) {
    if (["#application-submit", "#report-sharing"].includes(hash)) return "application";
    if (hash === "#report-supplement" || hash.startsWith("#growth-")) return "growth";
    return "matching";
  }
  if (pathname === "/portfolio" && new URLSearchParams(search).get("sourceReport")) return "growth";
  if (pathname === "/portfolio" || /^\/materials\/(resume|project)\/[^/]+$/.test(pathname)) return "materials";
  if (pathname === "/recommendations" || pathname === "/jobs" || /^\/jobs\/(?!new$|mine$|manage$)[^/]+$/.test(pathname)) return "recommendations";
  if (/^\/growth(?:\/[^/]+)?$/.test(pathname)) return "growth";
  if (pathname === "/reports") return "matching";
  return null;
}

export function flowStepsForLocation(pathname: string, search = "") {
  const reportDetail = /^\/reports\/[^/]+$/.test(pathname);
  const project = pathname.match(/^\/materials\/project\/([^/]+)$/)?.[1];
  const query = new URLSearchParams(search);
  const sourceReport = reportDetail ? pathname.split("/")[2] : query.get("sourceReport");
  const reportPath = sourceReport ? `/reports/${encodeURIComponent(sourceReport)}` : null;
  return FLOW_STEPS.map(step => ({ ...step,
    unavailableReason: step.key === "application" && !reportPath ? "请先打开一份本人报告，再核对分享范围并确认投递。" : undefined,
    href: step.key === "application" ? (reportPath ? `${reportPath}#application-submit` : null)
      : step.key === "matching" && reportPath ? reportPath
      : step.key === "growth" ? `/portfolio?${new URLSearchParams({add:"project",...(project?{sourceProjectVersion:project}:{}),...(sourceReport?{sourceReport}:{}),...(query.get("sourceRequirement")?{sourceRequirement:query.get("sourceRequirement")!}:{})})}` : step.href,
  }));
}
