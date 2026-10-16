"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "./AuthProvider";
import NotificationLink from "./NotificationLink";
import StudentAccountMenu from "./StudentAccountMenu";
import { errorMessage } from "@/lib/api/client";

export default function SiteHeader() {
  const { user, status, logout, reload } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const current = (href: string) => pathname === href || (href === "/reports" && pathname.startsWith("/reports/"))
    || (href === "/jobs" && /^\/jobs\/(?!new$|mine$|manage$)[^/]+$/.test(pathname)) ? "page" as const : undefined;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function handleLogout() {
    setBusy(true); setError("");
    try { await logout(); router.push("/"); router.refresh(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <header className="site-header sticky top-0 z-10 border-b">
    <div className="mx-auto flex min-h-16 max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
      <Link href="/" className="site-brand font-semibold">职证 CareerProof</Link>
      <nav aria-label="主导航" className="site-primary-nav flex flex-wrap items-center gap-3 text-sm">
        <Link href="/jobs" aria-current={current("/jobs")}>岗位发现</Link>
        {user?.role === "student" && <Link href="/recommendations" aria-current={current("/recommendations")}>职业推荐</Link>}
        {(user?.role === "student" || user?.role === "admin") && <Link href="/reports" aria-current={current("/reports")}>我的匹配报告</Link>}
        {(user?.role === "enterprise" || user?.role === "admin") && <>
          <Link href="/jobs/mine" aria-current={current("/jobs/mine")}>岗位管理</Link><Link href="/jobs/new" aria-current={current("/jobs/new")}>发布岗位</Link>
        </>}
        {user?.role !== "student" && <NotificationLink />}
        {status === "loading" ? <span className="text-slate-300">确认会话中…</span> :
          status === "error" ? <button onClick={() => void reload()} className="text-amber-200">服务连接异常 · 重试</button> :
          user?.role === "student" ? <NotificationLink render={count => <StudentAccountMenu name={user.displayName} unreadCount={count} busy={busy} onLogout={() => void handleLogout()} />} /> :
          user ? <><span className="max-w-28 truncate text-slate-300">{user.displayName}</span><button disabled={busy} onClick={handleLogout}>{busy ? "退出中…" : "退出"}</button></> :
          <><Link href="/login" aria-current={current("/login")}>登录</Link><Link href="/register" aria-current={current("/register")}>注册</Link></>}
      </nav>
    </div>
    {error && <p role="alert" className="mx-auto max-w-6xl px-4 pb-3 text-sm text-rose-200">{error}</p>}
  </header>;
}
