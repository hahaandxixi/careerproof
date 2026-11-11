"use client";
import { displayJobTitle, displayMaterialTitle } from "@/lib/demo-display-identity.js";
import IdentityName from "./IdentityName";
import ApplicationReply from "./ApplicationReply";
import { identityLabel } from "@/lib/demo-display-identity.js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import SourceIdentity, { SourceIdentityDetails } from "./SourceIdentity";
import EvidenceSnippet from "./EvidenceSnippet";
import ListPagination from "./ListPagination";
import CandidatePairComparison from "./CandidatePairComparison";
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
import { applicationFilterView, comparableApplicationGroup, comparableRadarAxes, mixedComparisonBasis } from "@/lib/application-comparison";
import { RULE_SCORE_CAP_NOTE } from "@/lib/evidence-display";
import { resolveSupportScale, supportMeasure } from "@/lib/support-index.js";
import SupportMeasureDetails from "./SupportMeasureDetails";
import { reportModeLabel, reportSummaryText } from "@/lib/report-display";
import { evidenceWorkspace } from "@/lib/evidence-workspace";
import { heatmapCellClass as cellClass } from "@/lib/heatmap-cell.js";
import { createApplicationBoardSession, initialApplicationBoardState, type ApplicationReplyResult } from "@/lib/application-board-session";
import { createRefreshGate } from "@/lib/refresh-gate";
import { trackReadRetryFocus } from "@/lib/read-retry-focus";
import { applicationBoardHistoryState, readApplicationBoardHistory, type ApplicationBoardFilters } from "@/lib/application-board-history";
import ApplicationVerification from "./ApplicationVerification";
import { activeVerificationReplyReferences, appendVerificationReplyQuestion, type VerificationReplyQuestion } from "@/lib/verification-reply-draft";

import { invalidNarrativeCitations, readableCitationText } from "@/lib/report-citations";
import { RADAR_STATUS } from "@/lib/skill-radar";
import { VERDICT_LABELS as VERDICT, APPLICATION_STATUS_LABELS as STATUS } from "@/lib/verdict-display.js";

export function ApplicationEmptyState({ filtered, onClear }: { filtered: boolean; onClear(): void }) {
  return <section className="panel space-y-3">
    <h2 className="section-title">{filtered ? "没有符合筛选的投递" : "暂无投递"}</h2>
    {!filtered && <p className="text-sm text-slate-600">学生确认授权后，投递会显示在这里。</p>}
    <div className="flex flex-wrap gap-2">{filtered && <button type="button" className="btn-secondary" onClick={onClear}>清除筛选</button>}<Link className="btn-secondary" href="/demo/heatmap">查看交互示例</Link></div>
  </section>;
}

export default function ApplicationBoard({jobId}:{jobId:string}){
  const {user}=useAuth();
  return <AccessGate roles={["enterprise"]}><Workspace key={`${user?.id}:${jobId}`} jobId={jobId} ownerId={user?.id??""}/></AccessGate>;
}
function Workspace({jobId,ownerId}:{jobId:string;ownerId:string}){
  const workspace=useRef<HTMLDivElement>(null);
  const [view,setView]=useState<"list"|"compare"|"report">("list");
  const [jobTitle,setJobTitle]=useState("");
  useEffect(()=>{let active=true;api.getJob(jobId).then(job=>{if(active)setJobTitle(job.title);}).catch(()=>{if(active)setJobTitle("");});return()=>{active=false;};},[jobId]);
  const [heldHeight,setHeldHeight]=useState<number|undefined>(undefined);
  const page=useRef(1);
  const filters=useRef<ApplicationBoardFilters>({q:"",status:"",requirementId:"",verdict:""});
  const comparisonBookmark=useRef<string[]>([]);
  const navigationReady=useRef(false);
  const rememberNavigation=useCallback(()=>{
    if(!workspace.current||!navigationReady.current||window.location.pathname!==`/jobs/${jobId}/applications`)return;
    window.history.replaceState(applicationBoardHistoryState(window.history.state,ownerId,jobId,
      {page:page.current,filters:filters.current,comparisonIds:comparisonBookmark.current}),"",window.location.href);
  },[ownerId,jobId]);
  const [state,setState]=useState(initialApplicationBoardState);
  const [anchorNotice,setAnchorNotice]=useState("");
  const {items,selected,error,notice,loading:busy}=state;
  const session=useMemo(()=>createApplicationBoardSession({
    list:async()=>{
      const url=window.location.href;
      const id=window.location.pathname===`/jobs/${jobId}/applications`?applicationAnchorId():null;
      const result=await api.jobApplications(jobId,page.current,20,filters.current);
      let unavailable=false;
      const items=await includeApplicationTarget(result.items,api.applicationDetail,id,jobId,()=>{unavailable=true;});
      const onAccepted=unavailable&&id?()=>{
        // A detached board must not rewrite history for the next owner or route.
        if(!workspace.current||document.visibilityState!=="visible"||window.location.href!==url)return;
        clearApplicationAnchor(id);
        setAnchorNotice("通知对应的投递已不可访问；下方仍显示当前岗位的其他已授权投递。");
      }:undefined;
      return {...result,items,pageItemCount:result.items.length,onAccepted};
    }, open:api.openApplication,
    detail:async id=>{const item=await api.applicationDetail(id);if(item.jobId!==jobId)throw new Error("投递不属于当前岗位");return item;},
    download:api.downloadApplicationResume, reply:api.replyApplication, errorMessage,
  },value=>{if(value.pagination)page.current=value.pagination.page;if(!value.loading&&!value.paused){comparisonBookmark.current=(value.comparison??[]).map(item=>item.id);rememberNavigation();}setState(value);}),[jobId,rememberNavigation]);
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
  const [pairIds,setPairIds]=useState<string[]>([]);
  const pairBookmark=useRef<{key:string;ids:string[]}>({key:"",ids:[]});
  const comparison=state.comparison??[];const compareIdsRef=useRef(compareIds);
  useEffect(()=>{if(busy||state.paused)return;const ids=(state.comparison??[]).map(c=>c.id);compareIdsRef.current=ids;setCompareIds(previous=>previous.join()===ids.join()?previous:ids);setPairIds(previous=>{const valid=previous.filter(id=>ids.includes(id));const next=valid.length===2?valid:ids.slice(0,2);return previous.join()===next.join()?previous:next;});if(ids.length<2)setCompareMode(false);},[state.comparison,state.paused,busy]);
  comparisonBookmark.current=compareIds;
  const [radarSelectionId,setRadarSelectionId]=useState("");
  const [workbenchMode,setWorkbenchMode]=useState<"matrix"|"radar">("matrix");
  const [verdict,setVerdict]=useState("");
  const [replyKind,setReplyKind]=useState("continue"),[replyText,setReplyText]=useState(""),[confirmReply,setConfirmReply]=useState(false);
  // 未确认草稿状态：仅写入结果未知时置位，与后续读取失败区分；与正文是否为空无关，
  // 删空后仍可编辑重输。清理代际 replyDraftGeneration 由各清理路径递增：发送前捕获本次代际，
  // await 返回后仅当代际一致才更新草稿状态，迟到的旧回调不得把清理后产生的新草稿标为未确认。
  const [unconfirmedReply,setUnconfirmedReply]=useState(false);
  const [replyResult,setReplyResult]=useState<ApplicationReplyResult|null>(null);
  const readFeedback=useRef<HTMLDivElement>(null);
  const retryLock=useRef(false),retryFromToolbar=useRef(false);
  const retryScope=useRef<"list"|"detail"|undefined>(undefined);
  const [readRetrying,setReadRetrying]=useState(false),[readComplete,setReadComplete]=useState(false);
  const replyDraftGeneration=useRef(0);
  const [replyDraftNotice,setReplyDraftNotice]=useState("");
  const [replyQuestions,setReplyQuestions]=useState<VerificationReplyQuestion[]>([]);
  const replyReferences=activeVerificationReplyReferences(replyText,replyQuestions);
  const verificationUnavailable=useCallback(()=>{replyDraftGeneration.current+=1;setReplyText("");setReplyQuestions([]);setConfirmReply(false);setReplyDraftNotice("");setUnconfirmedReply(false);setReplyResult(null);setReadComplete(false);void session.refresh();},[session]);
  function resetReply(){replyDraftGeneration.current+=1;setReplyText("");setReplyQuestions([]);setConfirmReply(false);setReplyDraftNotice("");setUnconfirmedReply(false);setReplyResult(null);setReadComplete(false);}
  async function refreshList(source:HTMLButtonElement,toolbar=false){
    if(retryLock.current||busy)return;
    retryLock.current=true;retryFromToolbar.current=toolbar;retryScope.current="list";setReadRetrying(true);resetReply();
    const generation=replyDraftGeneration.current;
    let applied=true;
    const finish=trackReadRetryFocus(source,()=>readFeedback.current,()=>applied&&replyDraftGeneration.current===generation);
    try{const refreshed=await session.refresh();applied=replyDraftGeneration.current===generation;if(applied&&refreshed)setReadComplete(true);}
    finally{retryLock.current=false;setReadRetrying(false);finish();}
  }
  async function refreshReply(source:HTMLButtonElement){
    if(retryLock.current||busy)return;
    retryLock.current=true;retryFromToolbar.current=false;retryScope.current=state.errorScope;setReadRetrying(true);
    let generation=replyDraftGeneration.current,applied=true;
    const finish=trackReadRetryFocus(source,()=>readFeedback.current,()=>applied&&replyDraftGeneration.current===generation);
    try{
      const result=await session.refreshReply();
      applied=result.applied&&replyDraftGeneration.current===generation;
      if(!applied)return;
      if(result.accessLost){resetReply();generation=replyDraftGeneration.current;}
      else if(result.refresh==="complete"){setUnconfirmedReply(false);setConfirmReply(false);}
      setReplyResult(result);
    }finally{retryLock.current=false;setReadRetrying(false);finish();}
  }
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
    const restoreNavigation=()=>{
      const saved=readApplicationBoardHistory(window.history.state,ownerId,jobId);
      page.current=saved.page;filters.current=saved.filters;comparisonBookmark.current=saved.comparisonIds;
      setQuery(saved.filters.q);setStatus(saved.filters.status);setFocus(saved.filters.requirementId);setFocusLabel("");setVerdict(saved.filters.verdict);
      setCompareIds(saved.comparisonIds);setCompareMode(false);setPairIds([]);setView("list");
      navigationReady.current=true;
    };
    restoreNavigation();
    session.activate();
    let alive=true;
    let releaseFrame:number|undefined;
    let pendingResume:ReturnType<typeof session.resume>|undefined;
    const holdLayout=()=>{
      const height=workspace.current?.getBoundingClientRect().height;
      if(height)setHeldHeight(previous=>previous??height);
    };
    let restoredHistoryUrl="";
    const refresh=()=>{if(restoredHistoryUrl===window.location.href){restoredHistoryUrl="";return;}setAnchorNotice("");resetReply();setHeldHeight(undefined);void session.refresh();};
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
        if(!result.selectedId){setRadarSelectionId("");}
        // Keep the old page height until authorized content has rendered. No
        // scroll command or anchor navigation runs during an ordinary return.
        releaseFrame=requestAnimationFrame(()=>{if(alive&&document.visibilityState==="visible")setHeldHeight(undefined);});
      }).finally(()=>{if(pendingResume===pending)pendingResume=undefined;});
    };
    // B-06：返回页面时 visibilitychange、focus、pageshow 紧邻触发，合并为一次刷新。
    const gate=createRefreshGate(resume);
    const historyReturn=()=>{
      if(window.location.pathname!==`/jobs/${jobId}/applications`)return;
      restoredHistoryUrl=window.location.href;
      setAnchorNotice("");navigationReady.current=false;session.clear();restoreNavigation();gate.reset();gate.trigger();
    };
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
    window.addEventListener("popstate",historyReturn);
    return ()=>{alive=false;navigationReady.current=false;if(releaseFrame!==undefined)cancelAnimationFrame(releaseFrame);session.dispose();document.removeEventListener("visibilitychange",visibility);window.removeEventListener("focus",focusWindow);window.removeEventListener("blur",blurWindow);window.removeEventListener("pageshow",gate.trigger);window.removeEventListener("hashchange",refresh);window.removeEventListener("popstate",historyReturn);};
  },[session,ownerId,jobId]);
  const dimensions=Array.from(new Map(items.flatMap(i=>i.dimensions).map(d=>[d.requirementId,d])).values());
  // Predicates are applied before server counting/pagination; local sorting must
  // not drop matches found in the fixed report's text outside visible labels.
  const filterView=applicationFilterView(items,"","","",selected?.id);
  const visible=filterView.visible;
  const matrixSource=compareMode ? comparison : visible;
  const mixedBasis=mixedComparisonBasis(matrixSource);
  const basisGroup=comparableApplicationGroup(matrixSource);
  const matrixItems=mixedBasis ? basisGroup.comparable : matrixSource;
  const excludedBasisItems=mixedBasis ? basisGroup.excluded : [];
  const matrixDimensions=Array.from(new Map(matrixItems.flatMap(i=>i.dimensions).map(d=>[d.requirementId,d])).values());
  const pair=pairIds.map(id=>comparison.find(c=>c.id===id)).filter((c):c is ApplicationView=>!!c);
  useEffect(()=>{if(workbenchMode!=="radar"||!selected?.report)return;if(!selected.dimensions.some(d=>d.requirementId===radarSelectionId))setRadarSelectionId(selected.dimensions[0]?.requirementId??"");},[workbenchMode,selected?.id,selected?.report?.id,selected?.dimensions,radarSelectionId]);
  function enterPersonalRadar(){const candidate=selected??matrixItems[0]??comparison[0]??items[0];if(!candidate)return;setWorkbenchMode("radar");if(!candidate.report){void open(candidate.id,radarSelectionId||candidate.dimensions[0]?.requirementId||"",true);}else if(!radarSelectionId){setRadarSelectionId(candidate.dimensions[0]?.requirementId||"");}}
  const pairComparable=pair.length===2 && comparableRadarAxes(pair[0],pair[1]);
  const sourceCandidate=selected;
  const pairOptions=mixedBasis?matrixItems:comparison;
  const mixedBasisCopy=matrixSource.some(c=>c.fixedRequirementBasisComplete!==true)?"部分固定报告缺少岗位要求信息，请逐份核对。":"报告的比较依据不同，请逐份核对。";
  function chooseComparison(ids:string[]){setReadComplete(false);compareIdsRef.current=ids;comparisonBookmark.current=ids;setCompareIds(ids);rememberNavigation();setCompareMode(false);void session.selectComparison(ids);}
  function toggleCompare(id:string){chooseComparison(toggleComparisonCandidate(compareIdsRef.current,id));}
  const selectedOutside=filterView.selectedOutside;
  function applyFilters(next={q:query.trim(),status,requirementId:focus,verdict}){setReadComplete(false);filters.current=next;page.current=1;rememberNavigation();void session.filter();}
  function clearFilters(){setQuery("");setFocus("");setFocusLabel("");setVerdict("");setStatus("");applyFilters({q:"",status:"",requirementId:"",verdict:""});}
  // B-15：列表或筛选结果每次变化后尝试一次定位。新导航 revealed；目标在 items 但被筛掉时转为提示；
  // 已消费的导航在同 hash 下反复调用只会得到 idle/waiting，因此自动刷新、撤回不会劫持视口。
  useEffect(()=>{applyAnchor(items.map(i=>i.id),visible.map(i=>i.id));},[applyAnchor,items,visible]);
  const activeView=view==="report"&&selected?.report?"report":view==="compare"&&pairComparable?"compare":"list";
  const blockedDraft=unconfirmedReply||(replyResult?.write==="rejected"&&replyResult.refresh!=="complete"&&!replyResult.accessLost);
  const replyNeedsRead=!!replyResult&&replyResult.refresh!=="complete"&&!replyResult.accessLost;
  async function open(id:string,requirementId="",stay=false){
    setRadarSelectionId(requirementId);
    if(selected?.id===id && selected.report){
      if(!stay)setView("report");
      return;
    }
    resetReply();
    if(await session.open(id)&&!stay)setView("report");
  }
  function openFixedReport(){setView("report");requestAnimationFrame(()=>{const panel=document.getElementById("selected-application-report");if(!panel)return;panel.scrollIntoView({block:"start"});(panel.querySelector("summary") as HTMLElement|null)?.focus({preventScroll:true});});}
  async function download(){await session.download(file=>{const url=URL.createObjectURL(file.blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=file.filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
  return <div ref={workspace} style={heldHeight?{minHeight:heldHeight}:undefined} className="review-workspace enterprise-recording-layout enterprise-review-page space-y-4"><div className="enterprise-compact-head"><div className="review-section-heading"><div><p className="workspace-meta">授权投递</p><h1 className="page-title">{displayJobTitle(jobTitle || items[0]?.jobTitle || "岗位候选人", jobId)}</h1></div>
    {((!error&&!replyNeedsRead&&!readRetrying)||(readRetrying&&retryFromToolbar.current))&&<ReadRetryButton busy={busy} quiet label="刷新授权投递" onRetry={source=>void refreshList(source,true)}/>}</div><nav className="review-view-nav" aria-label="候选人核对视图">{([{key:"list",label:"候选人"},{key:"compare",label:`双人对照（${comparison.length}）`},{key:"report",label:selected?`固定报告 · ${identityLabel(selected.candidateName,selected.candidateId)}`:"固定报告"}] as const).map(tab=><button key={tab.key} type="button" aria-pressed={activeView===tab.key} disabled={tab.key==="compare"?!pairComparable:tab.key==="report"?!selected?.report:false} title={tab.key==="compare"&&!pairComparable&&comparison.length>=2?"所选报告的依据或要求轴不可比，请重新选择":undefined} onClick={()=>setView(tab.key)}>{tab.label}</button>)}</nav></div>
    <details className="text-xs leading-5 text-slate-500"><summary className="disclosure">查看授权范围与使用说明</summary><p className="mt-2">仅显示向本岗位明确投递的报告，未投递或已撤回的学生不可见。每页20份，可翻页查看更早投递；筛选作用于本岗位全部已授权投递，并在计数和分页前执行。通知目标会单独核对授权后补入。翻页和筛选保留本次会话的对照名单；切回页面时先核对授权，再恢复本次会话的选中状态；离开窗口会清空未发送的回复，请发送前再次核对。学生撤回不会追回已下载副本。</p></details>
    {activeView==="list"&&state.pagination&&<><ListPagination label="候选人分页" value={state.pagination} busy={busy} onPage={value=>{page.current=value;rememberNavigation();resetReply();void session.filter();}}/>{items.length>state.pagination.pageItemCount&&<p className="text-xs text-slate-600">另外展示了当前页之外的已授权候选人，不计入本页记录数。</p>}</>}
    {notice&&<p role="status" className="panel text-amber-800">{notice}</p>}
    {anchorNotice&&<p role="status" className="panel text-amber-800">{anchorNotice}</p>}
    {anchorFilterTarget&&<div role="status" className="panel space-y-2 text-amber-800"><p>通知指向的投递在当前筛选结果之外，未自动滚动。可以清除筛选后定位，或直接打开该投递报告。</p><div className="flex flex-wrap gap-x-4 gap-y-1"><button type="button" className="btn-secondary" onClick={clearFilters}>清除筛选并定位</button><button type="button" className="btn-secondary" disabled={busy} onClick={()=>{setAnchorFilterTarget("");anchor.dismiss();void open(anchorFilterTarget);}}>直接打开该投递报告</button><button type="button" className="btn-quiet" onClick={()=>{anchor.dismiss();setAnchorFilterTarget("");}}>关闭</button></div></div>}
    <div className={`board-work-layout ${activeView==="list"?"board-work-list":""}`}>
    <form className={`enterprise-candidate-filters board-filter-rail ${activeView==="list"?"flex flex-col gap-4":"hidden"}`} onSubmit={event=>{event.preventDefault();applyFilters();}}>
      <h2 className="font-semibold">筛选投递</h2>
      <div className="flex flex-wrap items-end gap-2"><label className="min-w-0 flex-1 basis-full text-sm">查找候选人<input type="search" className="field mt-1" placeholder="姓名或报告内容" maxLength={200} value={query} onChange={e=>setQuery(e.target.value)}/></label><button className="btn" disabled={busy}>搜索</button><button className="btn-quiet" type="button" disabled={busy} onClick={clearFilters}>重置</button></div>
      <div role="group" aria-label="投递状态" className="board-filter-options border-t border-slate-200 pt-3">{[["","全部状态"],["submitted","已投递"],["viewed","企业已查看"],["downloaded","简历下载已交付"],["replied","企业已回复"]].map(([value,label])=><button key={value} type="button" className="selection-toggle" aria-pressed={status===value} disabled={busy} onClick={()=>{setStatus(value);applyFilters({q:query.trim(),status:value,requirementId:focus,verdict});}}>{label}</button>)}</div>
      <details className="border-t border-slate-100 pt-1"><summary className="disclosure">要求与证据筛选</summary><div className="grid gap-3 py-2 lg:grid-cols-[minmax(12rem,1fr)_2fr]"><RequirementFocusSelect dimensions={dimensions} value={focus} selectedLabel={focusLabel} onChange={(id,label)=>{setFocus(id);setFocusLabel(label);applyFilters({q:query.trim(),status,requirementId:id,verdict});}}/><div><p className="mb-2 text-sm">证据状态</p><div role="group" aria-label="证据状态" className="flex flex-wrap gap-2">{[["","全部"],["supported","有证据或部分支持"],["claimed_only","仅简历自述"],["gap","缺少材料"],["unsupported","暂不可评"]].map(([value,label])=><button key={value} type="button" className="selection-toggle" aria-pressed={verdict===value} disabled={busy} onClick={()=>{setVerdict(value);applyFilters({q:query.trim(),status,requirementId:focus,verdict:value});}}>{label}</button>)}</div></div></div></details>
      <div className="enterprise-candidate-groups" aria-label="候选人分组与选择">
        <h3>候选人选择</h3>
        <p>同依据可对照；不同依据单独核对。</p>
        <ul>{matrixItems.map(i=><li key={i.id}><button type="button" className="candidate-select" aria-pressed={selected?.id===i.id} disabled={busy} onClick={()=>void open(i.id,"",true)}><IdentityName name={i.candidateName} identityId={i.candidateId}/><span>{STATUS[i.status]??i.status}</span></button><label><input type="checkbox" checked={compareIds.includes(i.id)} disabled={busy||(!compareIds.includes(i.id)&&compareIds.length>=4)} onChange={()=>toggleCompare(i.id)}/>加入对照</label></li>)}{excludedBasisItems.map(app=><li key={app.id} className="is-isolated"><span><IdentityName name={app.candidateName} identityId={app.candidateId}/></span><small>不同依据 · 逐份核对</small></li>)}</ul>
      </div>
    </form>
    <div className="board-main min-w-0 space-y-4">
    <div ref={readFeedback} tabIndex={-1} aria-label="读取结果" hidden={!busy&&!error&&!replyResult&&!readComplete} className="rounded-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600">
      {blockedDraft?<UnconfirmedReplyDraft text={replyText} rejected={replyResult?.write==="rejected"} busy={busy} error={error} onRefresh={source=>void refreshReply(source)} onEdit={text=>applyReplyDraftEdit(text,setReplyText,setConfirmReply)}/>:replyResult?<ReplyReadFeedback result={replyResult} busy={busy} error={error} scope={state.errorScope??(readRetrying?retryScope.current:undefined)} onRefresh={source=>void refreshReply(source)}/>:<ApplicationReadFeedback busy={busy} error={error} scope={state.errorScope??state.loadingScope} retrying={readRetrying} complete={readComplete} onRefresh={source=>void refreshList(source)}/>}
    </div>
    {activeView==="list"&&mixedBasis&&<p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{mixedBasisCopy}</p>}
    {activeView==="list"&&!items.length&&!busy&&!error&&<ApplicationEmptyState filtered={Object.values(filters.current).some(Boolean)} onClear={clearFilters}/>}
    {activeView==="list"&&!!items.length&&filterView.empty&&<CandidateFilterNotice empty selectedName={selectedOutside&&selected?identityLabel(selected.candidateName,selected.candidateId):undefined} onClear={clearFilters}/>}
    {activeView!=="report"&&!!comparison.length&&<section className="space-y-2 border-y border-slate-200 py-2" aria-label="跨页对照名单"><div className="flex flex-wrap items-center gap-x-4 gap-y-2"><h2 className="text-sm font-semibold">对照名单 · {comparison.length}/4 位</h2><ul className="flex flex-wrap gap-2">{comparison.map(c=><li key={c.id} className="flex max-w-full items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm"><span className="break-words"><IdentityName name={c.candidateName} identityId={c.candidateId}/></span><button type="button" disabled={busy} className="btn-quiet btn-compact shrink-0" aria-label={`移出对照：${identityLabel(c.candidateName,c.candidateId)}`} onClick={()=>chooseComparison(compareIds.filter(id=>id!==c.id))}>移除</button></li>)}</ul><button type="button" disabled={busy} className="btn-quiet btn-compact" onClick={()=>chooseComparison([])}>清空对照</button></div>{comparison.length===4&&<p className="text-sm text-slate-600">已达4位上限，请先移除一位再加入。</p>}{comparison.length>2&&<div className="flex flex-wrap gap-3">{[0,1].map(index=><label key={index} className="min-w-0 text-sm">深入比较候选人{index===0?"A":"B"}<select className="field mt-1" value={pairIds[index]??""} onChange={e=>setPairIds(previous=>{const next=[...previous];next[index]=e.target.value;return next;})}>{pairOptions.map(c=><option key={c.id} value={c.id} disabled={pairIds[1-index]===c.id}>{identityLabel(c.candidateName,c.candidateId)}</option>)}</select></label>)}</div>}</section>}
    {activeView==="compare"&&pairComparable&&<CandidatePairComparison key={pairIds.join(":")} candidates={pair as [ApplicationView,ApplicationView]} busy={busy} initialIds={pairBookmark.current.key===pairIds.join(":")?pairBookmark.current.ids:undefined} onRequirementChange={(id,side)=>{const key=pairIds.join(":");if(pairBookmark.current.key!==key)pairBookmark.current={key,ids:[]};pairBookmark.current.ids[side]=id;}} onOpen={()=>{resetReply();void session.openComparison(pairIds);}}/>}
    {activeView==="list"&&!!matrixItems.length&&<div className="enterprise-review-workbench" data-mode={workbenchMode}><div className="enterprise-workbench-switch" role="group" aria-label="企业审阅视图"><button type="button" aria-pressed={workbenchMode==="matrix"} onClick={()=>setWorkbenchMode("matrix")}>热力矩阵</button><button type="button" aria-pressed={workbenchMode==="radar"} disabled={busy||!(selected||matrixItems[0]||items[0])} onClick={enterPersonalRadar}>个人雷达{selected?` · ${identityLabel(selected.candidateName,selected.candidateId)}`:""}</button></div><section className="comparison-document enterprise-matrix-workspace space-y-3"><div className="review-section-heading"><h2 className="text-lg font-semibold">岗位要求 × 投递候选人</h2><button type="button" className={compareIds.length>=2&&compareIds.length<=4?"btn":"btn-secondary"} disabled={compareIds.length<2||compareIds.length>4} aria-pressed={compareMode} onClick={()=>setCompareMode(!compareMode)}>{compareMode?"显示本页全部候选人":`热力图仅看所选（${compareIds.length}）`}</button></div><div className="relative isolate z-0 max-h-[65vh] overflow-auto rounded-lg border border-slate-200" role="region" aria-label="可滚动的授权候选人对照表" tabIndex={0}><table className="enterprise-matrix w-full table-fixed border-separate border-spacing-0 text-sm" ><colgroup><col style={{width:"28%"}}/>{matrixItems.map(i=><col key={i.id} style={{width:`${72/matrixItems.length}%`}}/>)}</colgroup><thead className="sticky top-0 z-20 bg-white"><tr><th scope="col" className="sticky left-0 z-30 break-words bg-white p-3 text-left">岗位要求</th>{matrixItems.map(i=><th scope="col" id={`application-${i.id}`} key={i.id} className={`break-words p-3 align-top ${selected?.id===i.id ? "bg-indigo-50" : "bg-white"}`}><button type="button" className="candidate-select w-full min-w-0 whitespace-normal break-words" aria-pressed={selected?.id===i.id} disabled={busy} onClick={()=>void open(i.id,"",true)}><IdentityName name={i.candidateName} identityId={i.candidateId}/></button><p className="mt-1 text-slate-600">{STATUS[i.status]??i.status}</p><label className="mt-2 flex items-center justify-center gap-1 font-normal"><input type="checkbox" checked={compareIds.includes(i.id)} disabled={busy||(!compareIds.includes(i.id)&&compareIds.length>=4)} onChange={()=>toggleCompare(i.id)}/>加入对照</label></th>)}</tr></thead><tbody>{matrixDimensions.map(d=><tr key={d.requirementId}><th scope="row" className="sticky left-0 z-10 break-words border-t border-slate-100 bg-white p-3 text-left font-medium text-slate-700">{d.title} · 权重{d.weight}</th>{matrixItems.map(i=>{const value=i.dimensions.find(v=>v.requirementId===d.requirementId);return <td key={i.id} className={`border-t border-slate-100 p-1 ${selected?.id===i.id ? "bg-indigo-50/70" : ""}`}><button type="button" disabled={busy || !value} title={value ? value.title + " · 权重" + value.weight : "本报告无此项"} aria-pressed={!!value&&selected?.id===i.id&&radarSelectionId===d.requirementId} aria-label={`${identityLabel(i.candidateName,i.candidateId)} · ${d.title} · ${value ? VERDICT[value.verdict]??value.verdict : "本报告无此项"}`} className={`w-full rounded-lg border p-3 hover:outline hover:outline-1 hover:outline-slate-400 ${value&&selected?.id===i.id&&radarSelectionId===d.requirementId?"ring-2 ring-inset ring-indigo-600":""} ${value ? cellClass(value.verdict,value.score) : "border-dashed border-slate-200 bg-slate-50 text-slate-600"}`} onClick={()=>{if(value)void open(i.id,d.requirementId,true);}}><span>{value ? VERDICT[value.verdict]??value.verdict : "本报告无此项"}</span></button></td>;})}</tr>)}</tbody></table></div></section>{workbenchMode==="radar"&&<section className="enterprise-radar-workspace" aria-label="个人材料支持雷达">{selected?<><div className="enterprise-radar-heading"><div className="min-w-0"><h2><IdentityName name={selected.candidateName} identityId={selected.candidateId}/> · 个人雷达</h2><p>{radarSelectionId?matrixDimensions.find(d=>d.requirementId===radarSelectionId)?.title||"当前要求":"选择要求后查看对应判断与来源"}</p></div><label className="enterprise-radar-select"><span>按文字选择要求</span><select className="field" value={radarSelectionId||selected.dimensions[0]?.requirementId||""} onChange={event=>setRadarSelectionId(event.target.value)}>{selected.dimensions.map(dimension=><option key={dimension.requirementId} value={dimension.requirementId}>{dimension.skill||dimension.title}</option>)}</select></label><ul className="enterprise-radar-legend" aria-label="雷达图例"><li><i className="dot-supported" />{RADAR_STATUS.supported} / {RADAR_STATUS.partial}</li><li><i className="dot-claimed" />{RADAR_STATUS.claimed_only}</li><li><i className="dot-gap" />{RADAR_STATUS.gap}（不绘点）</li><li>— {RADAR_STATUS.unsupported}</li></ul></div>{selected.report?<div className="enterprise-radar-embed"><SkillRadar key={`${selected.id}:${selected.report.id}:${radarSelectionId}`} dimensions={selected.dimensions} items={selected.report.items} initialRequirementId={radarSelectionId||selected.dimensions[0]?.requirementId||""} onRequirementChange={id=>{setRadarSelectionId(id);}} materials={selected.report.materials} aiFallbackUsed={selected.report.aiFallbackUsed} variant="overview"/></div>:<p className="text-sm text-slate-600">正在读取固定报告。读取完成后可点选雷达要求。</p>}</>:<p className="text-sm text-slate-600">先从左侧或矩阵选择一名候选人，再查看个人雷达。</p>}</section>}<aside className="enterprise-source-pane" aria-label="当前要求来源">{pairComparable&&<div className="enterprise-source-tabs" role="group" aria-label="A/B 来源切换">{pair.map((candidate,index)=><button key={candidate.id} type="button" aria-pressed={sourceCandidate?.id===candidate.id} disabled={busy} onClick={()=>void open(candidate.id,radarSelectionId||candidate.dimensions[0]?.requirementId||"",true)}>{index===0?"A":"B"} · {identityLabel(candidate.candidateName,candidate.candidateId)}</button>)}</div>}{sourceCandidate?.report?<SelectedRequirementEvidence application={sourceCandidate} requirementId={radarSelectionId||sourceCandidate.dimensions[0]?.requirementId||""} onOpenReport={openFixedReport}/>:<p className="text-sm text-slate-600">选择矩阵单元格查看固定报告来源。</p>}</aside>{pairComparable&&radarSelectionId&&pair.length===2&&(()=>{const requirement=matrixDimensions.find(d=>d.requirementId===radarSelectionId);const a=pair[0].dimensions.find(d=>d.requirementId===radarSelectionId);const b=pair[1].dimensions.find(d=>d.requirementId===radarSelectionId);return <div className="workbench-difference"><div><span>当前要求</span><strong>{requirement?.title||"未选择"}</strong></div>{[pair[0],pair[1]].map((candidate,index)=>{const value=index===0?a:b;return <div key={candidate.id} className="workbench-difference-candidate"><IdentityName name={candidate.candidateName} identityId={candidate.candidateId}/><strong>{value?(VERDICT[value.verdict]??value.verdict):"本报告无此项"}</strong>{(()=>{const saved=pair[index].report?.items.find(entry=>entry.requirementId===radarSelectionId)?.evidenceList[0];return saved?<span>{saved.filePath.split("/").pop()} · 第{saved.lineStart}–{saved.lineEnd}行</span>:<span>来源需在右侧切换读取</span>;})()}</div>;})}<p>{a&&b?(a.verdict===b.verdict?"当前记录状态相同，仍需分别核对来源。":"可见判断状态不同，请分别核对两份固定报告。"):"报告未对齐该要求，不能直接比较。"}</p></div>;})()}</div>}

    {activeView==="list"&&excludedBasisItems.length>0&&<section className="enterprise-uncomparable-list space-y-3"><div className="review-section-heading"><div><h2 className="section-title">其他报告 · 逐份核对</h2><p className="mt-1 text-sm leading-6 text-slate-600">以下报告的依据或要求轴不同，不进入上面的同尺度矩阵或双人对照。</p></div></div><ul className="divide-y divide-[#e0dbcd] border-y border-[#e0dbcd]">{excludedBasisItems.map(app=><li key={app.id} className="space-y-2 py-4"><div className="flex flex-wrap items-baseline justify-between gap-2"><span className="font-semibold"><IdentityName name={app.candidateName} identityId={app.candidateId}/></span><span className="text-sm text-slate-600">{STATUS[app.status] ?? app.status}</span></div><p className="text-sm leading-6 text-slate-700">投递于 <time dateTime={app.createdAt}>{new Date(app.createdAt).toLocaleString("zh-CN")}</time> · {app.dimensions.length} 项岗位要求</p><p className="break-words text-sm leading-6 text-slate-600">固定材料：{app.report?.materials?.map(material=>`${displayMaterialTitle(material.title, material.id)} v${material.versionNumber}`).join(" · ") || "未记录材料版本"}</p><button type="button" className="btn-secondary" disabled={busy} onClick={()=>void open(app.id)}>打开这份固定报告</button></li>)}</ul></section>}
    {selected?.report&&<details id="selected-application-report" hidden={activeView!=="report"} open={activeView==="report"} className="panel scroll-mt-28 space-y-4"><summary className="cursor-pointer py-1 font-semibold text-indigo-700">固定报告与回复</summary>{selectedOutside&&<CandidateFilterNotice empty={false} selectedName={identityLabel(selected.candidateName,selected.candidateId)} onClear={clearFilters}/>}<FixedReportOverview application={selected}/><button type="button" className="btn-secondary" disabled={busy} onClick={()=>void download()}>下载本次授权简历</button>
      <div className="enterprise-fixed-review"><SkillRadar key={`${selected.id}:${selected.report.id}:${radarSelectionId}`} dimensions={selected.dimensions} items={selected.report.items} initialRequirementId={radarSelectionId} onRequirementChange={id=>{setRadarSelectionId(id);}} materials={selected.report.materials} aiFallbackUsed={selected.report.aiFallbackUsed} variant="overview"/>
      <div className="enterprise-fixed-source"><SelectedRequirementEvidence application={selected} requirementId={radarSelectionId||selected.dimensions[0]?.requirementId||""} showReportLink={false}/></div></div>
      <details className="rounded-xl border border-slate-200 p-4"><summary className="cursor-pointer text-sm font-medium text-indigo-700">企业核验建议</summary><div className="mt-4"><ApplicationVerification key={`${selected.id}:${selected.report.id}`} applicationId={selected.id} report={selected.report} requirementComparison={selected.requirementComparison} onUnavailable={verificationUnavailable} onUseQuestion={selected.status!=="replied"&&!busy ? useVerificationQuestion : undefined}/></div></details>
      <details className="rounded-xl border border-slate-200 p-4"><summary className="cursor-pointer text-sm font-medium text-indigo-700">查看完整逐项报告（{selected.report.items.length}项）</summary><ul className="mt-4 space-y-3">{selected.report.items.map(item=><SavedRequirementDetail key={item.requirementId} item={item} report={selected.report!}/>)}</ul></details>
      {selected.status!=="replied"&&replyResult?.write!=="confirmed"&&<div className="space-y-3 border-t pt-4">
        <h3 className="font-semibold">发送站内回复</h3>
        <p className="rounded-lg bg-slate-50 p-3 text-sm">收件人：<strong><IdentityName name={selected.candidateName} identityId={selected.candidateId}/></strong></p>
        <p className="text-xs text-slate-500">发送后将直接显示给该学生，本期不可覆盖。</p>
        {replyDraftNotice&&<p role="status" className="text-sm text-indigo-800">{replyDraftNotice}</p>}
        <label className="block text-sm">回应类型<select className="field mt-1" disabled={busy} value={replyKind} onChange={e=>{setReplyKind(e.target.value);setConfirmReply(false);}}><option value="continue">继续沟通</option><option value="interview">面试邀请</option><option value="declined">暂不推进</option></select></label>
        <label className="block text-sm">回复正文<textarea className="field mt-1" maxLength={2000} disabled={busy} value={replyText} onChange={e=>applyReplyDraftEdit(e.target.value,setReplyText,setConfirmReply)}/></label>
        {replyReferences.length>0&&<div className="rounded-lg bg-slate-50 p-3 text-xs leading-6"><p>将随回复保存的原报告定位（企业人工确认后才发送）：</p><ul className="mt-1 space-y-1">{replyReferences.map(reference=><li key={reference.requirementId} className="flex flex-wrap items-center gap-2"><span>{`第${selected.report!.items.findIndex(item=>item.requirementId===reference.requirementId)+1}项：`}{selected.report!.items.find(item=>item.requirementId===reference.requirementId)?.requirementTitle || "岗位要求"} · {reference.citationIds.length ? reference.citationIds.join("、") : "暂无支持引用"}</span><button type="button" className="btn-quiet btn-compact shrink-0" onClick={()=>{setReplyQuestions(previous=>previous.filter(question=>question.requirementId!==reference.requirementId));setConfirmReply(false);}}>移除定位</button></li>)}</ul><p className="text-slate-500">删除正文中的要求名称或引用编号后，对应定位会自动移除。</p></div>}
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmReply} disabled={busy} onChange={e=>setConfirmReply(e.target.checked)}/>我已核对正文，确认发送给这位投递学生</label>
        <button type="button" className="btn" disabled={busy||!confirmReply||!replyText.trim()} onClick={async()=>{const text=replyText,references=replyReferences;const generation=replyDraftGeneration.current;const result=await session.reply(replyKind,text,references);const outcome=replySendOutcome(result,replyDraftGeneration.current===generation);if(outcome==="ignore")return;if(outcome==="reset")resetReply();else{setConfirmReply(false);setUnconfirmedReply(outcome==="mark-unconfirmed");}setReplyResult(result);}}>确认发送站内回复</button>
      </div>}
      <ApplicationReply application={selected} sent/>
    </details>}
    </div>
    </div>
  </div>;
}

type RequirementOption = { requirementId: string; title: string; skill: string };
export function FixedReportOverview({application}:{application:ApplicationView}){
  const report=application.report;
  if(!report)return null;
  const counts=evidenceWorkspace(report.items);
  return <div className="space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0"><h2 className="break-words text-xl font-semibold"><IdentityName name={application.candidateName} identityId={application.candidateId}/> · 投递时固定报告</h2><p className="mt-1 break-words text-sm text-slate-600">{displayJobTitle(report.jobTitle || application.jobTitle, application.jobId)}</p></div>
      {reportModeLabel(report) && <span className="rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-800">{reportModeLabel(report)}</span>}
    </div>
    <dl className="flex flex-wrap items-center gap-x-5 gap-y-2 border-y border-slate-200 py-2 text-sm text-slate-700">
      <div className="flex items-baseline gap-2"><dt>有证据支持</dt><dd className="text-base font-semibold tabular-nums text-emerald-700">{counts.supported.length}</dd></div>
      <div className="flex items-baseline gap-2"><dt>待补材料</dt><dd className="text-base font-semibold tabular-nums text-amber-700">{counts.gaps.length}</dd></div>
      <div className="flex items-baseline gap-2"><dt>岗位要求</dt><dd className="text-base font-semibold tabular-nums text-slate-900">{report.items.length}</dd></div>
    </dl>
    {(counts.partial.length>0||counts.other.length>0)&&<p className="text-sm text-slate-600">部分支持 {counts.partial.length} 项 · 未覆盖或需复核 {counts.other.length} 项</p>}
    <details className="border-t border-slate-200 pt-3 text-sm text-slate-600"><summary className="w-fit cursor-pointer py-1 text-indigo-700">报告时间、材料版本与判断范围</summary>
      <p className="mt-3">生成于 {new Date(report.createdAt).toLocaleString("zh-CN")}</p>
      <ul className="mt-2 space-y-1">{report.materials.map(material=><li key={`${material.kind}:${material.id}`} className="break-words">{material.title} · 第{material.versionNumber}版</li>)}</ul>
      {!report.materials.length&&<p className="mt-2">历史报告未记录材料版本清单，请按保存的来源核对。</p>}
      <p className="mt-3 leading-6">{reportSummaryText(report.summary)}</p>
      <p className="mt-2 leading-6">{RULE_SCORE_CAP_NOTE}材料证据不等于运行成功、本人贡献或录用结论；平台不执行上传的代码。完整来源可在下方逐项展开。</p>
    </details>
  </div>;
}

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
  const useAi = item.aiStatus === "validated" && !report.aiFallbackUsed && !invalidNarrativeCitations(item).length;
  const aiExplanation = useAi && item.aiExplanation?.trim() ? item.aiExplanation : null;
  const gap = (useAi ? item.aiInformationGap : null) || item.evidenceLevelGap;
  return <>
    {invalidNarrativeCitations(item).length>0&&<p className="text-sm text-amber-900">历史AI解释的引用需重新核对，当前显示规则判断。</p>}
    <p className="break-words text-base leading-7"><span className="font-medium">{aiExplanation ? "AI解释" : "规则解释"}：</span>{aiExplanation?readableCitationText(item,aiExplanation):item.explanation}</p>
    {gap && <p className="text-sm text-slate-700">待核对：{gap}</p>}
  </>;
}

export function SavedRequirementDetail({ item, report }: { item: ReportItem; report: MatchReport }) {
  const scale=resolveSupportScale(report.items);
  const measure=supportMeasure({score:item.finalScore,formulaVersion:item.formulaVersion,verdict:item.verdict},scale);
  return <li className="rounded-lg border border-slate-200 p-3 text-sm">
    <strong>{item.requirementTitle || item.skill}</strong>
    <p className="mt-2 text-base">{VERDICT[item.verdict] ?? item.verdict}</p>
    {measure.ratio!=null&&<p className="mt-2">{scale.label} {measure.text}</p>}
    {measure.issue&&item.verdict!=="unsupported"&&<p role="status" className="mt-2 text-amber-900">{measure.issue}；原始值 {String(measure.raw??"未记录")}。</p>}
    <details className="mt-2 text-sm"><summary className="cursor-pointer text-indigo-700">原报告计量与等级</summary><SupportMeasureDetails raw={item.finalScore} formulaVersion={item.formulaVersion} scale={scale}/><p>{item.evidenceLevelLabel??"未评级"} · {item.evidenceLevelReason}</p></details>
    <div className="mt-2 space-y-2"><SavedRequirementInterpretation item={item} report={report}/></div>
    <details className="mt-2"><summary className="cursor-pointer text-indigo-700">查看本次授权引用片段</summary>{item.evidenceList.map((source, index) => <div key={index} className="mt-2 text-xs"><p className="break-all">{source.citationId ?? "引用"} · <SourceIdentity source={source} materials={report.materials ?? []} /> · 第{source.lineStart}—{source.lineEnd}行</p><pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{source.snippet}</pre><SourceIdentityDetails source={source} /></div>)}</details>
  </li>;
}

export function SelectedRequirementEvidence({ application, requirementId, showReportLink = true, onOpenReport }: { application: ApplicationView; requirementId: string; showReportLink?: boolean; onOpenReport?: () => void }) {
  const report = application.report;
  const item = report?.items.find(value => value.requirementId === requirementId);
  const source = item?.evidenceList[0];
  if (!report) return null;
  return <section className="panel space-y-2 border-indigo-200" aria-label="当前格子的固定报告依据">
    <h2 className="font-semibold"><IdentityName name={application.candidateName} identityId={application.candidateId}/> · {item?.requirementTitle || "该报告未包含这条要求"}</h2>
    {item ? <>
      <div className="flex flex-wrap items-center gap-2 text-sm"><strong>{VERDICT[item.verdict] ?? item.verdict}</strong><span className="text-slate-600">{report.materials.map(material => `${displayMaterialTitle(material.title, material.id)} v${material.versionNumber}`).join(" · ") || "材料版本未记录"}</span></div>
      {source ? <div className="enterprise-source-code"><p className="enterprise-source-code-meta"><SourceIdentity source={source} materials={report.materials} /> · 第{source.lineStart}–{source.lineEnd}行</p><EvidenceSnippet evidence={source} materials={report.materials} showContextNote={false} theme="dark"/><SourceIdentityDetails source={source} /></div> : <p className="rounded border border-dashed border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{item.verdict === "unsupported" ? "此项暂未评估，请核对岗位要求与材料。" : item.verdict === "claimed_only" ? "暂无此项要求的可定位引用；目前仅见简历声明。" : "暂无此项要求的可定位引用；这是材料缺口。"}</p>}
      <details className="text-sm"><summary className="disclosure">判断依据</summary><div className="mt-2 space-y-2"><SavedRequirementInterpretation item={item} report={report}/>{item.evidenceList.slice(1).map((extra, index) => <div key={`${extra.citationId}-${index}`} className="rounded bg-slate-50 p-2 text-xs"><p><SourceIdentity source={extra} materials={report.materials} /> · 第{extra.lineStart}–{extra.lineEnd}行</p><EvidenceSnippet evidence={extra} materials={report.materials} showContextNote={false}/></div>)}</div></details>
    </> : <p className="text-sm text-slate-600">不同报告的要求版本可能不同；请按各自固定要求核对，不能把空格子当作能力不足。</p>}
    {showReportLink && (onOpenReport ? <button type="button" className="btn-secondary" onClick={onOpenReport}>查看报告与回复</button> : <a className="btn-secondary" href="#selected-application-report">查看报告与回复</a>)}
  </section>;
}

// 回复失败（请求失败或响应丢失）后的唯一编辑规则：正文可继续修改，任何编辑都撤销人工发送确认，
// 使已勾选的确认不会被带进下一次核对。正常编辑与失败草稿共用，避免两处行为漂移。
export function applyReplyDraftEdit(text:string,edit:(text:string)=>void,confirm:(on:boolean)=>void){
  edit(text);confirm(false);
}
// 写入回执与读取结果分别处理；读取失败不得抹去已确认的提交。
// 迟到的旧回调（等待期间发生过清理，新草稿可能已产生）一律忽略，不得改变新状态。
export type ReplySendOutcome="reset"|"mark-rejected"|"mark-unconfirmed"|"ignore";
export function replySendOutcome(result:ApplicationReplyResult,generationUnchanged:boolean):ReplySendOutcome{
  if(!generationUnchanged||!result.applied||result.write==="not_sent")return "ignore";
  if(result.accessLost||result.write==="confirmed")return "reset";
  return result.write==="rejected"?"mark-rejected":"mark-unconfirmed";
}

export function ReadRetryButton({busy,label,onRetry,quiet=false}:{busy:boolean;label:string;onRetry:(source:HTMLButtonElement)=>void;quiet?:boolean}){
  return <button type="button" className={`${quiet?"btn-quiet":"btn-secondary"} aria-disabled:cursor-wait aria-disabled:opacity-60`} aria-label={label} aria-disabled={busy} onClick={event=>{if(!busy)onRetry(event.currentTarget);}}>{busy?"正在读取…":label}</button>;
}

export function ApplicationReadFeedback({busy,error,scope,retrying,complete,onRefresh}:{busy:boolean;error:string;scope?:"list"|"detail";retrying:boolean;complete:boolean;onRefresh:(source:HTMLButtonElement)=>void}){
  if(!busy&&!error&&!complete)return null;
  if(!busy&&!error&&complete)return <p role="status" className="text-sm text-emerald-800">投递列表已更新。</p>;
  const label=scope==="detail"?"返回投递列表":"重新加载投递列表";
  return <section className="panel space-y-3" aria-label={scope==="detail"?"报告读取状态":"投递列表读取状态"}>
    <h2 className="font-semibold">{busy?(scope==="detail"?"正在读取固定报告":"正在加载投递列表"):(scope==="detail"?"固定报告未能读取":"投递列表加载失败")}</h2>
    {error&&!busy&&<p role="alert" className="text-sm text-rose-700">{error}</p>}
    {(!!error||retrying)&&<ReadRetryButton busy={busy} label={label} onRetry={onRefresh}/>}
  </section>;
}

export function ReplyReadFeedback({result,busy,onRefresh,error="",scope}:{result:ApplicationReplyResult;busy:boolean;onRefresh:(source:HTMLButtonElement)=>void;error?:string;scope?:"list"|"detail"}){
  if(result.write==="not_sent"||!result.applied)return null;
  if(result.write!=="confirmed"&&result.refresh!=="complete"&&!result.accessLost)return null;
  const message=result.write==="confirmed"
    ? result.accessLost?"回复已发送；当前投递已无法访问，报告与草稿已清除。":busy?"回复已发送，正在重新读取状态…":result.refresh==="complete"?"回复已发送。":scope==="list"?"回复已发送，投递列表刷新失败。":"回复已发送，最新状态刷新失败。"
    : result.accessLost?"当前投递已无法访问，报告与草稿已清除。":result.write==="rejected"?"本次发送被拒绝，已刷新当前回复状态，请核对下方记录。":"已刷新当前回复状态，请核对下方记录；不会自动重发。";
  return <div role="status" className="panel flex flex-wrap items-center justify-between gap-3 text-sm"><div><p>{message}</p>{error&&!busy&&<p role="alert" className="mt-2 text-rose-700">{error}</p>}</div>{result.refresh==="failed"&&!result.accessLost&&<ReadRetryButton busy={busy} label={scope==="list"?"重新加载投递列表":"刷新回复状态"} onRetry={onRefresh}/>}</div>;
}
// 筛选只影响候选列表，不关闭已打开报告或清空未发送草稿；用可见提示避免把旧报告误认为当前筛选结果。
export function CandidateFilterNotice({empty,selectedName,onClear}:{empty:boolean;selectedName?:string;onClear:()=>void}){
  if(!empty&&!selectedName)return null;
  const text=empty
    ? `本岗位没有符合关键词、状态、岗位要求和证据状态组合的候选人。${selectedName?` 当前打开的 ${selectedName} 不在筛选结果中；报告与未发送草稿仍保留。`:""}`
    : `当前打开的 ${selectedName} 不在本页筛选结果中。以下保留先前选中的固定报告与未发送草稿；回复仍指向 ${selectedName} 对应的投递，不会因筛选改变收件人。`;
  return <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900"><p>{text}</p><button type="button" className="btn-secondary mt-2" onClick={onClear}>清除全部筛选</button></div>;
}
// 会话失败清空列表与旧报告后，草稿只保留在本页组件状态：可编辑、可复制、仍限2000字；
// 面板由未确认草稿状态（发送失败置位、resetReply 生命周期清除）控制，与正文是否为空无关，
// 删空后仍可重新输入；不提供发送入口，不显示已送达，也不自动重发——重新发送必须先刷新并重新核对授权。
export function UnconfirmedReplyDraft({text,onEdit,rejected=false,busy=false,onRefresh,error=""}:{text:string;onEdit:(nextText:string)=>void;rejected?:boolean;busy?:boolean;onRefresh?:(source:HTMLButtonElement)=>void;error?:string}){
  return <div className="panel space-y-2 text-sm"><p>{rejected?"本次发送被拒绝。":"回复是否送达尚未确认，平台不会自动重发。"}以下保留了本页草稿，可继续编辑或复制，长度仍限2000字；请先刷新授权投递并核对该投递的回复状态，再决定是否发送。</p>{error&&!busy&&<p role="alert" className="text-rose-700">{error}</p>}<textarea className="field" maxLength={2000} disabled={busy} value={text} onChange={e=>onEdit(e.target.value)} aria-label={rejected?"未发送的回复草稿":"未确认发送的回复草稿"}/>{onRefresh&&<ReadRetryButton busy={busy} label="刷新回复状态" onRetry={onRefresh}/>}</div>;
}
