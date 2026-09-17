import type { Verdict } from "@/lib/types";

const CONFIG: Record<Verdict, { label: string; className: string }> = {
  verified: { label: "有证据支持", className: "bg-emerald-100 text-emerald-700" },
  claimed_only: { label: "仅声明", className: "bg-amber-100 text-amber-700" },
  gap: { label: "材料待补充", className: "bg-rose-100 text-rose-700" },
};

export default function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const c = CONFIG[verdict];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${c.className}`}
    >
      {c.label}
    </span>
  );
}
