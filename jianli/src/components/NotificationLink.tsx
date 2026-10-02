"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { useAuth } from "./AuthProvider";

export default function NotificationLink() {
  const { user } = useAuth();
  return user && ["student", "enterprise"].includes(user.role) ? <Counter key={user.id} /> : null;
}
function Counter() {
  const [count, setCount] = useState<number | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    const load = () => {
      const ticket = ++generation.current;
      if (document.visibilityState === "hidden") { setCount(null); return; }
      void api.notificationCount().then(result => { if (ticket === generation.current) setCount(result.unreadCount); })
        .catch(() => { if (ticket === generation.current) setCount(null); });
    };
    load();
    window.addEventListener("notifications-changed", load); window.addEventListener("focus", load);
    document.addEventListener("visibilitychange", load);
    return () => { ++generation.current; window.removeEventListener("notifications-changed", load);
      window.removeEventListener("focus", load); document.removeEventListener("visibilitychange", load); };
  }, []);
  return <Link href="/notifications">通知{count === null ? "" : `（${count} 未读）`}</Link>;
}
