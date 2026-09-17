import type { PipelineStep } from "@/lib/agent/pipeline";

/** 展示 Agent 工作流的可追踪步骤（回应「工具调用过程可见」） */
export default function PipelineSteps({ steps }: { steps: PipelineStep[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((s) => (
        <li key={s.step} className="flex gap-3">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-semibold text-white">
            {s.step}
          </span>
          <div className="text-sm">
            <span className="font-medium text-slate-700">{s.name}</span>
            <span className="text-slate-500"> · {s.detail}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}
