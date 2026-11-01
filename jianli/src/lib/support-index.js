// Display only. evidence-v3 and v4 use high=.65 and final_score=rule_score*100.
// c458812 changes the detector v3→v4 without changing those weights.
const RULE_CAPS = Object.freeze({ "evidence-v3": 65, "evidence-v4": 65 });
export const SUPPORT_INDEX_LABEL = "材料支持度指数";
// Explicit metadata for the public interface fixture, never inferred for saved reports.
export const DEMO_SUPPORT_SCALE = Object.freeze({ formulaVersion: "synthetic-only", cap: 65 });

/** @typedef {{formulaVersion?: string|null}} SupportAxis */
/** @typedef {{formulaVersion: string, cap: number}} SampleScale */
/** @typedef {{mode: 'index'|'raw', denominator: number, label: string, reason: string, versions: string[], sample?: SampleScale}} SupportScale */

/** @param {string|null|undefined} version @param {SampleScale} [sample] */
function confirmedCap(version, sample) {
  if (version && Object.hasOwn(RULE_CAPS, version)) return RULE_CAPS[/** @type {keyof typeof RULE_CAPS} */ (version)];
  return sample && version === sample.formulaVersion && Number.isFinite(sample.cap) && sample.cap > 0 ? sample.cap : null;
}

/** Resolve once from every axis, never from the selected requirement or observed maximum.
 * @param {readonly SupportAxis[]} axes @param {SampleScale} [sample] @returns {SupportScale}
 */
export function resolveSupportScale(axes, sample) {
  const versions = [...new Set(axes.map(d => d.formulaVersion || "未记录"))];
  const caps = axes.map(d => confirmedCap(d.formulaVersion, sample));
  const cap = caps[0];
  if (axes.length && cap != null && caps.every(value => value === cap)) {
    return { mode: "index", denominator: cap, label: SUPPORT_INDEX_LABEL, reason: "", versions, sample };
  }
  return { mode: "raw", denominator: 100, label: "原报告材料支持度（未换算）", versions, sample,
    reason: "整图规则上限未能一致确认，保留原始分值；未换算为指数。" };
}

/** @param {unknown} value */
export function formatSupportNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? String(Number(value.toFixed(1))) : String(value ?? "未记录");
}

/** Original API numbers must not use the rounded index formatter.
 * @param {unknown} value
 */
export function formatRawSupportNumber(value) { return String(value ?? "未记录"); }

/** No clamping: anomalous raw values stay traceable but are not plotted.
 * @param {{score?: number|null, formulaVersion?: string|null, verdict: string}} axis @param {SupportScale} scale
 */
export function supportMeasure(axis, scale) {
  const raw = axis.score;
  const cap = confirmedCap(axis.formulaVersion, scale.sample);
  let issue = "";
  if (raw == null) issue = "原始分值未记录";
  else if (typeof raw !== "number" || !Number.isFinite(raw)) issue = "原始分值不是有限数值";
  else if (raw < 0) issue = "原始分值小于0，无法按本规则换算或绘点";
  else if (scale.mode === "index" && cap !== scale.denominator) issue = "本项规则与整图换算依据不一致，无法换算或绘点";
  else if (cap != null && raw > cap) issue = `原始分值超过已确认规则上限${cap}，无法按本规则换算或绘点`;
  else if (raw > scale.denominator) issue = "原始分值超出旧图坐标范围，无法绘点";
  const numeric = !issue && typeof raw === "number";
  const ratio = numeric ? raw / scale.denominator : null;
  const value = ratio == null ? null : scale.mode === "index" ? ratio * 100 : raw;
  const plottable = ["supported", "verified", "partial", "claimed_only"].includes(axis.verdict);
  return { raw, value, text: scale.mode === "index" ? formatSupportNumber(value) : formatRawSupportNumber(value), ratio: plottable ? ratio : null, issue };
}

/** @param {SupportScale} scale */
export function supportScaleNote(scale) {
  return scale.mode === "index"
    ? `指数 = 原始分值 ÷ ${scale.denominator} × 100。100对应全局规则上限，不是能力或录用分数；部分复杂要求的规则上限更低。`
    : scale.reason;
}
