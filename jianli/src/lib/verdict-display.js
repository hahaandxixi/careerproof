/** Display wording only. Historical verdict values and scores remain unchanged. */
/** @type {Record<string, string>} */
export const VERDICT_LABELS = {
  supported: "有证据支持",
  partial: "部分证据支持",
  claimed_only: "仅简历声明",
  gap: "材料待补充",
  unsupported: "规则暂未支持",
  verified: "有证据支持",
};

/** @type {Record<string, string>} */
export const APPLICATION_STATUS_LABELS = {
  submitted: "已投递",
  viewed: "已查看",
  downloaded: "已下载",
  replied: "已回复",
  withdrawn: "已撤回授权",
};

/** @param {string | null | undefined} verdict */
export function verdictLabel(verdict) {
  if (!verdict || verdict === "not_evaluated") return "尚未评估";
  return VERDICT_LABELS[verdict] ?? verdict;
}
