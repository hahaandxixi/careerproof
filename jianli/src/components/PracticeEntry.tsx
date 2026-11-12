"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api/client";

/** Lightweight entry from one saved report requirement into the shared practice page.
 * Opening a session never calls the model; consent is collected on that page. */
export default function PracticeEntry({ reportId, requirementId }: { reportId: string; requirementId: string }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "opening">("idle");
  const [error, setError] = useState("");
  const open = async () => {
    setState("opening");
    setError("");
    try {
      const { session } = await api.createInterviewSession(reportId, { requirementId });
      router.push(`/interview/${session.id}`);
    } catch (reason) {
      setError(errorMessage(reason));
      setState("idle");
    }
  };
  return <div className="mt-2 flex flex-wrap items-center gap-2">
    <button type="button" className="btn-secondary btn-compact" disabled={state === "opening"} onClick={() => void open()}>
      {state === "opening" ? "正在打开练习…" : "模拟面试 · 练这一项"}
    </button>
    <span className="text-xs text-slate-500">先确认发送范围，再生成首问</span>
    {error && <span role="alert" className="text-xs text-rose-700">{error}</span>}
  </div>;
}
