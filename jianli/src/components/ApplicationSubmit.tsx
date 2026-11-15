"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api/client";
import { createApplicationSubmitSession } from "@/lib/application-submit-session";

export default function ApplicationSubmit({reportId, reviewRevision, blocked = false, onRefresh}: {reportId:string; reviewRevision?:number|null; blocked?:boolean; onRefresh?:()=>void}) {
  const [consent,setConsent] = useState(false);
  const [state,setState] = useState({busy:false,notice:"",done:false,applicationId:""});
  const synchronized = !blocked && Number.isSafeInteger(reviewRevision) && (reviewRevision ?? 0) >= 1;
  useEffect(() => { setConsent(false); }, [reportId, blocked, reviewRevision]);
  const session = useMemo(()=>createApplicationSubmitSession({submit:()=>api.createApplication(reportId, reviewRevision!),errorMessage},value => {
    setState(value);
    if (value.notice && !value.done) setConsent(false);
  }),[reportId, reviewRevision]);
  return <section id="application-submit" className="panel scroll-mt-24 space-y-3">
    {!synchronized && <p role="status" className="text-sm text-amber-800">请先同步最新核对记录，再确认投递。{!blocked && onRefresh && <button type="button" className="btn-secondary" onClick={onRefresh}>重新读取报告</button>}</p>}
    <h2 className="font-semibold">向该岗位投递本份报告</h2>
    <p className="text-sm leading-6 text-slate-600">确认后，该岗位所属企业将获得以下访问权：</p>
    <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-slate-600">
      <li>查看<b>投递时固定的报告</b>与代码引用片段，后续新报告不会替换本次内容；</li>
      <li>下载<b>本次投递的简历原文件</b>，文件可能含联系方式；</li>
      <li>以上访问可随时撤回，但<b>撤回前已下载的副本无法追回</b>。</li>
    </ul>
    <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={consent} disabled={state.busy || !synchronized} onChange={e=>setConsent(e.target.checked)} /><span>我已确认本份材料适合分享，同意向该岗位所属企业授权上述内容。</span></label>
    {state.done ? <Link href={state.applicationId ? `/applications#application-${encodeURIComponent(state.applicationId)}` : "/applications"} className="btn inline-block">查看投递进度 →</Link> : <button type="button" className="btn" disabled={!consent||state.busy||!synchronized} onClick={()=>{if (consent && synchronized) void session.submit();}}>{state.busy?"正在投递…":"确认投递"}</button>}
    {state.notice&&<p role="status" className={state.done?"text-sm text-brand-ink":"text-sm text-rose-700"}>{state.notice}</p>}
    {state.notice && !state.done && onRefresh && <button type="button" className="btn-secondary" disabled={state.busy || blocked} onClick={() => { setConsent(false); onRefresh(); }}>重新读取报告后确认</button>}
  </section>;
}
