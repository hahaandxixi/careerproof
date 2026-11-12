import type { MatchReport } from "@/lib/api/domain";
import { displayMaterialTitle } from "@/lib/demo-display-identity.js";

type Materials = MatchReport["materials"];

export function reportMaterialCount(materials?: Materials) {
  return materials?.length ? `本次材料 ${materials.length} 份` : "材料版本未记录";
}

export function ReportMaterialList({ materials }: { materials: Materials }) {
  return <ul className="space-y-1 break-words">
    {materials.map(material => <li key={`${material.kind}-${material.id}`}>{displayMaterialTitle(material.title, material.id)} · 第 {material.versionNumber} 版</li>)}
  </ul>;
}

export default function ReportMaterialVersions({ materials }: { materials: Materials }) {
  if (!materials.length) return <p className="text-sm text-slate-600">{reportMaterialCount(materials)}</p>;
  return <details className="min-w-0 text-sm text-slate-600">
    <summary className="disclosure">{reportMaterialCount(materials)}</summary>
    <ReportMaterialList materials={materials} />
  </details>;
}
