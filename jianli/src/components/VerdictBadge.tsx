import { verdictLabel } from "@/lib/verdict-display.js";

const COLORS: Record<string, string> = {
  verified: "bg-emerald-100 text-emerald-700",
  supported: "bg-emerald-100 text-emerald-700",
  partial: "bg-indigo-100 text-indigo-700",
  claimed_only: "bg-amber-100 text-amber-700",
  gap: "bg-rose-100 text-rose-700",
  unsupported: "bg-slate-100 text-slate-700",
};

export default function VerdictBadge({ verdict }: { verdict: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${COLORS[verdict] ?? COLORS.unsupported}`}
    >
      {verdictLabel(verdict)}
    </span>
  );
}
