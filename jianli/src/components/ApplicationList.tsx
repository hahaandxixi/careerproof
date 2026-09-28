"use client";
import { useEffect, useState } from "react";
import { api, errorMessage, type ApplicationView } from "@/lib/api/client";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";

const STATUS:Record<string,string>={submitted:"已投递",viewed:"企业已查看报告，尚未回复",downloaded:"平台已交付简历下载，尚未回复",replied:"企业已回复",withdrawn:"已撤回授权"};
const REPLY:Record<string,string>={interview:"面试邀请",continue:"继续沟通",declined:"暂不推进"};

export default function ApplicationList(){const {user}=useAuth();return <AccessGate roles={["student"]}><Workspace key={user?.id}/></AccessGate>;}
function Workspace(){
  const [items,setItems]=useState<ApplicationView[]>([]), [error,setError]=useState(""), [busy,setBusy]=useState(false);
  const [revokeId,setRevokeId]=useState<string|null>(null);
  async function load(){setBusy(true);setError("");try{setItems(await api.myApplications());}catch(e){setError(errorMessage(e));}finally{setBusy(false);}}
  useEffect(()=>{void load();},[]);
  return <div className="space-y-5"><h1 className="text-3xl font-bold">我的投递</h1><p className="text-sm leading-6 text-slate-600">状态来自平台请求与企业明确回复。查看或下载不代表通过筛选；未回复不能推断录用概率。刷新获取最新状态。</p><button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>void load()}>刷新投递状态</button>
    {error&&<p role="alert" className="text-rose-700">{error}</p>}{!items.length&&!busy&&<p className="panel">暂无投递。先生成匹配报告，再确认分享授权。</p>}
    {items.map(item=><article key={item.id} className="panel space-y-3"><h2 className="text-xl font-semibold">{item.jobTitle}</h2><p className="text-sm">{item.companyName} · {STATUS[item.status]??item.status}</p>{item.replyText&&<blockquote className="rounded-lg bg-indigo-50 p-3 text-sm whitespace-pre-wrap">{REPLY[item.replyKind??""]}：{item.replyText}</blockquote>}<ol className="space-y-2 text-xs text-slate-600">{item.events.map(e=><li key={e.type}>{new Date(e.at).toLocaleString()} · {e.detail}</li>)}</ol>
      {item.status!=="withdrawn"&&(revokeId===item.id?<div className="space-y-2"><p className="text-sm text-amber-800">撤回后企业不能继续访问本份报告或下载。已下载副本无法追回，本期撤回后不能重新投递同岗位。</p><button type="button" className="btn" disabled={busy} onClick={async()=>{setBusy(true);try{await api.withdrawApplication(item.id);setRevokeId(null);await load();}catch(e){setError(errorMessage(e));}finally{setBusy(false);}}}>确认撤回授权</button><button type="button" className="ml-3 text-sm underline" onClick={()=>setRevokeId(null)}>取消</button></div>:<button type="button" className="text-sm text-amber-700 underline" onClick={()=>setRevokeId(item.id)}>撤回投递授权</button>)}
    </article>)}
  </div>;
}
