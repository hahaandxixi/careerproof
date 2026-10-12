"use client";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api/client";
import { createRefreshGate } from "@/lib/refresh-gate";
import { useAuth } from "./AuthProvider";

export default function NotificationLink({ render }: { render?: (count: number | null) => ReactNode } = {}) {
  const { user } = useAuth();
  return user && ["student", "enterprise"].includes(user.role) ? <Counter key={user.id} render={render} /> : null;
}
function Counter({ render }: { render?: (count: number | null) => ReactNode }) {
  const [count, setCount] = useState<number | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    const load = () => {
      const ticket = ++generation.current;
      if (document.visibilityState === "hidden") { setCount(null); return; }
      void api.notificationCount().then(result => { if (ticket === generation.current) setCount(result.unreadCount); })
        .catch(() => { if (ticket === generation.current) setCount(null); });
    };
    // B-06：返回页面时 visibilitychange、focus 紧邻触发，合并为一次请求；
    // notifications-changed 是未读数真实变化信号，保持直连不被合并。
    const gate = createRefreshGate(load);
    const presenceLoad = () => { if (document.visibilityState === "hidden") { load(); gate.reset(); } else gate.trigger(); };
    const blurWindow = () => gate.reset();
    gate.trigger();
    window.addEventListener("notifications-changed", load); window.addEventListener("focus", presenceLoad);
    window.addEventListener("blur", blurWindow);
    document.addEventListener("visibilitychange", presenceLoad);
    return () => { ++generation.current; window.removeEventListener("notifications-changed", load);
      window.removeEventListener("focus", presenceLoad); window.removeEventListener("blur", blurWindow); document.removeEventListener("visibilitychange", presenceLoad); };
  }, []);
  if (render) return render(count);
  return <Link href="/notifications">通知{count === null ? "" : `（${count} 未读）`}</Link>;
}
