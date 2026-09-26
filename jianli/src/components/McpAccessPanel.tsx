"use client";

import { useState } from "react";
import { api, errorMessage, type McpGrant } from "@/lib/api/client";

export default function McpAccessPanel({ reportId }: { reportId: string }) {
  const [consent, setConsent] = useState(false);
  const [history, setHistory] = useState(false);
  const [grant, setGrant] = useState<McpGrant | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function issue() {
    if (!consent || busy || grant) return;
    setBusy(true); setMessage("");
    try {
      const previous = history ? await api.previousComparison(reportId) : null;
      if (history && !previous) { setMessage("没有可授权的上一份同岗位报告，请取消勾选后继续。"); return; }
      const ids = previous ? [previous.baseId, reportId] : [reportId];
      setGrant(await api.issueMcpGrant(ids));
    } catch (error) { setMessage(errorMessage(error)); }
    finally { setBusy(false); }
  }
  async function revoke() {
    if (!grant || busy) return;
    setBusy(true); setMessage("");
    try { await api.revokeMcpGrant(grant.grantId); setGrant(null); setMessage("授权已撤销，客户端不能再读取。"); }
    catch (error) { setMessage(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <details className="card p-5">
    <summary className="cursor-pointer text-sm font-medium">外部工具只读访问（可选）</summary>
    <div className="mt-4 space-y-4 text-sm">
      <p className="leading-6 text-slate-600">允许你选择的 MCP 客户端检索本报告证据、读取摘要和比较已授权报告。客户端可能把内容发送给其模型服务；自动脱敏不能保证清除全部隐私。请先检查材料，选择可信客户端。</p>
      <label className="flex items-start gap-2"><input type="checkbox" checked={history} disabled={!!grant || busy} onChange={e => setHistory(e.target.checked)} />同时授权上一份同岗位报告，用于比较（不会授权其他报告）</label>
      <label className="flex items-start gap-2"><input type="checkbox" checked={consent} disabled={!!grant || busy} onChange={e => setConsent(e.target.checked)} />我已检查敏感信息，同意把选定报告的脱敏摘要和证据提供给我的外部客户端</label>
      {!grant ? <button className="btn-secondary" disabled={!consent || busy} onClick={issue}>生成十分钟只读授权</button> : <div className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50 p-4">
        <p>授权 {grant.reportIds.length} 份报告；有效至 {new Date(grant.expiresAt).toLocaleTimeString("zh-CN")}，最多调用 40 次。不能上传、修改或复核。</p>
        <label className="block text-xs">临时凭证（不会写入浏览器存储）<input className="field mt-2" type="password" readOnly autoComplete="off" value={grant.token} /></label>
        <div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={async () => { try { await navigator.clipboard.writeText(grant.token); setMessage("临时凭证已复制。只放入本机客户端环境变量，勿分享或提交。"); } catch { setMessage("无法复制，请检查浏览器剪贴板权限。"); } }}>复制临时凭证</button><button className="btn-secondary" disabled={busy} onClick={revoke}>立即撤销</button></div>
        <p className="break-all text-xs text-slate-600">授权编号：{grant.grantId}。刷新页面会隐藏凭证，服务端仍在到期或撤销前有效；需要继续管理时请先撤销再离开。</p>
      </div>}
      {message && <p role="status" className="break-words text-sm text-slate-700">{message}</p>}
    </div>
  </details>;
}
