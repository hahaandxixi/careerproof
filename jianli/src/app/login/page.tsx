"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { errorMessage } from "@/lib/api/client";

export default function LoginPage() {
  const router = useRouter();
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
      router.push(user.role === "student" ? "/portfolio" : "/jobs");
      router.refresh();
    } catch (reason) {
      setError(errorMessage(reason));
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="mb-6">
          <p className="text-sm font-medium text-indigo-600">欢迎回来</p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">登录职证 CareerProof</h1>
          <p className="mt-2 text-sm text-slate-500">继续整理材料，查看属于你的匹配报告。</p>
        </div>

        <Link href="/demo" className="mb-5 block rounded-lg bg-indigo-50 p-3 text-sm text-indigo-700">首次测试？查看演示账号、样例下载和操作指南 →</Link>
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">邮箱</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              placeholder="name@example.com"
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
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
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
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "登录中…" : "登录"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-slate-500">
          还没有账号？
          <Link href="/register" className="ml-1 font-medium text-indigo-600 hover:text-indigo-700">
            立即注册
          </Link>
        </p>
      </div>
    </div>
  );
}
