"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import SourceIdentity, { SourceIdentityDetails } from "./SourceIdentity";
import ListPagination from "./ListPagination";
import { api, errorMessage } from "@/lib/api/client";
import type { ApplicationView } from "@/lib/api/client";
import type { MatchReport, ReportItem } from "@/lib/api/domain";
import { applicationAnchorId, clearApplicationAnchor, includeApplicationTarget } from "@/lib/notification-session";
import { createApplicationAnchorRevealer } from "@/lib/application-anchor";
import AccessGate from "./AccessGate";
import { useAuth } from "./AuthProvider";
// 雷达图只在打开对照详情时渲染，按需加载，减小首屏包体。
const SkillRadar = dynamic(() => import("./SkillRadar"), {
  ssr: false,
  loading: () => <div className="h-56 w-56 animate-pulse rounded-full bg-slate-100" role="status" aria-label="正在加载雷达图" />,
});
import { applicationFilterView, mixedComparisonBasis } from "@/lib/application-comparison";
import { RULE_SCORE_CAP_NOTE, evidenceLevelName } from "@/lib/evidence-display";
import { reportModeLabel, reportSummaryText } from "@/lib/report-display";
import { heatmapCellClass as cellClass } from "@/lib/heatmap-cell.js";
import { createApplicationBoardSession, initialApplicationBoardState } from "@/lib/application-board-session";
import { createRefreshGate } from "@/lib/refresh-gate";
import ApplicationVerification from "./ApplicationVerification";
import { activeVerificationReplyReferences, appendVerificationReplyQuestion, type VerificationReplyQuestion } from "@/lib/verification-reply-draft";

import { VERDICT_LABELS as VERDICT, APPLICATION_STATUS_LABELS as STATUS } from "@/lib/verdict-display.js";

export default function ApplicationBoard({jobId}:{jobId:string}){
  const {user}=useAuth();
  return <AccessGate roles={["enterprise"]}><Workspace key={`${user?.id}:${jobId}`} jobId={jobId}/></AccessGate>;
}
function Workspace({jobId}:{jobId:string}){
  const workspace=useRef<HTMLDivElement>(null);
  const [heldHeight,setHeldHeight]=useState<number|undefined>(undefined);
  const page=useRef(1);
  const filters=useRef({q:"",status:"",requirementId:"",verdict:""});
  const [state,setState]=useState(initialApplicationBoardState);
  const [anchorNotice,setAnchorNotice]=useState("");
  const {items,selected,error,notice,loading:busy}=state;
  const session=useMemo(()=>createApplicationBoardSession({
    list:async()=>{const id=applicationAnchorId();const result=await api.jobApplications(jobId,page.current,20,filters.current);const items=await includeApplicationTarget(result.items, api.applicationDetail, id, jobId, ()=>{if(id)clearApplicationAnchor(id);setAnchorNotice("通知对应的投递已不可访问；下方仍显示当前岗位的其他已授权投递。");});return {...result,items,pageItemCount:result.items.length};}, open:api.openApplication,
    detail:async id=>{const item=await api.applicationDetail(id);if(item.jobId!==jobId)throw new Error("投递不属于当前岗位");return item;},
    download:api.downloadApplicationResume, reply:api.replyApplication, errorMessage,
  },value=>{if(value.pagination)page.current=value.pagination.page;setState(value);}),[jobId]);
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
  const [focusLabel,setFocusLabel]=useState("");
  const [status,setStatus]=useState("");
  const [compareIds,setCompareIds]=useState<string[]>([]);
  const [compareMode,setCompareMode]=useState(false);
  const comparisonBookmark=useRef<string[]>([]);
  comparisonBookmark.current=compareIds;
  const [radarRequirement,setRadarRequirement]=useState("");
  const [radarSelectionId,setRadarSelectionId]=useState("");
  const [radarEvidenceExpanded,setRadarEvidenceExpanded]=useState(false);
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
    let alive=true;
    let releaseFrame:number|undefined;
    let pendingResume:ReturnType<typeof session.resume>|undefined;
    const holdLayout=()=>{
      const height=workspace.current?.getBoundingClientRect().height;
      if(height)setHeldHeight(previous=>previous??height);
    };
    const refresh=()=>{resetReply();setHeldHeight(undefined);setCompareIds([]);setCompareMode(false);void session.refresh();};
    const resume=()=>{
      if(document.visibilityState!=="visible")return;
      holdLayout();resetReply();
      const pending=session.resume(comparisonBookmark.current);
      if(pendingResume===pending)return;
      pendingResume=pending;
      void pending.then(result=>{
        if(!alive||!result||document.visibilityState!=="visible")return;
        const remaining=comparisonBookmark.current.filter(id=>result.authorizedIds.includes(id));
        setCompareIds(previous=>previous.length===remaining.length&&previous.every((id,i)=>id===remaining[i])?previous:remaining);
        setCompareMode(previous=>previous&&remaining.length>=2);
        if(!result.selectedId){setRadarRequirement("");setRadarSelectionId("");setRadarEvidenceExpanded(false);}
        // Keep the old page height until authorized content has rendered. No
        // scroll command or anchor navigation runs during an ordinary return.
        releaseFrame=requestAnimationFrame(()=>{if(alive&&document.visibilityState==="visible")setHeldHeight(undefined);});
      }).finally(()=>{if(pendingResume===pending)pendingResume=undefined;});
    };
    // B-06：返回页面时 visibilitychange、focus、pageshow 紧邻触发，合并为一次刷新。
    const gate=createRefreshGate(resume);
    const visibility=()=>{
      resetReply();
      if(document.visibilityState==="hidden"){
        holdLayout();
        if(releaseFrame!==undefined)cancelAnimationFrame(releaseFrame);
        session.suspend();gate.reset();
      }else gate.trigger();
    };
    const focusWindow=()=>{if(document.visibilityState==="visible"){resetReply();gate.trigger();}};
    // 离开窗口后即使 3 秒内返回，也必须重新核对投递授权。
    const blurWindow=()=>{resetReply();gate.reset();};
    gate.trigger();
    document.addEventListener("visibilitychange",visibility);
    window.addEventListener("focus",focusWindow);
    window.addEventListener("blur",blurWindow);
    window.addEventListener("pageshow",gate.trigger);
    // B-15：hashchange 是新的显式锚点导航（同页锚点链接或前进/后退），不走合并闸门；重新核对授权后由列表 effect 定位一次。
    window.addEventListener("hashchange",refresh);
    return ()=>{alive=false;if(releaseFrame!==undefined)cancelAnimationFrame(releaseFrame);session.dispose();document.removeEventListener("visibilitychange",visibility);window.removeEventListener("focus",focusWindow);window.removeEventListener("blur",blurWindow);window.removeEventListener("pageshow",gate.trigger);window.removeEventListener("hashchange",refresh);};
  },[session]);
  const dimensions=Array.from(new Map(items.flatMap(i=>i.dimensions).map(d=>[d.requirementId,d])).values());
  // Predicates are applied before server counting/pagination; local sorting must
  // not drop matches found in the fixed report's text outside visible labels.
  const filterView=applicationFilterView(items,"","","",selected?.id);
  const visible=filterView.visible;
  const matrixItems=compareMode ? visible.filter(item=>compareIds.includes(item.id)) : visible;
  const mixedBasis=mixedComparisonBasis(matrixItems);
  const selectedOutside=filterView.selectedOutside;
  function applyFilters(next={q:query.trim(),status,requirementId:focus,verdict}){filters.current=next;page.current=1;setCompareIds([]);setCompareMode(false);void session.filter();}
  function clearFilters(){setQuery("");setFocus("");setFocusLabel("");setVerdict("");setStatus("");applyFilters({q:"",status:"",requirementId:"",verdict:""});}
  // B-15：列表或筛选结果每次变化后尝试一次定位。新导航 revealed；目标在 items 但被筛掉时转为提示；
  // 已消费的导航在同 hash 下反复调用只会得到 idle/waiting，因此自动刷新、撤回不会劫持视口。
  useEffect(()=>{applyAnchor(items.map(i=>i.id),visible.map(i=>i.id));},[applyAnchor,items,visible]);
  async function open(id:string,requirementId=""){resetReply();setRadarRequirement(requirementId);setRadarSelectionId(requirementId);setRadarEvidenceExpanded(false);await session.open(id);}
  async function download(){await session.download(file=>{const url=URL.createObjectURL(file.blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=file.filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
  return <div ref={workspace} style={heldHeight?{minHeight:heldHeight}:undefined} className="space-y-5"><h1 className="text-3xl font-bold">已授权投递 · 岗位匹配对照</h1><p className="text-sm leading-6 text-slate-600">查看学生向本岗位授权的固定报告，点选格子即可联动要求与证据。分数仅辅助核对，不代表录用顺序。</p>
    <button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>{resetReply();void session.refresh();}}>刷新授权投递</button>
    <details className="text-xs leading-5 text-slate-500"><summary className="cursor-pointer py-2 text-indigo-700">查看授权范围与使用说明</summary><p className="mt-2">仅显示向本岗位明确投递的报告，未投递或已撤回的学生不可见。每页20份，可翻页查看更早投递；筛选作用于本岗位全部已授权投递，并在计数和分页前执行。通知目标会单独核对授权后补入。主动刷新或翻页会收起报告；切回页面时先核对授权，再恢复本次会话的选中状态；离开窗口会清空未发送的回复，请发送前再次核对。学生撤回不会追回已下载副本。</p></details>
    {state.pagination&&<><ListPagination label="候选人分页" value={state.pagination} busy={busy} onPage={value=>{page.current=value;resetReply();setCompareIds([]);setCompareMode(false);void session.refresh();}}/>{items.length>state.pagination.pageItemCount&&<p className="text-xs text-slate-600">另外展示了当前页之外的已授权候选人，不计入本页记录数。</p>}</>}
    {busy&&<p role="status" className="panel">正在核对授权投递，请稍候…</p>}
    {notice&&<p role="status" className="panel text-amber-800">{notice}</p>}
    {anchorNotice&&<p role="status" className="panel text-amber-800">{anchorNotice}</p>}
    {anchorFilterTarget&&<div role="status" className="panel space-y-2 text-amber-800"><p>通知指向的投递在当前筛选结果之外，未自动滚动。可以清除筛选后定位，或直接打开该投递报告。</p><div className="flex flex-wrap gap-x-4 gap-y-1"><button type="button" className="text-indigo-700 underline" onClick={clearFilters}>清除筛选并定位</button><button type="button" className="text-indigo-700 underline" disabled={busy} onClick={()=>{setAnchorFilterTarget("");anchor.dismiss();void open(anchorFilterTarget);}}>直接打开该投递报告</button><button type="button" className="text-sm underline" onClick={()=>{anchor.dismiss();setAnchorFilterTarget("");}}>关闭</button></div></div>}
    {error&&<p role="alert" className="panel text-rose-700">{error} 请刷新授权投递重试，旧报告已清除。</p>}
    {unconfirmedReply&&<UnconfirmedReplyDraft text={replyText} onEdit={text=>applyReplyDraftEdit(text,setReplyText,setConfirmReply)}/>}
    <form className="panel grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={event=>{event.preventDefault();applyFilters();}}><label className="text-sm">姓名或报告摘要、要求、说明<input type="search" className="field mt-2" maxLength={200} value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="text-sm">投递状态<select className="field mt-2" value={status} onChange={e=>setStatus(e.target.value)}><option value="">全部状态</option><option value="submitted">尚未查看</option><option value="viewed">已查看，未回复</option><option value="downloaded">已下载，未回复</option><option value="replied">已回复</option></select></label><RequirementFocusSelect dimensions={dimensions} value={focus} selectedLabel={focusLabel} onChange={(id,label)=>{setFocus(id);setFocusLabel(label);}}/><label className="text-sm">证据状态筛选<select className="field mt-2" value={verdict} onChange={e=>setVerdict(e.target.value)}><option value="">全部证据状态</option><option value="supported">有证据或部分支持</option><option value="claimed_only">仅简历自述</option><option value="gap">缺少材料</option><option value="unsupported">暂不可评</option></select></label><div className="flex flex-wrap gap-3 sm:col-span-2 lg:col-span-4"><button className="btn" disabled={busy}>筛选全部授权投递</button><button className="btn-secondary" type="button" disabled={busy} onClick={clearFilters}>清除筛选</button><p className="self-center text-xs text-slate-600">关键词、状态与同一条要求的证据条件共同筛选；总数包含所有页。</p></div></form>
    {mixedBasis&&<p role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">投递报告的岗位要求、权重或规则版本不同，当前按投递时间排列，不按分数排名。请打开每份报告核对其原始要求；表格行名仅作定位，格子中的说明来自各自快照。</p>}
    {!items.length&&!busy&&!error&&<p className="panel">当前范围没有已授权投递，可以清除筛选或由学生从该岗位的完整报告中确认投递。平台不会从学生库导出未经授权的简历。<Link className="mt-3 block text-indigo-700 underline" href="/demo/heatmap">先查看合成热力图交互示例 →</Link></p>}
    {!!items.length&&filterView.empty&&<CandidateFilterNotice empty selectedName={selectedOutside?selected?.candidateName:undefined} onClear={clearFilters}/>}
    {!!visible.length&&<section className="panel space-y-3"><h2 className="font-semibold">岗位要求 × 投递候选人</h2><p className="text-xs leading-5 text-slate-600">可勾选本页2–4位候选人并排核对；对照仅使用各自已授权的固定报告。状态色不代表录用顺序。{RULE_SCORE_CAP_NOTE}</p><div className="flex flex-wrap items-center gap-3"><button type="button" className="btn-secondary" disabled={compareIds.length<2||compareIds.length>4} aria-pressed={compareMode} onClick={()=>setCompareMode(!compareMode)}>{compareMode?"返回本页全部候选人":`并排核对 ${compareIds.length} 位`}</button><span className="text-xs text-slate-600">已选 {compareIds.length}/4 位</span>{!!compareIds.length&&<button type="button" className="text-sm text-indigo-700 underline" onClick={()=>{setCompareIds([]);setCompareMode(false);}}>清除对照选择</button>}</div>{matrixItems.length>1&&<p className="text-xs text-indigo-700 sm:hidden">表格可左右滑动查看各位候选人。</p>}<div className="max-h-[60vh] overflow-auto rounded-lg border border-slate-200" role="region" aria-label="可滚动的授权候选人对照表" tabIndex={0}><table className="w-full border-separate border-spacing-0 text-xs"><thead className="sticky top-0 z-20 bg-white"><tr><th className="sticky left-0 z-30 min-w-40 bg-white p-3 text-left">岗位要求</th>{matrixItems.map(i=><th id={`application-${i.id}`} key={i.id} className={`min-w-36 p-2 ${selected?.id===i.id ? "bg-indigo-50" : "bg-white"}`}><button type="button" className="candidate-select" aria-pressed={selected?.id===i.id} disabled={busy} onClick={()=>void open(i.id)}>{i.candidateName}{selected?.id===i.id&&<span className="mt-1 block text-xs">当前候选人</span>}</button><p className="mt-1 font-normal">{i.overallScore??"不可评"} · {STATUS[i.status]??i.status}</p><label className="mt-2 flex items-center justify-center gap-1 font-normal"><input type="checkbox" checked={compareIds.includes(i.id)} disabled={!compareIds.includes(i.id)&&compareIds.length>=4} onChange={()=>{setCompareMode(false);setCompareIds(previous=>toggleComparisonCandidate(previous,i.id));}}/>加入对照</label></th>)}</tr></thead><tbody>{dimensions.map(d=><tr key={d.requirementId}><th className="sticky left-0 z-10 min-w-40 border-t border-slate-100 bg-white p-3 text-left font-normal">{d.title} · 权重{d.weight}</th>{matrixItems.map(i=>{const value=i.dimensions.find(v=>v.requirementId===d.requirementId);return <td key={i.id} className={`border-t border-slate-100 p-1 ${selected?.id===i.id ? "bg-indigo-50/70" : ""}`}><button type="button" disabled={busy} title={value ? value.title + " · 权重" + value.weight : "本报告没有这条要求"} className={`w-full rounded-lg border p-3 ${cellClass(value?.verdict??"unsupported",value?.score??null)}`} onClick={()=>void open(i.id,d.requirementId)}>{value?.score??"—"}<span className="mt-1 block">{VERDICT[value?.verdict??"unsupported"]??value?.verdict}</span>{value?.evidenceLevel!=null&&<span className="mt-1 block">实践证据 {evidenceLevelName(value.evidenceLevel)}</span>}</button></td>;})}</tr>)}</tbody></table></div></section>}
    {selected?.report&&radarRequirement&&<SelectedRequirementEvidence application={selected} requirementId={radarRequirement}/>}
    {selected?.report&&<section id="selected-application-report" className="panel space-y-4">{selectedOutside&&<CandidateFilterNotice empty={false} selectedName={selected.candidateName} onClear={clearFilters}/>}<h2 className="text-xl font-semibold">{selected.candidateName} · 投递时固定报告</h2><p className="text-xs leading-5 text-slate-500">岗位：{selected.report.jobTitle || selected.jobTitle} · 报告生成于 {new Date(selected.report.createdAt).toLocaleString("zh-CN")} · 后续新版不会改写本次投递</p><p className="text-sm leading-6">{reportSummaryText(selected.report.summary)}</p><p className="text-xs text-slate-500">报告模式：{reportModeLabel(selected.report)}；查看与下载不等于通过面试。</p><button type="button" className="btn-secondary" disabled={busy} onClick={()=>void download()}>下载本次授权简历</button>
      <SkillRadar key={`${selected.id}:${selected.report.id}:${radarRequirement}`} dimensions={selected.dimensions} items={selected.report.items} initialRequirementId={radarSelectionId} onRequirementChange={id=>{setRadarSelectionId(id);setRadarEvidenceExpanded(false);}} evidenceExpanded={radarEvidenceExpanded} onEvidenceExpandedChange={setRadarEvidenceExpanded} materials={selected.report.materials} aiFallbackUsed={selected.report.aiFallbackUsed}/>
      <details className="rounded-xl border border-slate-200 p-4"><summary className="cursor-pointer text-sm font-medium text-indigo-700">AI核验建议与沟通问题（按需查看）</summary><div className="mt-4"><ApplicationVerification key={`${selected.id}:${selected.report.id}`} applicationId={selected.id} report={selected.report} onUnavailable={verificationUnavailable} onUseQuestion={selected.status!=="replied"&&!busy ? useVerificationQuestion : undefined}/></div></details>
      <details className="rounded-xl border border-slate-200 p-4"><summary className="cursor-pointer text-sm font-medium text-indigo-700">查看完整逐项报告（{selected.report.items.length}项）</summary><p className="mt-2 text-xs text-slate-500">数值为材料支持度。{RULE_SCORE_CAP_NOTE}历史投递按原报告数值显示，不限制到 65。</p><ul className="mt-4 space-y-3">{selected.report.items.map(item=><SavedRequirementDetail key={item.requirementId} item={item} report={selected.report!}/>)}</ul></details>
      {selected.status!=="replied"&&<div className="space-y-3 border-t pt-4">
        <h3 className="font-semibold">发送站内回复</h3>
        <p className="rounded-lg bg-slate-50 p-3 text-sm">当前收件人：<strong>{selected.candidateName}</strong><span className="text-xs text-slate-500"> · 投递编号 {selected.id.slice(0,8)}（仅发送给该投递对应学生）</span></p>
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

type RequirementOption = { requirementId: string; title: string; skill: string };
export function RequirementFocusSelect({ dimensions, value, selectedLabel, onChange }: {
  dimensions: RequirementOption[]; value: string; selectedLabel: string;
  onChange: (id: string, label: string) => void;
}) {
  // A zero-result filter cannot discard its selected option. Its label was
  // captured from an already authorized row; no broader metadata is fetched.
  const selectedMissing = !!value && !dimensions.some(item => item.requirementId === value);
  return <label className="text-sm">聚焦岗位要求<select className="field mt-2" value={value} onChange={event => onChange(event.target.value, event.target.selectedOptions[0]?.textContent ?? "")}><option value="">全部要求</option>{selectedMissing && <option value={value}>{selectedLabel || "已选要求（当前结果未包含）"}</option>}{dimensions.map(item => <option key={item.requirementId} value={item.requirementId}>{item.skill || item.title}</option>)}</select></label>;
}

export function toggleComparisonCandidate(ids: string[], id: string): string[] {
  if (ids.includes(id)) return ids.filter(value => value !== id);
  return ids.length < 4 ? [...ids, id] : ids;
}

function SavedRequirementInterpretation({ item, report }: { item: ReportItem; report: MatchReport }) {
  // Rejected text may remain in a fixed snapshot. Both compact and complete
  // views adopt only validated, non-fallback AI interpretation.
  const useAi = item.aiStatus === "validated" && !report.aiFallbackUsed;
  const aiExplanation = useAi && item.aiExplanation?.trim() ? item.aiExplanation : null;
  const gap = (useAi ? item.aiInformationGap : null) || item.evidenceLevelGap;
  return <>
    <p className="break-words text-sm"><span className="font-medium">{aiExplanation ? "AI解释" : "规则解释"}：</span>{aiExplanation || item.explanation}</p>
    {gap && <p className="text-sm text-slate-700">待核对：{gap}</p>}
  </>;
}

export function SavedRequirementDetail({ item, report }: { item: ReportItem; report: MatchReport }) {
  return <li className="rounded-lg border border-slate-200 p-3 text-sm">
    <strong>{item.requirementTitle || item.skill}</strong>
    <p>{VERDICT[item.verdict] ?? item.verdict} · 材料支持度 {item.finalScore ?? "不可评"}</p>
    <p>实践证据：{item.evidenceLevelLabel ?? (item.evidenceLevel != null ? evidenceLevelName(item.evidenceLevel) : "待评估")} · {item.evidenceLevelSource === "ai_preliminary" ? "AI 初评，待独立核验" : "规则或复核结果"}</p>
    <p>{item.evidenceLevelReason ?? ""}</p>
    <div className="mt-2 space-y-2"><SavedRequirementInterpretation item={item} report={report}/></div>
    <details className="mt-2"><summary className="cursor-pointer text-indigo-700">查看本次授权引用片段</summary>{item.evidenceList.map((source, index) => <div key={index} className="mt-2 text-xs"><p className="break-all">{source.citationId ?? "引用"} · <SourceIdentity source={source} materials={report.materials ?? []} /> · 第{source.lineStart}—{source.lineEnd}行</p><pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{source.snippet}</pre><SourceIdentityDetails source={source} /></div>)}</details>
  </li>;
}

export function SelectedRequirementEvidence({ application, requirementId }: { application: ApplicationView; requirementId: string }) {
  const report = application.report;
  const item = report?.items.find(value => value.requirementId === requirementId);
  if (!report) return null;
  return <section className="panel space-y-3 border-indigo-200" aria-label="当前格子的固定报告依据">
    <h2 className="font-semibold">{application.candidateName} · {item?.requirementTitle || "该报告未包含这条要求"}</h2>
    {item ? <>
      <p className="text-sm">{VERDICT[item.verdict] ?? item.verdict}</p>
      <SavedRequirementInterpretation item={item} report={report}/>
      {item.evidenceList.slice(0, 2).map((source, index) => <div key={`${source.citationId}-${index}`} className="rounded-lg bg-slate-50 p-3 text-xs"><p><SourceIdentity source={source} materials={report.materials} /> · 第{source.lineStart}–{source.lineEnd}行 · {source.citationId || "规则引用"}</p><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words">{source.snippet}</pre><SourceIdentityDetails source={source} /></div>)}
      {!item.evidenceList.length && <p className="text-sm text-slate-600">该固定报告没有可展示的支持引用；不能据此推断学生没有相关能力。</p>}
    </> : <p className="text-sm text-slate-600">不同报告的要求版本可能不同；请按各自固定要求核对，不能把空格子当作能力不足。</p>}
    <a className="text-sm text-indigo-700 underline" href="#selected-application-report">查看完整固定报告与回复收件人 →</a>
  </section>;
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
// 筛选只影响候选列表，不关闭已打开报告或清空未发送草稿；用可见提示避免把旧报告误认为当前筛选结果。
export function CandidateFilterNotice({empty,selectedName,onClear}:{empty:boolean;selectedName?:string;onClear:()=>void}){
  if(!empty&&!selectedName)return null;
  const text=empty
    ? `本岗位没有符合关键词、状态、岗位要求和证据状态组合的候选人。${selectedName?` 当前打开的 ${selectedName} 不在筛选结果中；报告与未发送草稿仍保留。`:""}`
    : `当前打开的 ${selectedName} 不在本页筛选结果中。以下保留先前选中的固定报告与未发送草稿；回复仍指向 ${selectedName} 对应的投递，不会因筛选改变收件人。`;
  return <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900"><p>{text}</p><button type="button" className="mt-2 text-indigo-700 underline" onClick={onClear}>清除全部筛选</button></div>;
}
// 会话失败清空列表与旧报告后，草稿只保留在本页组件状态：可编辑、可复制、仍限2000字；
// 面板由未确认草稿状态（发送失败置位、resetReply 生命周期清除）控制，与正文是否为空无关，
// 删空后仍可重新输入；不提供发送入口，不显示已送达，也不自动重发——重新发送必须先刷新并重新核对授权。
export function UnconfirmedReplyDraft({text,onEdit}:{text:string;onEdit:(nextText:string)=>void}){
  return <div className="panel space-y-2 text-sm"><p>回复是否送达尚未确认，平台不会自动重发。以下保留了本页草稿，可继续编辑或复制，长度仍限2000字；请先刷新授权投递并核对该投递的回复状态，再决定是否发送。</p><textarea className="field" maxLength={2000} value={text} onChange={e=>onEdit(e.target.value)} aria-label="未确认发送的回复草稿"/></div>;
}
