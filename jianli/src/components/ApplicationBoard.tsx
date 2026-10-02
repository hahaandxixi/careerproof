"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { applicationAnchorId, includeApplicationTarget, revealApplicationAnchor } from "@/lib/notification-session";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";
import SkillRadar from "./SkillRadar";
import { filterApplications, mixedComparisonBasis } from "@/lib/application-comparison";
import { createApplicationBoardSession, initialApplicationBoardState } from "@/lib/application-board-session";
import ApplicationVerification from "./ApplicationVerification";
import { activeVerificationReplyReferences, appendVerificationReplyQuestion, type VerificationReplyQuestion } from "@/lib/verification-reply-draft";

const VERDICT:Record<string,string>={supported:"有证据",partial:"部分支持",claimed_only:"仅自述",gap:"缺材料",unsupported:"暂不可评",verified:"有证据"};
const STATUS:Record<string,string>={submitted:"待查看",viewed:"已查看",downloaded:"已交付下载",replied:"已回复"};
function cellClass(verdict:string,score:number|null){
  if(verdict==="unsupported"||score===null)return "bg-slate-100 text-slate-500";
  if(verdict==="claimed_only")return "bg-amber-50 text-amber-800 border-dashed";
  if(verdict==="gap")return "bg-white text-slate-600 border-dashed";
  return score>=75?"bg-emerald-100 text-emerald-900":score>=40?"bg-blue-50 text-blue-900":"bg-slate-50 text-slate-700";
}

export default function ApplicationBoard({jobId}:{jobId:string}){
  const {user}=useAuth();
  return <AccessGate roles={["enterprise"]}><Workspace key={`${user?.id}:${jobId}`} jobId={jobId}/></AccessGate>;
}
function Workspace({jobId}:{jobId:string}){
  const [state,setState]=useState(initialApplicationBoardState);
  const {items,selected,error,notice,loading:busy}=state;
  const session=useMemo(()=>createApplicationBoardSession({
    list:async()=>includeApplicationTarget(await api.jobApplications(jobId), api.applicationDetail, applicationAnchorId(), jobId), open:api.openApplication,
    download:api.downloadApplicationResume, reply:api.replyApplication, errorMessage,
  },setState),[jobId]);
  useEffect(()=>{revealApplicationAnchor();},[items]);
  const [query,setQuery]=useState(""),[focus,setFocus]=useState("");
  const [verdict,setVerdict]=useState("");
  const [replyKind,setReplyKind]=useState("continue"),[replyText,setReplyText]=useState(""),[confirmReply,setConfirmReply]=useState(false);
  const [replyDraftNotice,setReplyDraftNotice]=useState("");
  const [replyQuestions,setReplyQuestions]=useState<VerificationReplyQuestion[]>([]);
  const replyReferences=activeVerificationReplyReferences(replyText,replyQuestions);
  const verificationUnavailable=useCallback(()=>{setReplyText("");setReplyQuestions([]);setConfirmReply(false);setReplyDraftNotice("");void session.refresh();},[session]);
  function resetReply(){setReplyText("");setReplyQuestions([]);setConfirmReply(false);setReplyDraftNotice("");}
  function useVerificationQuestion(question: VerificationReplyQuestion){
    const result=appendVerificationReplyQuestion(replyText,question);
    if(result.status==="too_long"){setReplyDraftNotice("回复已接近 2000 字上限，请缩短正文后重试。");return;}
    if(result.status==="duplicate"){setReplyDraftNotice("这条核验问题已在回复草稿中。");return;}
    setReplyText(result.text);
    setReplyQuestions(previous=>[...previous,question]);
    setReplyKind("continue");
    setConfirmReply(false);
    setReplyDraftNotice("已加入可编辑草稿。请对照固定报告核对问题与引用，再确认发送。");
  }
  useEffect(()=>{
    session.activate();
    const refresh=()=>{resetReply();void session.refresh();};
    const visibility=()=>{
      resetReply();
      if(document.visibilityState==="hidden")session.clear();else refresh();
    };
    const focusWindow=()=>{if(document.visibilityState==="visible")refresh();};
    refresh();
    document.addEventListener("visibilitychange",visibility);
    window.addEventListener("focus",focusWindow);
    window.addEventListener("pageshow",refresh);
    return ()=>{session.dispose();document.removeEventListener("visibilitychange",visibility);window.removeEventListener("focus",focusWindow);window.removeEventListener("pageshow",refresh);};
  },[session]);
  const dimensions=Array.from(new Map(items.flatMap(i=>i.dimensions).map(d=>[d.requirementId,d])).values());
  const mixedBasis=mixedComparisonBasis(items);
  const visible=filterApplications(items,query,focus,verdict);
  async function open(id:string){resetReply();await session.open(id);}
  async function download(){await session.download(file=>{const url=URL.createObjectURL(file.blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=file.filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
  return <div className="space-y-5"><h1 className="text-3xl font-bold">已授权投递 · 岗位匹配对照</h1><p className="text-sm leading-6 text-slate-600">只包含向本岗位明确投递的报告。分数来自投递时固定报告，不重新评分；排序仅辅助核验，不代表录用顺序。未投递或已撤回的学生不可见，默认展示最近100份；通知指定的更早投递会单独核对授权后补入。</p>
    <button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>{resetReply();void session.refresh();}}>刷新授权投递</button>
    <p className="text-xs leading-5 text-slate-500">刷新或重新回到此页面会核对授权并收起已打开报告；离开窗口会清空未发送的回复，请发送前再次核对。学生撤回不会追回已下载副本。</p>
    {busy&&<p role="status" className="panel">正在核对授权投递，请稍候…</p>}
    {notice&&<p role="status" className="panel text-amber-800">{notice}</p>}
    {error&&<p role="alert" className="panel text-rose-700">{error} 请刷新授权投递重试，旧报告已清除。</p>}
    {error&&replyText.trim()&&<div className="panel space-y-2 text-sm"><p>回复是否送达尚未确认。以下保留了本页草稿，请先复制，再刷新授权投递并核对该投递的回复状态。</p><textarea className="field" readOnly value={replyText} aria-label="未确认发送的回复草稿"/></div>}
    <div className="panel grid gap-3 sm:grid-cols-3"><label className="text-sm">关键词（姓名、技能或要求）<input type="search" className="field mt-2" value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="text-sm">聚焦岗位要求<select className="field mt-2" value={focus} onChange={e=>setFocus(e.target.value)}><option value="">全部要求</option>{dimensions.map(d=><option key={d.requirementId} value={d.requirementId}>{d.skill||d.title}</option>)}</select></label><label className="text-sm">证据状态筛选<select className="field mt-2" value={verdict} onChange={e=>setVerdict(e.target.value)}><option value="">全部状态</option><option value="supported">有证据或部分支持</option><option value="claimed_only">仅简历自述</option><option value="gap">缺少材料</option><option value="unsupported">暂不可评</option></select></label></div>
    {mixedBasis&&<p role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">投递报告的岗位要求、权重或规则版本不同，当前按投递时间排列，不按分数排名。请打开每份报告核对其原始要求；表格行名仅作定位，格子中的说明来自各自快照。</p>}
    {!items.length&&!busy&&!error&&<p className="panel">暂无已授权投递，请由学生从该岗位的完整报告中确认投递。平台不会从学生库导出未经授权的简历。</p>}
    {!!items.length&&<section className="panel space-y-3"><h2 className="font-semibold">岗位要求 × 投递候选人</h2><p className="text-xs text-slate-500">绿色/蓝色：有证据的分数；虚线：缺材料或仅自述；灰色：不可评。数值为原报告0—100分，权重沿用原报告。点击姓名或格子查看固定报告。</p><div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr><th className="p-3 text-left">岗位要求</th>{visible.map(i=><th id={`application-${i.id}`} key={i.id} className="min-w-36 p-2"><button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>void open(i.id)}>{i.candidateName}</button><p className="mt-1 font-normal">{i.overallScore??"不可评"} · {STATUS[i.status]??i.status}</p></th>)}</tr></thead><tbody>{dimensions.map(d=><tr key={d.requirementId}><th className="min-w-40 p-3 text-left font-normal">{d.title} · 权重{d.weight}</th>{visible.map(i=>{const value=i.dimensions.find(v=>v.requirementId===d.requirementId);return <td key={i.id} className="p-1"><button type="button" disabled={busy} title={value ? value.title + " · 权重" + value.weight : "本报告没有这条要求"} className={`w-full rounded-lg border p-3 ${cellClass(value?.verdict??"unsupported",value?.score??null)}`} onClick={()=>void open(i.id)}>{value?.score??"—"}<span className="mt-1 block">{VERDICT[value?.verdict??"unsupported"]??value?.verdict}</span>{value?.evidenceLevel!=null&&<span className="mt-1 block">实践证据 {value.evidenceLevel}/5</span>}</button></td>;})}</tr>)}</tbody></table></div>{!visible.length&&<p role="status">没有匹配候选人，试试其他关键词。</p>}</section>}
    {selected?.report&&<section className="panel space-y-4"><h2 className="text-xl font-semibold">{selected.candidateName} · 投递时固定报告</h2><p className="text-sm leading-6">{selected.report.summary}</p><p className="text-xs text-slate-500">报告模式：{selected.report.aiFallbackUsed?"规则降级":selected.report.analysisMode}；查看与下载不等于通过面试。</p><button type="button" className="btn" disabled={busy} onClick={()=>void download()}>下载本次授权简历</button>
      <SkillRadar dimensions={selected.dimensions}/>
      <ApplicationVerification key={`${selected.id}:${selected.report.id}`} applicationId={selected.id} report={selected.report} onUnavailable={verificationUnavailable} onUseQuestion={selected.status!=="replied"&&!busy ? useVerificationQuestion : undefined}/>
      <ul className="space-y-3">{selected.report.items.map(item=><li key={item.requirementId} className="rounded-lg border border-slate-200 p-3 text-sm"><strong>{item.requirementTitle||item.skill}</strong><p>{VERDICT[item.verdict]??item.verdict} · {item.finalScore??"不可评"} / 100</p><p>实践证据：{item.evidenceLevel!=null ? item.evidenceLevel+"/5" : "待评估"} · {item.evidenceLevelSource==="ai_preliminary" ? "AI 初评，待独立核验" : "规则或复核结果"}</p><p>{item.evidenceLevelReason}</p><p className="mt-2">{item.aiExplanation||item.explanation}</p>{item.aiInformationGap&&<p className="mt-2 text-amber-800">待核验：{item.aiInformationGap}</p>}<details className="mt-2"><summary className="cursor-pointer text-indigo-700">查看本次授权引用片段</summary>{item.evidenceList.map((e,index)=><div key={index} className="mt-2 text-xs"><p className="break-all">{e.citationId??"引用"} · {e.filePath} · 第{e.lineStart}—{e.lineEnd}行</p><pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{e.snippet}</pre></div>)}</details></li>)}</ul>
      {selected.status!=="replied"&&<div className="space-y-3 border-t pt-4">
        <h3 className="font-semibold">发送站内回复</h3>
        <p className="text-xs text-slate-500">此回复将直接显示给学生；不会发送邮件，不由 AI 自动做决定。发送后本期不可覆盖。</p>
        {replyDraftNotice&&<p role="status" className="text-sm text-indigo-800">{replyDraftNotice}</p>}
        <label className="block text-sm">回应类型<select className="field mt-1" disabled={busy} value={replyKind} onChange={e=>{setReplyKind(e.target.value);setConfirmReply(false);}}><option value="continue">继续沟通</option><option value="interview">面试邀请</option><option value="declined">暂不推进</option></select></label>
        <label className="block text-sm">回复正文<textarea className="field mt-1" maxLength={2000} disabled={busy} value={replyText} onChange={e=>{setReplyText(e.target.value);setConfirmReply(false);}}/></label>
        {replyReferences.length>0&&<div className="rounded-lg bg-slate-50 p-3 text-xs leading-6"><p>将随回复保存的原报告定位（企业人工确认后才发送）：</p><ul className="mt-1 space-y-1">{replyReferences.map(reference=><li key={reference.requirementId} className="flex flex-wrap items-center gap-2"><span>{`第${selected.report!.items.findIndex(item=>item.requirementId===reference.requirementId)+1}项：`}{selected.report!.items.find(item=>item.requirementId===reference.requirementId)?.requirementTitle || "岗位要求"} · {reference.citationIds.length ? reference.citationIds.join("、") : "暂无支持引用"}</span><button type="button" className="text-indigo-700 underline" onClick={()=>{setReplyQuestions(previous=>previous.filter(question=>question.requirementId!==reference.requirementId));setConfirmReply(false);}}>移除定位</button></li>)}</ul><p className="text-slate-500">删除正文中的要求名称或引用编号后，对应定位会自动移除。</p></div>}
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmReply} disabled={busy} onChange={e=>setConfirmReply(e.target.checked)}/>我已核对正文，确认发送给这位投递学生</label>
        <button type="button" className="btn" disabled={busy||!confirmReply||!replyText.trim()} onClick={async()=>{const text=replyText,references=replyReferences;const sent=await session.reply(replyKind,text,references);if(sent)resetReply();}}>确认发送站内回复</button>
      </div>}
      {selected.replyText&&<blockquote className="rounded-lg bg-indigo-50 p-3 text-sm whitespace-pre-wrap">已发送回复：{selected.replyText}</blockquote>}
    </section>}
  </div>;
}
