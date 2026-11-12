/** Display wording only. Historical verdict values and scores remain unchanged. */
/** @type {Record<string, string>} */
export const VERDICT_LABELS = {
  supported: "有证据支持",
  partial: "材料待补充",
  claimed_only: "仅简历声明",
  gap: "材料待补充",
  unsupported: "规则暂未支持",
  verified: "有证据支持",
};

/** @param {string} verdict */
export function isMaterialGap(verdict) {
  return verdict === "gap" || verdict === "partial";
}

export const EVIDENCE_FILTERS = [
  ["supported_only", VERDICT_LABELS.supported],
  ["needs_material", VERDICT_LABELS.gap],
  ["claimed_only", VERDICT_LABELS.claimed_only],
  ["unsupported", VERDICT_LABELS.unsupported],
];

/** @type {Record<string, string>} */
export const APPLICATION_STATUS_LABELS = {
  submitted: "已投递",
  viewed: "企业已查看",
  downloaded: "简历下载已交付",
  replied: "企业已回复",
  withdrawn: "已撤回授权",
};

/** @param {string | null | undefined} verdict */
export function verdictLabel(verdict) {
  if (!verdict || verdict === "not_evaluated") return "尚未评估";
  return VERDICT_LABELS[verdict] ?? verdict;
}
