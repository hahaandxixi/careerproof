"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "./AuthProvider";
import NotificationLink from "./NotificationLink";
import StudentAccountMenu from "./StudentAccountMenu";
import AccountMenu from "./AccountMenu";
import LoginLink from "./LoginLink";
import { errorMessage } from "@/lib/api/client";

export default function SiteHeader() {
  const { user, status, logout, reload } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const current = (href: string) => pathname === href ||
    (href === "/portfolio" && pathname.startsWith("/materials/")) ||
    (href === "/jobs/mine" && /^\/jobs\/[^/]+\/applications$/.test(pathname)) ||
    (["/portfolio", "/reports", "/growth", "/applications"].includes(href) && pathname.startsWith(`${href}/`)) ||
    (href === "/jobs" && (pathname === "/recommendations" || /^\/jobs\/(?!new$|mine$|manage$)[^/]+$/.test(pathname))) ? "page" as const : undefined;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function handleLogout() {
    setBusy(true); setError("");
    try { await logout(); router.push("/"); router.refresh(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <header className={`site-header sticky top-0 z-10 border-b ${!user ? "site-header-public" : ""}`}>
    <div className="site-header-inner mx-auto max-w-6xl px-4">
      <Link href="/" className="site-brand shrink-0 py-2 font-semibold">职证 CareerProof</Link>
      <nav aria-label="主导航" className="site-primary-nav text-sm">
        {user?.role === "student" ? <>
          <Link href="/portfolio" aria-current={current("/portfolio")}>我的材料</Link>
          <Link href="/jobs" aria-current={current("/jobs")}>发现岗位</Link>
          <Link href="/reports" aria-current={current("/reports")}>我的报告</Link>
          <Link href="/applications" aria-current={current("/applications")}>我的投递</Link>
        </> : <>
          <Link href="/jobs" aria-current={current("/jobs")}>岗位发现</Link>
          {(user?.role === "enterprise" || user?.role === "admin") && <>
            <Link href="/jobs/mine" aria-current={current("/jobs/mine")}>岗位管理</Link>
            <Link href="/jobs/new" aria-current={current("/jobs/new")}>发布岗位</Link>
          </>}
          {user?.role === "admin" && <Link href="/reports" aria-current={current("/reports")}>匹配报告</Link>}
        </>}
      </nav>
      <div className="site-account flex min-w-0 items-center justify-end gap-3 text-sm">

        {status === "loading" ? <span className="text-xs text-slate-300">确认会话中…</span> :
          status === "error" ? <button onClick={() => void reload()} className="min-h-11 text-amber-200">连接异常 · 重试</button> :
          user?.role === "student" ? <NotificationLink render={count => <StudentAccountMenu name={user.displayName} unreadCount={count} busy={busy} onLogout={() => void handleLogout()} />} /> :
          user?.role === "enterprise" ? <NotificationLink render={count => <AccountMenu role="enterprise" name={user.displayName} unreadCount={count} busy={busy} onLogout={() => void handleLogout()} />} /> :
          user ? <><span className="max-w-28 truncate text-slate-300" title={user.displayName}>{user.displayName}</span><button className="min-h-11" disabled={busy} onClick={handleLogout}>{busy ? "退出中…" : "退出"}</button></> :
          <><LoginLink className="inline-flex min-h-11 items-center">登录</LoginLink><LoginLink register className="inline-flex min-h-11 items-center rounded-lg bg-indigo-600 px-3 text-white hover:bg-indigo-500">注册</LoginLink></>}
      </div>
    </div>
    {error && <p role="alert" className="mx-auto max-w-6xl px-4 pb-3 text-sm text-rose-200">{error}</p>}
  </header>;
}
