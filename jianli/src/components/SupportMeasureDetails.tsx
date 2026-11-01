import { formatRawSupportNumber, supportScaleNote, type SupportScale } from "@/lib/support-index.js";

/** Used inside existing measurement details; never rewrites the saved report text. */
export default function SupportMeasureDetails({raw, formulaVersion, scale}: {
  raw: number|null|undefined; formulaVersion?: string|null; scale: SupportScale;
}) {
  return <><p>原始分值 {formatRawSupportNumber(raw)} · 规则 {formulaVersion || "未记录"}</p>
    <p className="mt-1 leading-6">{supportScaleNote(scale)}</p></>;
}
