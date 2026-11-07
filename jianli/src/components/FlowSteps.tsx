"use client";
import Link from "next/link";
import { useId, useState } from "react";
import type { FlowStepKey } from "@/lib/flow-steps";
import { navigateEvidenceFragment } from "@/lib/evidence-anchor";

export default function FlowSteps({ steps, currentKey }: {
  steps: readonly { key: FlowStepKey; label: string; href: string | null; unavailableReason?: string }[];
  currentKey: FlowStepKey;
}) {
  const [expanded, setExpanded] = useState(false);
  const guideId = useId();
  return <div className="flow-guide mb-4">
    <button type="button" aria-expanded={expanded} aria-controls={guideId} onClick={() => setExpanded(value => !value)} className="flex min-h-11 w-full items-center justify-between gap-3 text-left text-sm sm:hidden">
      <span className="font-medium text-indigo-800">{steps.find(step => step.key === currentKey)?.label}</span>
      <span className="shrink-0 text-slate-600">{expanded ? "收起流程 −" : "完整流程 +"}</span>
    </button>
    <nav id={guideId} aria-label="学生操作指南" className={`student-flow ${expanded ? "block" : "hidden sm:block"}`}>
      <ol>{steps.map((step, index) => <li key={step.key} aria-current={step.key === currentKey ? "step" : undefined}>
        {index > 0 && <span className="flow-arrow" aria-hidden="true">→</span>}
        {step.href && step.key !== currentKey ? <Link href={step.href} className="flow-step" onClick={event => {
          if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
          const currentPath = window.location.pathname;
          if (!step.href?.startsWith(`${currentPath}#`)) return;
          event.preventDefault();
          navigateEvidenceFragment(step.href.slice(currentPath.length));
        }}>
          <span className="flow-number" aria-hidden="true">{index + 1}</span><span>{step.label}</span>
        </Link> : <span className="flow-step" title={step.unavailableReason}>
          <span className="flow-number" aria-hidden="true">{index + 1}</span><span>{step.label}</span>
        </span>}
        {step.unavailableReason && <span className="flow-unavailable">{step.unavailableReason}</span>}
      </li>)}</ol>
    </nav>
  </div>;
}
