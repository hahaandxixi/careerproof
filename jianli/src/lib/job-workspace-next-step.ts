type MaterialVersion = {
  status: string;
  taskId?: string | null;
  originalFilename?: string | null;
  createdAt: string;
};

export function jobWorkspaceNextStep({ versions, report, incomplete }: {
  versions: MaterialVersion[];
  report?: { id: string; title: string };
  incomplete: boolean;
}) {
  const active = versions.filter(version => version.taskId && ["pending", "running", "failed"].includes(version.status))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
  if (active) {
    const failed = active.status === "failed";
    const status = failed ? "处理失败" : active.status === "pending" ? "等待处理" : "正在处理";
    return {
      description: `${status} · ${active.originalFilename ?? "已上传材料"}`,
      href: `/tasks/${active.taskId}`,
      action: failed ? "处理上传问题" : "查看材料处理",
    };
  }
  if (report) return { description: report.title, href: `/reports/${report.id}`, action: "继续核对报告" };
  if (incomplete) return { description: "部分材料或报告暂未读取。", action: "重试读取" };
  if (versions.some(version => version.status === "completed")) {
    return { description: "已有可用材料，可以选择岗位生成报告。", href: "/jobs", action: "发现岗位" };
  }
  return { description: "上传材料后，可以按岗位核对证据。", href: "/portfolio", action: "准备材料" };
}
