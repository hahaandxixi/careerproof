type MaterialVersion = {
  status: string;
  taskId?: string | null;
  originalFilename?: string | null;
  createdAt: string;
};

export function jobWorkspaceNextStep({ versions, incomplete }: {
  versions: MaterialVersion[];
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
  if (incomplete) return { description: "部分材料或报告暂未读取。", action: "重试读取" };
  if (versions.some(version => version.status === "completed")) {
    return { description: "暂无待处理事项。", href: "/jobs", action: "发现岗位" };
  }
  return { description: "暂无待处理事项。", href: "/portfolio", action: "准备材料" };
}
