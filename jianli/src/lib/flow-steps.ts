export const FLOW_STEPS = [
  { key: "materials", label: "准备材料", href: "/portfolio" },
  { key: "recommendations", label: "推荐职业与岗位", href: "/recommendations" },
  { key: "matching", label: "查看岗位匹配", href: "/reports" },
  { key: "growth", label: "补充材料", href: "/portfolio" },
  { key: "application", label: "确认投递", href: null },
] as const;

export type FlowStepKey = typeof FLOW_STEPS[number]["key"];

// These are locations, not a completion ledger. No saved state is inferred.
export function studentFlowLocation(pathname: string, role?: string): FlowStepKey | null {
  if (role !== "student") return null;
  if (pathname === "/portfolio" || /^\/materials\/(resume|project)\/[^/]+$/.test(pathname)) return "materials";
  if (pathname === "/recommendations") return "recommendations";
  if (/^\/growth(?:\/[^/]+)?$/.test(pathname)) return "growth";
  if (pathname === "/reports" || /^\/reports\/[^/]+$/.test(pathname)
    || pathname === "/jobs" || /^\/jobs\/(?!new$|mine$|manage$)[^/]+$/.test(pathname)) return "matching";
  return null;
}

export function flowStepsForLocation(pathname: string) {
  const reportDetail = /^\/reports\/[^/]+$/.test(pathname);
  const project = pathname.match(/^\/materials\/project\/([^/]+)$/)?.[1];
  return FLOW_STEPS.map(step => ({ ...step,
    href: step.key === "application" && reportDetail ? `${pathname}#application-submit`
      : step.key === "growth" ? `/portfolio?${new URLSearchParams({add:"project",...(project?{sourceProjectVersion:project}:{}),...(reportDetail?{sourceReport:pathname.split("/")[2]}:{})})}` : step.href,
  }));
}
