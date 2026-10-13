"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api/client";
import { applicationAnchorId, clearApplicationAnchor, includeApplicationTarget } from "@/lib/notification-session";
import { createApplicationAnchorRevealer } from "@/lib/application-anchor";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";
// 雷达图只在打开对照详情时渲染，按需加载，减小首屏包体。
const SkillRadar = dynamic(() => import("./SkillRadar"), {
  ssr: false,
  loading: () => <div className="h-56 w-56 animate-pulse rounded-full bg-slate-100" role="status" aria-label="正在加载雷达图" />,
});
import { filterApplications, mixedComparisonBasis } from "@/lib/application-comparison";
import { RULE_SCORE_CAP_NOTE, evidenceLevelName } from "@/lib/evidence-display";
import { createApplicationBoardSession, initialApplicationBoardState } from "@/lib/application-board-session";
import { createRefreshGate } from "@/lib/refresh-gate";
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
  const [anchorNotice,setAnchorNotice]=useState("");
  const {items,selected,error,notice,loading:busy}=state;
  const session=useMemo(()=>createApplicationBoardSession({
    list:async()=>{const id=applicationAnchorId();return includeApplicationTarget(await api.jobApplications(jobId), api.applicationDetail, id, jobId, ()=>{if(id)clearApplicationAnchor(id);setAnchorNotice("通知对应的投递已不可访问；下方仍显示当前岗位的其他已授权投递。");});}, open:api.openApplication,
    download:api.downloadApplicationResume, reply:api.replyApplication, errorMessage,
  },setState),[jobId]);
  // B-15：只对新出现的显式锚点导航（进入页面或 hashchange）滚动一次；目标被筛选条件排除时给出可执行提示，不静默失败。
  // 提示存为 string（""=无提示）：filtered-out 期间每次渲染都会重放同一 outcome，依赖 Object.is 去重，避免对象身份引发循环渲染。
  const [anchorFilterTarget,setAnchorFilterTarget]=useState("");
  const anchor=useMemo(()=>createApplicationAnchorRevealer({parseAnchorId:applicationAnchorId}),[]);
  const applyAnchor=useCallback((itemIds:string[],visibleIds:string[])=>{
    const outcome=anchor.attempt(itemIds,visibleIds);
    setAnchorFilterTarget(outcome==="filtered-out"?applicationAnchorId()??"":"");
    return outcome;
  },[anchor]);
  const [query,setQuery]=useState(""),[focus,setFocus]=useState("");
  const [radarRequirement,setRadarRequirement]=useState("");
  const [verdict,setVerdict]=useState("");
  const [replyKind,setReplyKind]=useState("continue"),[replyText,setReplyText]=useState(""),[confirmReply,setConfirmReply]=useState(false);
  // 未确认草稿状态：发送失败时置位，只由 resetReply（刷新/离窗/换投递）清除；与正文是否为空无关，
  // 删空后仍可编辑重输。清理代际 replyDraftGeneration 由各清理路径递增：发送前捕获本次代际，
  // await 返回后仅当代际一致才更新草稿状态，迟到的旧回调不得把清理后产生的新草稿标为未确认。
  const [unconfirmedReply,setUnconfirmedReply]=useState(false);
  const replyDraftGeneration=useRef(0);
  const [replyDraftNotice,setReplyDraftNotice]=useState("");
  const [replyQuestions,setReplyQuestions]=useState<VerificationReplyQuestion[]>([]);
  const replyReferences=activeVerificationReplyReferences(replyText,replyQuestions);
  const verificationUnavailable=useCallback(()=>{replyDraftGeneration.current+=1;setReplyText("");setReplyQuestions([]);setConfirmReply(false);setReplyDraftNotice("");setUnconfirmedReply(false);void session.refresh();},[session]);
  function resetReply(){replyDraftGeneration.current+=1;setReplyText("");setReplyQuestions([]);setConfirmReply(false);setReplyDraftNotice("");setUnconfirmedReply(false);}
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
    // B-06：返回页面时 visibilitychange、focus、pageshow 紧邻触发，合并为一次刷新。
    const gate=createRefreshGate(refresh);
    const visibility=()=>{
      resetReply();
      if(document.visibilityState==="hidden"){session.clear();gate.reset();}else gate.trigger();
    };
    const focusWindow=()=>{if(document.visibilityState==="visible"){resetReply();gate.trigger();}};
    // 离开窗口后即使 3 秒内返回，也必须重新核对投递授权。
    const blurWindow=()=>gate.reset();
    gate.trigger();
    document.addEventListener("visibilitychange",visibility);
    window.addEventListener("focus",focusWindow);
    window.addEventListener("blur",blurWindow);
    window.addEventListener("pageshow",gate.trigger);
    // B-15：hashchange 是新的显式锚点导航（同页锚点链接或前进/后退），不走合并闸门；重新核对授权后由列表 effect 定位一次。
    window.addEventListener("hashchange",refresh);
    return ()=>{session.dispose();document.removeEventListener("visibilitychange",visibility);window.removeEventListener("focus",focusWindow);window.removeEventListener("blur",blurWindow);window.removeEventListener("pageshow",gate.trigger);window.removeEventListener("hashchange",refresh);};
  },[session]);
  const dimensions=Array.from(new Map(items.flatMap(i=>i.dimensions).map(d=>[d.requirementId,d])).values());
  const mixedBasis=mixedComparisonBasis(items);
  const visible=filterApplications(items,query,focus,verdict);
  // B-15：列表或筛选结果每次变化后尝试一次定位。新导航 revealed；目标在 items 但被筛掉时转为提示；
  // 已消费的导航在同 hash 下反复调用只会得到 idle/waiting，因此自动刷新、撤回不会劫持视口。
  useEffect(()=>{applyAnchor(items.map(i=>i.id),visible.map(i=>i.id));},[applyAnchor,items,visible]);
  async function open(id:string,requirementId=""){resetReply();setRadarRequirement(requirementId);await session.open(id);}
  async function download(){await session.download(file=>{const url=URL.createObjectURL(file.blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=file.filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
  return <div className="space-y-5"><h1 className="text-3xl font-bold">已授权投递 · 岗位匹配对照</h1><p className="text-sm leading-6 text-slate-600">查看学生向本岗位授权的固定报告，点选格子即可联动要求与证据。分数仅辅助核对，不代表录用顺序。</p>
    <button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>{resetReply();void session.refresh();}}>刷新授权投递</button>
    <details className="text-xs leading-5 text-slate-500"><summary className="cursor-pointer py-2 text-indigo-700">查看授权范围与使用说明</summary><p className="mt-2">仅显示向本岗位明确投递的报告，未投递或已撤回的学生不可见。默认展示最近100份，更早的通知目标会单独核对授权后补入。刷新或重新回到此页面会核对授权并收起已打开报告；离开窗口会清空未发送的回复，请发送前再次核对。学生撤回不会追回已下载副本。</p></details>
    {busy&&<p role="status" className="panel">正在核对授权投递，请稍候…</p>}
    {notice&&<p role="status" className="panel text-amber-800">{notice}</p>}
    {anchorNotice&&<p role="status" className="panel text-amber-800">{anchorNotice}</p>}
    {anchorFilterTarget&&<div role="status" className="panel space-y-2 text-amber-800"><p>通知指向的投递在当前筛选结果之外，未自动滚动。可以清除筛选后定位，或直接打开该投递报告。</p><div className="flex flex-wrap gap-x-4 gap-y-1"><button type="button" className="text-indigo-700 underline" onClick={()=>{setQuery("");setFocus("");setVerdict("");}}>清除筛选并定位</button><button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>{setAnchorFilterTarget("");anchor.dismiss();void open(anchorFilterTarget);}}>直接打开该投递报告</button><button type="button" className="text-sm underline" onClick={()=>{anchor.dismiss();setAnchorFilterTarget("");}}>关闭</button></div></div>}
    {error&&<p role="alert" className="panel text-rose-700">{error} 请刷新授权投递重试，旧报告已清除。</p>}
    {unconfirmedReply&&<UnconfirmedReplyDraft text={replyText} onEdit={text=>applyReplyDraftEdit(text,setReplyText,setConfirmReply)}/>}
    <div className="panel grid gap-3 sm:grid-cols-3"><label className="text-sm">关键词（姓名、技能或要求）<input type="search" className="field mt-2" value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="text-sm">聚焦岗位要求<select className="field mt-2" value={focus} onChange={e=>setFocus(e.target.value)}><option value="">全部要求</option>{dimensions.map(d=><option key={d.requirementId} value={d.requirementId}>{d.skill||d.title}</option>)}</select></label><label className="text-sm">证据状态筛选<select className="field mt-2" value={verdict} onChange={e=>setVerdict(e.target.value)}><option value="">全部状态</option><option value="supported">有证据或部分支持</option><option value="claimed_only">仅简历自述</option><option value="gap">缺少材料</option><option value="unsupported">暂不可评</option></select></label></div>
    {mixedBasis&&<p role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">投递报告的岗位要求、权重或规则版本不同，当前按投递时间排列，不按分数排名。请打开每份报告核对其原始要求；表格行名仅作定位，格子中的说明来自各自快照。</p>}
    {!items.length&&!busy&&!error&&<p className="panel">暂无已授权投递，请由学生从该岗位的完整报告中确认投递。平台不会从学生库导出未经授权的简历。<Link className="mt-3 block text-indigo-700 underline" href="/demo/heatmap">先查看合成热力图交互示例 →</Link></p>}
    {!!items.length&&<section className="panel space-y-3"><h2 className="font-semibold">岗位要求 × 投递候选人</h2><p className="text-xs text-slate-500">绿色/蓝色：有证据的分数；虚线：缺材料或仅自述；灰色：不可评。数值为原报告分数，{RULE_SCORE_CAP_NOTE}权重沿用原报告。点击姓名或格子查看固定报告。</p><div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr><th className="p-3 text-left">岗位要求</th>{visible.map(i=><th id={`application-${i.id}`} key={i.id} className="min-w-36 p-2"><button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>void open(i.id)}>{i.candidateName}</button><p className="mt-1 font-normal">{i.overallScore??"不可评"} · {STATUS[i.status]??i.status}</p></th>)}</tr></thead><tbody>{dimensions.map(d=><tr key={d.requirementId}><th className="min-w-40 p-3 text-left font-normal">{d.title} · 权重{d.weight}</th>{visible.map(i=>{const value=i.dimensions.find(v=>v.requirementId===d.requirementId);return <td key={i.id} className="p-1"><button type="button" disabled={busy} title={value ? value.title + " · 权重" + value.weight : "本报告没有这条要求"} className={`w-full rounded-lg border p-3 ${cellClass(value?.verdict??"unsupported",value?.score??null)}`} onClick={()=>void open(i.id,d.requirementId)}>{value?.score??"—"}<span className="mt-1 block">{VERDICT[value?.verdict??"unsupported"]??value?.verdict}</span>{value?.evidenceLevel!=null&&<span className="mt-1 block">实践证据 {evidenceLevelName(value.evidenceLevel)}</span>}</button></td>;})}</tr>)}</tbody></table></div>{!visible.length&&<p role="status">没有匹配候选人，试试其他关键词。</p>}</section>}
    {selected?.report&&<section className="panel space-y-4"><h2 className="text-xl font-semibold">{selected.candidateName} · 投递时固定报告</h2><p className="text-sm leading-6">{selected.report.summary}</p><p className="text-xs text-slate-500">报告模式：{selected.report.aiFallbackUsed?"规则降级":selected.report.analysisMode}；查看与下载不等于通过面试。</p><button type="button" className="btn" disabled={busy} onClick={()=>void download()}>下载本次授权简历</button>
      <SkillRadar key={`${selected.id}:${selected.report.id}:${radarRequirement}`} dimensions={selected.dimensions} items={selected.report.items} initialRequirementId={radarRequirement}/>
      <details className="rounded-xl border border-slate-200 p-4"><summary className="cursor-pointer text-sm font-medium text-indigo-700">AI核验建议与沟通问题（按需查看）</summary><div className="mt-4"><ApplicationVerification key={`${selected.id}:${selected.report.id}`} applicationId={selected.id} report={selected.report} onUnavailable={verificationUnavailable} onUseQuestion={selected.status!=="replied"&&!busy ? useVerificationQuestion : undefined}/></div></details>
      <details className="rounded-xl border border-slate-200 p-4"><summary className="cursor-pointer text-sm font-medium text-indigo-700">查看完整逐项报告（{selected.report.items.length}项）</summary><p className="mt-2 text-xs text-slate-500">数值为材料支持度。{RULE_SCORE_CAP_NOTE}历史投递按原报告数值显示，不限制到 65。</p><ul className="mt-4 space-y-3">{selected.report.items.map(item=><li key={item.requirementId} className="rounded-lg border border-slate-200 p-3 text-sm"><strong>{item.requirementTitle||item.skill}</strong><p>{VERDICT[item.verdict]??item.verdict} · 材料支持度 {item.finalScore??"不可评"}</p><p>实践证据：{item.evidenceLevelLabel ?? (item.evidenceLevel!=null ? evidenceLevelName(item.evidenceLevel) : "待评估")} · {item.evidenceLevelSource==="ai_preliminary" ? "AI 初评，待独立核验" : "规则或复核结果"}</p><p>{item.evidenceLevelReason}</p><p className="mt-2">{item.aiExplanation||item.explanation}</p>{item.aiInformationGap&&<p className="mt-2 text-amber-800">待核验：{item.aiInformationGap}</p>}<details className="mt-2"><summary className="cursor-pointer text-indigo-700">查看本次授权引用片段</summary>{item.evidenceList.map((e,index)=><div key={index} className="mt-2 text-xs"><p className="break-all">{e.citationId??"引用"} · {e.filePath} · 第{e.lineStart}—{e.lineEnd}行</p><pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{e.snippet}</pre></div>)}</details></li>)}</ul></details>
      {selected.status!=="replied"&&<div className="space-y-3 border-t pt-4">
        <h3 className="font-semibold">发送站内回复</h3>
        <p className="text-xs text-slate-500">此回复将直接显示给学生；不会发送邮件，不由 AI 自动做决定。发送后本期不可覆盖。</p>
        {replyDraftNotice&&<p role="status" className="text-sm text-indigo-800">{replyDraftNotice}</p>}
        <label className="block text-sm">回应类型<select className="field mt-1" disabled={busy} value={replyKind} onChange={e=>{setReplyKind(e.target.value);setConfirmReply(false);}}><option value="continue">继续沟通</option><option value="interview">面试邀请</option><option value="declined">暂不推进</option></select></label>
        <label className="block text-sm">回复正文<textarea className="field mt-1" maxLength={2000} disabled={busy} value={replyText} onChange={e=>applyReplyDraftEdit(e.target.value,setReplyText,setConfirmReply)}/></label>
        {replyReferences.length>0&&<div className="rounded-lg bg-slate-50 p-3 text-xs leading-6"><p>将随回复保存的原报告定位（企业人工确认后才发送）：</p><ul className="mt-1 space-y-1">{replyReferences.map(reference=><li key={reference.requirementId} className="flex flex-wrap items-center gap-2"><span>{`第${selected.report!.items.findIndex(item=>item.requirementId===reference.requirementId)+1}项：`}{selected.report!.items.find(item=>item.requirementId===reference.requirementId)?.requirementTitle || "岗位要求"} · {reference.citationIds.length ? reference.citationIds.join("、") : "暂无支持引用"}</span><button type="button" className="text-indigo-700 underline" onClick={()=>{setReplyQuestions(previous=>previous.filter(question=>question.requirementId!==reference.requirementId));setConfirmReply(false);}}>移除定位</button></li>)}</ul><p className="text-slate-500">删除正文中的要求名称或引用编号后，对应定位会自动移除。</p></div>}
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmReply} disabled={busy} onChange={e=>setConfirmReply(e.target.checked)}/>我已核对正文，确认发送给这位投递学生</label>
        <button type="button" className="btn" disabled={busy||!confirmReply||!replyText.trim()} onClick={async()=>{const text=replyText,references=replyReferences;const generation=replyDraftGeneration.current;const sent=await session.reply(replyKind,text,references);const outcome=replySendOutcome(sent,replyDraftGeneration.current===generation);if(outcome==="reset")resetReply();else if(outcome==="mark-unconfirmed")setUnconfirmedReply(true);}}>确认发送站内回复</button>
      </div>}
      {selected.replyText&&<blockquote className="rounded-lg bg-indigo-50 p-3 text-sm whitespace-pre-wrap">已发送回复：{selected.replyText}</blockquote>}
    </section>}
  </div>;
}

// 回复失败（请求失败或响应丢失）后的唯一编辑规则：正文可继续修改，任何编辑都撤销人工发送确认，
// 使已勾选的确认不会被带进下一次核对。正常编辑与失败草稿共用，避免两处行为漂移。
export function applyReplyDraftEdit(text:string,edit:(text:string)=>void,confirm:(on:boolean)=>void){
  edit(text);confirm(false);
}
// 发送完成后的失败草稿归属规则：清理代际在发送期间未变，成功才重置、失败才标记未确认；
// 迟到的旧回调（等待期间发生过清理，新草稿可能已产生）一律忽略，不得改变新状态。
export type ReplySendOutcome="reset"|"mark-unconfirmed"|"ignore";
export function replySendOutcome(sent:boolean,generationUnchanged:boolean):ReplySendOutcome{
  if(!generationUnchanged)return "ignore";
  return sent?"reset":"mark-unconfirmed";
}
// 会话失败清空列表与旧报告后，草稿只保留在本页组件状态：可编辑、可复制、仍限2000字；
// 面板由未确认草稿状态（发送失败置位、resetReply 生命周期清除）控制，与正文是否为空无关，
// 删空后仍可重新输入；不提供发送入口，不显示已送达，也不自动重发——重新发送必须先刷新并重新核对授权。
export function UnconfirmedReplyDraft({text,onEdit}:{text:string;onEdit:(nextText:string)=>void}){
  return <div className="panel space-y-2 text-sm"><p>回复是否送达尚未确认，平台不会自动重发。以下保留了本页草稿，可继续编辑或复制，长度仍限2000字；请先刷新授权投递并核对该投递的回复状态，再决定是否发送。</p><textarea className="field" maxLength={2000} value={text} onChange={e=>onEdit(e.target.value)} aria-label="未确认发送的回复草稿"/></div>;
}
