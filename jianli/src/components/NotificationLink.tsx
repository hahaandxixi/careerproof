"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api/client";
import { createRefreshGate } from "@/lib/refresh-gate";
import { useAuth } from "./AuthProvider";

export default function NotificationLink({ render }: { render?: (count: number | null) => ReactNode } = {}) {
  const { user } = useAuth();
  return user && ["student", "enterprise"].includes(user.role) ? <Counter key={user.id} render={render} /> : null;
}
function Counter({ render }: { render?: (count: number | null) => ReactNode }) {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    // 票据与取消标志都收在 effect 闭包内：重载取最新票据生效，卸载后一律丢弃，
    // 不需要跨 effect 的 ref 计数器。
    let cancelled = false;
    let ticket = 0;
    const load = () => {
      const mine = ++ticket;
      if (document.visibilityState === "hidden") { if (!cancelled) setCount(null); return; }
      void api.notificationCount().then(result => { if (!cancelled && mine === ticket) setCount(result.unreadCount); })
        .catch(() => { if (!cancelled && mine === ticket) setCount(null); });
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
    return () => { cancelled = true; window.removeEventListener("notifications-changed", load);
      window.removeEventListener("focus", presenceLoad); window.removeEventListener("blur", blurWindow); document.removeEventListener("visibilitychange", presenceLoad); };
  }, []);
  if (render) return render(count);
  return <Link href="/notifications">通知{count === null ? "" : `（${count} 未读）`}</Link>;
}
