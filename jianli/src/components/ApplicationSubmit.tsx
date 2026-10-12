"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api/client";
import { createApplicationSubmitSession } from "@/lib/application-submit-session";

// 传智杯44：轻量投递。首屏只保留三个必须先看到的风险点（固定报告/引用、
// 简历下载可能含联系方式、撤回但已下载副本无法追回），其余分享说明折叠进
// details；授权不预勾选，确认按钮忙碌防重、失败后可直接重试。
export default function ApplicationSubmit({reportId}: {reportId:string}) {
  const [consent,setConsent] = useState(false);
  const [state,setState] = useState({busy:false,notice:"",done:false});
  const session = useMemo(()=>createApplicationSubmitSession({submit:()=>api.createApplication(reportId),errorMessage},setState),[reportId]);
  return <section id="application-submit" className="panel scroll-mt-24 space-y-3">
    <h2 className="font-semibold">向该岗位投递本份报告</h2>
    <p className="text-sm leading-6 text-slate-600">确认后，该岗位所属企业将获得以下访问权：</p>
    <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-slate-600">
      <li>查看<b>投递时固定的报告</b>与代码引用片段，后续新报告不会替换本次内容；</li>
      <li>下载<b>本次投递的简历原文件</b>，文件可能含联系方式；</li>
      <li>以上访问可随时撤回，但<b>撤回前已下载的副本无法追回</b>。</li>
    </ul>
    <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={consent} disabled={state.busy} onChange={e=>setConsent(e.target.checked)} /><span>我已确认本份材料适合分享，同意向该岗位所属企业授权上述内容。</span></label>
    {state.done ? <Link href="/applications" className="btn inline-block">查看投递进度 →</Link> : <button type="button" className="btn" disabled={!consent||state.busy} onClick={()=>{void session.submit();}}>{state.busy?"正在投递…":"确认投递"}</button>}
    {state.notice&&<p role="status" className={state.done?"text-sm text-indigo-700":"text-sm text-rose-700"}>{state.notice}</p>}
    <details className="text-sm leading-6 text-slate-600">
      <summary className="cursor-pointer select-none text-indigo-700">其他分享说明与限制</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>仅授权本份报告；其他报告与其他简历版本不在授权范围内。</li>
        <li>投递不自动发送邮件、不调用 AI，也不向其他第三方分享。</li>
        <li>撤回后可重新确认授权再投递，将建立新记录，旧投递不会恢复或被覆盖。</li>
      </ul>
    </details>
    <Link href="/applications" className="block text-sm text-indigo-700 underline">查看我的投递</Link>
  </section>;
}
