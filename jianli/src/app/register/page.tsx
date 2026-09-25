"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { errorMessage, type UserRole } from "@/lib/api/client";

type PublicRole = Exclude<UserRole, "admin">;

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<PublicRole>("student");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("密码至少需要8个字符");
      return;
    }
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }
    setSubmitting(true);
    try {
      const user = await register({
        displayName: displayName.trim(),
        email: email.trim(),
        password,
        role,
      });
      router.push(user.role === "student" ? "/portfolio" : "/jobs");
      router.refresh();
    } catch (reason) {
      setError(errorMessage(reason));
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="mb-6">
          <p className="text-sm font-medium text-indigo-600">创建账号</p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">加入职证 CareerProof</h1>
          <p className="mt-2 text-sm text-slate-500">学生账号可以上传简历与项目，企业账号用于发布岗位。</p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <fieldset>
            <legend className="text-sm font-medium text-slate-700">账号类型</legend>
            <div className="mt-2 grid grid-cols-2 gap-3">
              {[
                { value: "student" as const, title: "学生", detail: "上传简历与项目" },
                { value: "enterprise" as const, title: "企业", detail: "发布岗位与筛选" },
              ].map((item) => (
                <label
                  key={item.value}
                  className={`cursor-pointer rounded-xl border p-3 transition focus-within:ring-2 focus-within:ring-indigo-600 focus-within:ring-offset-2 ${
                    role === item.value
                      ? "border-indigo-500 bg-indigo-50 ring-2 ring-indigo-100"
                      : "border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <input
                    type="radio"
                    name="role"
                    value={item.value}
                    checked={role === item.value}
                    onChange={() => setRole(item.value)}
                    className="sr-only"
                  />
                  <span className="block text-sm font-semibold text-slate-800">{item.title}</span>
                  <span className="mt-1 block text-xs text-slate-500">{item.detail}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">姓名或显示名称</span>
            <input
              required
              maxLength={100}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              placeholder={role === "student" ? "如：小李" : "如：校园招聘负责人"}
            />
          </label>

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

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">密码</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                placeholder="至少8个字符"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">确认密码</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                placeholder="再次输入密码"
              />
            </label>
          </div>

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
            {submitting ? "注册中…" : "注册并登录"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-slate-500">
          已有账号？
          <Link href="/login" className="ml-1 font-medium text-indigo-600 hover:text-indigo-700">
            返回登录
          </Link>
        </p>
      </div>
    </div>
  );
}
