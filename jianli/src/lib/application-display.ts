// 传智杯44：投递展示口径。状态/回复文案与“下一动作”集中在这里，
// 供 ApplicationList 卡片与回归测试共用；文案不把查看或下载推断为录用进展。
export const APPLICATION_STATUS_TEXT: Record<string, string> = {
  submitted: "已投递",
  viewed: "企业已查看报告，尚未回复",
  downloaded: "平台已交付简历下载，尚未回复",
  replied: "企业已回复",
  withdrawn: "已撤回授权",
};

export const APPLICATION_REPLY_TEXT: Record<string, string> = {
  interview: "面试邀请",
  continue: "继续沟通",
  declined: "暂不推进",
};

// 每种状态给求职者一个此刻能执行的下一步；查看/下载都不等于通过筛选。
export const APPLICATION_NEXT_ACTION: Record<string, string> = {
  submitted: "等待企业查看，稍后可刷新状态。",
  viewed: "等待企业回复即可；查看报告不代表通过筛选。",
  downloaded: "等待企业回复即可，无需重复投递；下载也不代表通过筛选。",
  replied: "阅读企业回复并按其内容跟进。",
  withdrawn: "如需继续该岗位，可重新确认授权后再次投递。",
};

export function applicationStatusText(status: string): string {
  return APPLICATION_STATUS_TEXT[status] ?? status;
}

export function applicationReplyText(kind: string): string {
  return APPLICATION_REPLY_TEXT[kind] ?? kind;
}

export function applicationNextAction(status: string): string {
  return APPLICATION_NEXT_ACTION[status] ?? "刷新投递状态获取最新进展。";
}

export function applicationEventsSummary(events: readonly unknown[]): string {
  return `投递记录（${events.length} 条）`;
}
