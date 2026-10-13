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
    case "partial": return "bg-indigo-50 text-indigo-900";
    case "claimed_only": return "bg-amber-50 text-amber-900 border-dashed";
    case "gap": return "bg-white text-slate-700 border-dashed";
    default: return "bg-slate-100 text-slate-600";
  }
}
