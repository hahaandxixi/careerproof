import Link from "next/link";
import type { FlowStepKey } from "@/lib/flow-steps";

export default function FlowSteps({ steps, currentKey }: {
  steps: readonly { key: FlowStepKey; label: string; href: string | null }[];
  currentKey: FlowStepKey;
}) {
  return <div className="mb-6">
    <nav aria-label="学生操作指南" className="student-flow">
      <ol>{steps.map((step, index) => <li key={step.key} aria-current={step.key === currentKey ? "step" : undefined}>
        {index > 0 && <span className="flow-arrow" aria-hidden="true">→</span>}
        {step.href && step.key !== currentKey ? <Link href={step.href} className="flow-step">
          <span className="flow-number" aria-hidden="true">{index + 1}</span><span>{step.label}</span>
        </Link> : <span className="flow-step">
          <span className="flow-number" aria-hidden="true">{index + 1}</span><span>{step.label}{step.key === currentKey && <small>当前位置</small>}</span>
        </span>}
      </li>)}</ol>
    </nav>
    <p className="mt-1 text-xs leading-5 text-slate-500 sm:hidden">左右滑动查看全部 {steps.length} 步。</p>
  </div>;
}
