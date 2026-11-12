// Color describes the saved evidence verdict, never a newly computed score rank.
/**
 * @param {string} verdict
 * @param {number | null} [score]
 */
export function heatmapCellClass(verdict, score = 0) {
  if (score === null || !Number.isFinite(score) || score < 0 || score > 100) {
    return "bg-slate-100 text-slate-600";
  }
  switch (verdict) {
    case "supported":
    case "verified": return "bg-emerald-100 text-emerald-900";
    case "claimed_only": return "bg-amber-50 text-amber-900 border-dashed";
    case "partial":
    case "gap": return "bg-white text-slate-700 border-dashed";
    default: return "bg-slate-100 text-slate-600";
  }
}

/** Review is only known after the matching frozen requirement has been read.
 * @param {{confirmationStatus?: string | null}} [item]
 */
export function heatmapReview(item) {
  if (!item) return { state: "unread", label: "复核未载入" };
  if (item.confirmationStatus === "rejected") return { state: "rejected", label: "本人已驳回 · 需复核" };
  if (item.confirmationStatus === "corrected") return { state: "corrected", label: "本人标记修正 · 需复核" };
  return { state: "read", label: "" };
}
