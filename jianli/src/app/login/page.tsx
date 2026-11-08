"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { api, errorMessage } from "@/lib/api/client";

import { authEntry, checkedReturnPath, safeReturnPath } from "@/lib/auth-return";

export default function LoginPage() {
  const router = useRouter();
  const [returnTo, setReturnTo] = useState<string | null>(null);
  useEffect(() => { setReturnTo(safeReturnPath(new URLSearchParams(window.location.search).get("next"))); }, []);
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const user = await login(email.trim(), password);
      router.replace(await checkedReturnPath(returnTo, user.role, api));
      router.refresh();
    } catch (reason) {
      setError(errorMessage(reason));
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <div className="workspace-sheet p-5 sm:p-7">
        <div className="mb-6">
          <h1 className="page-title">登录</h1>
          <p className="mt-2 text-sm text-slate-500">继续整理材料，查看属于你的匹配报告。</p>
        </div>

        <Link href="/demo" className="mb-5 block rounded-lg bg-indigo-50 p-3 text-sm text-indigo-700">首次测试？查看演示账号、样例下载和操作指南 →</Link>
        {returnTo && <p className="mb-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">登录后返回刚才的页面；仅继续你有权访问的内容。</p>}
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">账号（邮箱）</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="field mt-1"
              placeholder="请输入邮箱账号"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">密码</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="field mt-1"
              placeholder="请输入密码"
            />
          </label>

          {error && (
            <div role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn w-full"
          >
            {submitting ? "登录中…" : "登录"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-slate-500">
          还没有账号？
          <Link href={authEntry("/register", returnTo)} className="ml-1 font-medium text-indigo-600 hover:text-indigo-700">
            立即注册
          </Link>
        </p>
      </div>
    </div>
  );
}

