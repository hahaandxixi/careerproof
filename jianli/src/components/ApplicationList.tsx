"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { ApplicationView } from "@/lib/api/client";
import { applicationAnchorId, clearApplicationAnchor, includeApplicationTarget } from "@/lib/notification-session";
import { createApplicationAnchorRevealer } from "@/lib/application-anchor";
import { createApplicationListSession, type ApplicationListState } from "@/lib/application-list-session";
import { createRefreshGate } from "@/lib/refresh-gate";
import { applicationEventsSummary, applicationNextAction, applicationReplyText, applicationStatusText } from "@/lib/application-display";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";

// 传智杯44：单条投递卡片是无状态展示组件，突出岗位/公司/状态/企业回复/下一动作；
// 完整投递记录默认折叠；撤回二次确认、重新投递入口与报告/引用链接协议保持不变。
export function ApplicationItemCard({item, confirming, busy, onRequestWithdraw, onConfirmWithdraw, onCancelWithdraw}: {
  item: ApplicationView;
  confirming: boolean;
  busy: boolean;
  onRequestWithdraw(id: string): void;
  onConfirmWithdraw(id: string): void;
  onCancelWithdraw(): void;
}) {
  const reportHref = `/reports/${encodeURIComponent(item.reportId)}`;
  return <article id={`application-${item.id}`} className="panel space-y-3">
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <h2 className="text-xl font-semibold">{item.jobTitle}</h2>
      <p className="text-sm text-slate-700">{item.companyName} · {applicationStatusText(item.status)}</p>
    </div>
    <p className="text-sm text-indigo-700"><span className="font-medium">下一步：</span>{applicationNextAction(item.status)}</p>
    {item.replyText&&<blockquote className="rounded-lg bg-indigo-50 p-3 text-sm whitespace-pre-wrap">{applicationReplyText(item.replyKind??"")}：{item.replyText}</blockquote>}
    <p className="text-sm"><Link className="text-indigo-700 underline" href={reportHref}>查看本次投递的原报告</Link>{item.replyText&&<span className="ml-2 text-xs text-slate-500">后续新报告不会替换本次投递。</span>}</p>
    {!!item.replyReferences?.length&&<div className="rounded-lg bg-slate-50 p-3 text-sm"><p className="font-medium">企业回复对应的原报告位置</p><ul className="mt-2 space-y-2">{item.replyReferences.map(reference=><li key={reference.requirementId} className="break-words"><Link className="text-indigo-700 underline" href={`${reportHref}#requirement-${encodeURIComponent(reference.requirementId)}`}>{`第${item.dimensions.findIndex(d=>d.requirementId===reference.requirementId)+1}项：`}{item.dimensions.find(d=>d.requirementId===reference.requirementId)?.title || "查看岗位要求"}</Link><Link className="ml-2 text-xs text-indigo-700 underline" href={`${reportHref}?enterpriseReply=${encodeURIComponent(reference.requirementId)}#requirement-${encodeURIComponent(reference.requirementId)}`}>带着这项问题补证 →</Link>{reference.citationIds.length>0&&<span className="ml-2 text-xs">引用：{reference.citationIds.map((id,index)=><span key={id}>{index>0?"、":""}<Link className="text-indigo-700 underline" href={`${reportHref}#citation-${encodeURIComponent(id)}`}>{id}</Link></span>)}</span>}</li>)}</ul><p className="mt-2 text-xs text-slate-500">这些链接定位本次投递的原报告；引用不自动证明能力或本人贡献。</p></div>}
    {item.status==="withdrawn"&&<p className="text-sm text-slate-600">本次授权已撤回。<Link className="ml-2 text-indigo-700 underline" href={`${reportHref}#application-submit`}>重新确认授权并投递</Link>；也可从新版报告投递，原记录与企业回复不会被覆盖。</p>}
    {item.status!=="withdrawn"&&(confirming
      ?<div className="space-y-2"><p className="text-sm text-amber-800">撤回后企业不能继续访问本份报告或下载。已下载副本无法追回，如需再次分享，可从报告页重新确认授权；将创建新的投递，旧记录继续保留。</p><button type="button" className="btn" disabled={busy} onClick={()=>onConfirmWithdraw(item.id)}>确认撤回授权</button><button type="button" className="ml-3 text-sm underline" onClick={onCancelWithdraw}>取消</button></div>
      :<button type="button" className="text-sm text-amber-700 underline" onClick={()=>onRequestWithdraw(item.id)}>撤回投递授权</button>)}
    <details className="text-xs text-slate-600">
      <summary className="cursor-pointer select-none">{applicationEventsSummary(item.events)}</summary>
      <ol className="mt-2 space-y-2">{item.events.map(e=><li key={e.type}>{new Date(e.at).toLocaleString()} · {e.detail}</li>)}</ol>
    </details>
  </article>;
}

export default function ApplicationList(){const {user}=useAuth();return <AccessGate roles={["student"]}><Workspace key={user?.id}/></AccessGate>;}
function Workspace(){
  const [state,setState]=useState<ApplicationListState>({items:[],loading:true,error:""});
  const [anchorNotice,setAnchorNotice]=useState("");
  const {items,error,loading:busy}=state;
  const [revokeId,setRevokeId]=useState<string|null>(null);
  const session=useMemo(()=>createApplicationListSession({
    list:async()=>{const id=applicationAnchorId();return includeApplicationTarget(await api.myApplications(),api.applicationDetail,id,undefined,()=>{if(id)clearApplicationAnchor(id);setAnchorNotice("通知对应的投递已不可访问；下方仍显示你的其他投递。");});},
    withdraw:api.withdrawApplication,errorMessage,
  },setState),[]);
  useEffect(()=>{
    session.activate();
    const refresh=()=>{if(document.visibilityState!=="hidden"){setRevokeId(null);void session.refresh();}};
    // B-06：返回页面时 visibilitychange、focus 紧邻触发，合并为一次刷新；hashchange 是锚点导航，保持直连。
    const gate=createRefreshGate(refresh);
    const visibility=()=>{setRevokeId(null);if(document.visibilityState==="hidden"){session.clear();gate.reset();}else gate.trigger();};
    const focusWindow=()=>{if(document.visibilityState!=="hidden")gate.trigger();};
    // 真正离开窗口后返回应重新读取，去重只合并同一次返回的事件串。
    const blurWindow=()=>gate.reset();
    if(document.visibilityState!=="hidden")gate.trigger();else session.clear();
    document.addEventListener("visibilitychange",visibility);window.addEventListener("focus",focusWindow);window.addEventListener("blur",blurWindow);window.addEventListener("hashchange",refresh);
    return ()=>{session.dispose();document.removeEventListener("visibilitychange",visibility);window.removeEventListener("focus",focusWindow);window.removeEventListener("blur",blurWindow);window.removeEventListener("hashchange",refresh);};
  },[session]);
  // B-15：只对新出现的显式锚点导航（进入页面或 hashchange）滚动一次；刷新、撤回造成的 items 变化不再劫持视口。目标不可访问的提示仍由 includeApplicationTarget 的回调负责。
  const anchor=useMemo(()=>createApplicationAnchorRevealer({parseAnchorId:applicationAnchorId}),[]);
  useEffect(()=>{anchor.attempt(items.map(item=>item.id),items.map(item=>item.id));},[anchor,items]);
  return <div className="space-y-5"><h1 className="text-3xl font-bold">我的投递</h1>
    <details className="text-sm leading-6 text-slate-600"><summary className="cursor-pointer select-none text-indigo-700">状态与刷新说明</summary><p className="mt-2">状态来自平台请求与企业明确回复。查看或下载不代表通过筛选；未回复不能推断录用概率。刷新获取最新状态。</p></details>
    <button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>{setRevokeId(null);void session.refresh();}}>刷新投递状态</button>
    {error&&<p role="alert" className="text-rose-700">{error}</p>}{anchorNotice&&<p role="status" className="text-amber-800">{anchorNotice}</p>}{busy&&<p role="status">正在核对本人投递…</p>}{!items.length&&!busy&&!error&&<p className="panel">暂无投递。先生成匹配报告，再确认分享授权。</p>}
    {items.map(item=><ApplicationItemCard key={item.id} item={item} confirming={revokeId===item.id} busy={busy} onRequestWithdraw={setRevokeId} onConfirmWithdraw={id=>{setRevokeId(null);void session.withdraw(id);}} onCancelWithdraw={()=>setRevokeId(null)} />)}
  </div>;
}
