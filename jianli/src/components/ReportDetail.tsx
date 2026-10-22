"use client";

import Link from "next/link";
import SourceIdentity, { SourceIdentityDetails } from "./SourceIdentity";
import { sourceLocationId } from "@/lib/source-label";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { MatchReport } from "@/lib/api/domain";
import { sourceContextVerified, validatedGrowthAdvice } from "@/lib/analysis-status";
import { reportAiRatedCount, reportModeLabel, reportSummaryText } from "@/lib/report-display";
import { evidenceLevelName } from "@/lib/evidence-display";
import { ErrorNotice } from "./AccessGate";
import { useAuth } from "./AuthProvider";
import EvidenceSnippet from "./EvidenceSnippet";
import SourceCoverage from "./SourceCoverage";
import EvidenceLink from "./EvidenceLink";
import EvidenceAnchorRestore from "./EvidenceAnchorRestore";
import ReportComparisonPanel from "./ReportComparisonPanel";
import McpAccessPanel from "./McpAccessPanel";
import ApplicationSubmit from "./ApplicationSubmit";
import GrowthTaskStart from "./GrowthTaskStart";
import { ReportActionLayer } from "./ReportEvidenceWorkspace";
import ReportAgentEvidence from "./ReportAgentEvidence";
import { evidenceWorkspaceSummary } from "@/lib/evidence-workspace";
import { VERDICT_LABELS as VERDICTS } from "@/lib/verdict-display.js";

const CRITERION_LABELS: Record<string, string> = { relevance: "与要求相关", operation: "实质操作", task: "完整任务" };
const REVIEW_LABELS: Record<string, string> = { pending: "待本人核对", accepted: "本人已采纳", rejected: "本人已驳回", corrected: "本人标记已修正" };
export default function ReportDetail({ id }: { id: string }) {
  const { user } = useAuth();
  const [report, setReport] = useState<MatchReport | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  useEffect(() => {
    let current = true;
    setError(""); setReport(null);
    api.getReport(id).then(value => { if (current) setReport(value); }).catch(reason => { if (current) setError(errorMessage(reason)); });
    return () => { current = false; };
  }, [id, revision]);
  if (error) return <ErrorNotice message={error} retry={() => setRevision(value => value + 1)} />;
  if (!report) return <p className="py-12 text-center text-slate-500">正在加载报告…</p>;
  const modeLabel = reportModeLabel(report);
  const aiUsed = ["ai_evidence", "ai_evidence_manual"].includes(report.analysisMode) && !report.aiFallbackUsed;
  const aiRatedCount = reportAiRatedCount(report);
  const assessedCount = report.items.filter(item => item.verdict !== "unsupported").length;
  const referenceCount = report.items.reduce((count, item) => count + item.evidenceList.filter(evidence => evidence.provenance === "reference").length, 0);
  async function review(requirementId: string, status: "pending" | "accepted" | "rejected" | "corrected") {
    setReviewing(requirementId); setError("");
    try {
      await api.reviewEvidence(id, requirementId, status, reviewNotes[requirementId]);
      setReport(await api.getReport(id));
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setReviewing(null); }
  }
  return <div className="min-w-0 space-y-6">
    <EvidenceAnchorRestore revision={report.id} />
    <Link className="text-sm text-indigo-600" href="/reports">← 匹配报告</Link>
    <aside className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-7 text-amber-900">
      规则可评估 {assessedCount}/{report.items.length} 项要求。
      {assessedCount === 0 ? " 当前规则不覆盖该岗位要求，暂不评级，请人工审阅材料。" : assessedCount < report.items.length ? " 未覆盖要求不评级；逐项核对材料，不能据此评价整个岗位或跨岗位排名。" : " 全部要求有对应规则，不代表证据完整或能力已被证实。"}
    </aside>
    {referenceCount > 0 && <aside className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm leading-7 text-sky-950">本次检索到 {referenceCount} 条第三方参考片段，可用于理解技术实现和补证方向；它们不计入个人实践评级，也不能证明本人贡献。</aside>}
    <section className="panel"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm text-indigo-600">{modeLabel}</p><h1 className="mt-2 text-2xl font-bold">{report.candidateName} × {report.jobTitle}</h1><p className="mt-3 max-w-3xl text-sm font-medium leading-7 text-indigo-950">{evidenceWorkspaceSummary(report.items)}</p><p className="mt-2 text-xs text-slate-500">{new Date(report.createdAt).toLocaleString("zh-CN")}{report.aiModel ? ` · ${report.aiModel}` : ""}</p></div><div className="text-right"><strong className="text-xl text-indigo-600">逐项实践证据等级</strong><p className="mt-2 text-xs text-slate-500">不汇总总分，不对应考试证书级别</p></div></div><p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-slate-700">{reportSummaryText(report.summary)}</p>{report.aiUsage && <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500"><span className="rounded-full bg-slate-100 px-3 py-1">模型耗时 {Math.round((report.aiUsage.latency_ms ?? 0) / 100) / 10} 秒</span><span className="rounded-full bg-slate-100 px-3 py-1">输入 {report.aiUsage.input_tokens ?? 0} tokens</span><span className="rounded-full bg-slate-100 px-3 py-1">输出 {report.aiUsage.output_tokens ?? 0} tokens</span></div>}<p className="mt-4 rounded-xl bg-amber-50 p-3 text-xs leading-6 text-amber-900">{aiUsed ? (sourceContextVerified(report.evidenceContextVersion) ? "引用编号与所展示原文已校验；解释是否充分受证据支持仍需人工核对。代码未执行，运行结果、测试质量和本人贡献均未认证。" : "历史报告仅核验引用编号，未通过本轮完整上下文与过度推断检查，建议重新生成报告。") : report.aiFallbackUsed ? "外部模型调用或校验失败，本报告已自动使用本地规则结果。" : "有证据支持不等于能力认证；没有找到证据不代表没有能力。暂不支持的技能不评级。"}</p>{user?.role !== "enterprise" && <Link className="mt-4 inline-block text-sm text-indigo-600" href={`/tasks/${report.taskId}`}>查看实际处理记录 →</Link>}</section>
    <ReportActionLayer report={report} role={user?.role} />
    <ReportAgentEvidence report={report} canGrow={user?.role === "student"} />
    {user?.role === "student" && <ApplicationSubmit reportId={report.id} />}
    <details className="panel"><summary className="cursor-pointer font-semibold">本次使用的材料版本（{report.materials.length}份）</summary><ul className="mt-3 space-y-3">{report.materials.map(material => <li key={`${material.kind}-${material.id}`} className="rounded-lg bg-slate-50 p-3"><p className="text-sm">{material.kind === "resume" ? "简历" : material.materialRole === "reference" ? "第三方参考" : "个人项目 / 作品"} · {material.title} · 第 {material.versionNumber} 版{user?.role === "student" && <Link className="ml-3 text-indigo-600" href={`/materials/${material.kind}/${material.id}`}>预览</Link>}</p><details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer">查看版本校验信息</summary><p className="mt-2 break-all">版本：{material.id}<br />内容摘要：{material.contentHash}</p></details></li>)}</ul></details>
    {user?.role === "student" && <McpAccessPanel key={id} reportId={id} />}
    {user?.role === "student" && <div id="report-comparison" className="scroll-mt-24"><ReportComparisonPanel reportId={id} revision={JSON.stringify(report.items.map(item => [item.confirmationStatus, item.confirmedAt, item.reviewerNote]))} /></div>}
    {!!report.visualClaims?.length && <section className="panel space-y-3"><h2 className="font-semibold">图片观察附件</h2><p className="text-sm leading-6 text-slate-600">以下是生成报告时保存的视觉描述，不进入当前评级或代码引用白名单。本人核对不代表独立认证。</p>{report.visualClaims.map(visual => <div key={visual.id} className="rounded-lg bg-slate-50 p-3 text-sm leading-6"><p>{visual.model} · {visual.reviewStatus === "accepted" ? "本人已采纳描述" : visual.reviewStatus === "rejected" ? "本人已驳回描述" : "待本人核对"}</p>{visual.observations?.observations.map((item, index) => <p key={index}>{item.description} · 待核验：{item.needs_verification}</p>)}<Link className="text-indigo-700 underline" href={`/materials/project/${visual.projectVersionId}`}>查看原图与当前核对状态 →</Link></div>)}</section>}
    <details className="panel"><summary className="cursor-pointer font-semibold">证据等级如何划分？</summary><p className="mt-3 text-sm leading-7">1 级：基础线索；2 级：局部操作；3 级：任务实现；4 级：验证闭环；5 级：工程验证。当前自动判定至 3 级，4、5 级需可审计的验证与复核流程，尚未开放授予。仅自述、未找到证据和规则不支持均不评级。等级参考考试的知识应用与岗位实践维度设计，不等于软考资格或 NCRE 等级。岗位权重只表示重要性，不参与平均等级。借鉴技能图谱的领域分层，AI 逐项审查相关性、实质操作和完整任务；规则约束最高等级，模型可以降低评级。AI 初评及采纳证据均不等于独立认证。</p><p className="mt-2 text-xs text-slate-500">参考：<a className="underline" href="https://ncre.neea.edu.cn/xhtml1/folder/1507/909-1.htm" target="_blank" rel="noreferrer">全国计算机等级考试介绍</a>、<a className="underline" href="https://gxt.hunan.gov.cn/gxt/rkb/zgjs11/202202/t20220210_22483921.html" target="_blank" rel="noreferrer">软考数据库系统工程师说明</a>。本项目采用自定义证据判据。</p></details>
    <p className="text-sm text-slate-600">本报告 {aiRatedCount}/{report.items.length} 项完成 AI 判据初评；其余项显示规则结果或复核状态。历史报告不会自动补写 AI 等级。</p>
    <section className="space-y-3"><h2 className="text-lg font-semibold">逐项证据</h2>{report.items.map(item => <article id={`requirement-${item.requirementId}`} key={item.requirementId} className="panel scroll-mt-24"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">{item.requirementTitle}</h3><p className="mt-2 text-xs text-slate-500">{item.skill} · 岗位权重 {item.weight} / 5</p></div><div className="text-right"><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700">{VERDICTS[item.verdict] ?? item.verdict}</span><p className="mt-3 text-sm">{item.evidenceLevelLabel ?? (item.evidenceLevel != null ? `实践证据 ${evidenceLevelName(item.evidenceLevel)}` : "待评估")}</p></div></div>
      <p className="mt-4 break-words text-sm leading-6 text-slate-600">{item.explanation}</p>
      <div aria-label={`定位${item.skill}实现来源`} className="mt-2 flex flex-wrap gap-2">{item.evidenceList.map((source, index) => ({ source, index })).filter(({ source }) => ["python_code", "fastapi_route", "pytest_test", "sql_query", "sql_schema", "react_component", "typescript_code"].includes(source.evidenceType) && source.provenance !== "reference").slice(0, 3).map(({ source, index }) => <EvidenceLink targetId={sourceLocationId(item.requirementId, source, index)} key={index} className="min-w-0 rounded border border-indigo-100 px-2 py-1 text-xs text-indigo-700 underline"><SourceIdentity source={source} materials={report.materials} /> · 第 {source.lineStart}–{source.lineEnd} 行</EvidenceLink>)}</div><p className="mt-2 break-words text-sm leading-6 text-slate-600">{item.evidenceLevelGap && `下一步核验：${item.evidenceLevelGap}`}</p><details className="mt-3 rounded-xl border border-slate-200 p-3"><summary className="cursor-pointer py-1 text-sm font-medium text-indigo-700">查看判断依据与 AI 解释</summary><p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">{item.claimed ? `简历声明：${item.claimText || item.skill}` : "未从简历中识别到该技能声明"}</p>
      <div className="mt-3 break-words rounded-lg bg-slate-50 p-3 text-sm leading-6"><p className="mb-2 text-xs text-indigo-700">{item.skillPath?.join(" → ")} · {item.evidenceLevelSource === "ai_preliminary" ? "AI 初评 · 待独立核验" : item.evidenceLevelSource === "review_suspended" ? "人工复核已暂停等级" : "规则评级 · 未采用 AI 评级"}</p><p>{item.evidenceLevelLabel}：{item.evidenceLevelReason}</p><p className="mt-1 text-slate-600">仍缺少：{item.evidenceLevelGap}</p><p className="mt-2 text-xs text-slate-400">等级规则 {item.evidenceLevelVersion} · 基于保存材料判定，不代表考试认证</p></div>
      {!!item.ratingCriteria?.length && <ul className="mt-3 space-y-2 text-sm">{item.ratingCriteria.map(criterion => <li key={criterion.criterion} className="rounded-lg border border-slate-200 p-3"><strong>{CRITERION_LABELS[criterion.criterion] ?? criterion.criterion}：{criterion.supported ? "AI 判断支持" : "尚未支持"}</strong><p className="mt-1 text-slate-600">{criterion.reason}</p><div className="mt-2 flex gap-3">{criterion.citation_ids.map(citation => <EvidenceLink className="text-xs text-indigo-600 underline" key={citation} citationId={citation}>{citation}</EvidenceLink>)}</div></li>)}</ul>}
      {item.aiStatus === "validated" && <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50/60 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-indigo-900">AI 证据解释</p>{item.aiConfidence !== null && <span className="text-xs text-indigo-700">解释置信度 {Math.round(item.aiConfidence * 100)}%</span>}</div><p className="mt-3 text-sm leading-6 text-indigo-950">{item.aiExplanation}</p>{item.aiCitationIds.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{item.aiCitationIds.map(citation => <EvidenceLink key={citation} className="rounded-full bg-white px-3 py-1 text-xs text-indigo-700 shadow-sm" citationId={citation}>引用 {citation}</EvidenceLink>)}</div>}{item.aiInformationGap && <p className="mt-3 text-xs leading-6 text-slate-600"><strong>仍缺少：</strong>{item.aiInformationGap}</p>}{item.aiSuggestion && <p className="mt-1 text-xs leading-6 text-slate-600"><strong>建议补充：</strong>{item.aiSuggestion}</p>}{item.aiSuggestionRedundant && <p className="mt-2 text-xs leading-6 text-amber-800">这条旧建议重复要求提交当前已展示的源码，仅保留原文供核对，不用于补证草稿。</p>}{item.aiTaskPlanWarning && <p role="alert" className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs leading-6 text-amber-900">{item.aiTaskPlanWarning} 已隐藏该任务草稿，请重新核对交付物后再继续。</p>}</div>}
      <SourceCoverage item={item} materials={report.materials} />
      </details>
      {user?.role === "student" && <div id={`growth-${item.requirementId}`} className="scroll-mt-24"><GrowthTaskStart reportId={report.id} requirementId={item.requirementId} advice={validatedGrowthAdvice(report, item)} /></div>}
      {item.evidenceList.length ? <details className="mt-4" ><summary className="cursor-pointer text-sm font-medium text-indigo-600">查看 {item.evidenceList.length} 条来源证据</summary><p className="mt-2 text-xs leading-6 text-slate-600">以下是规则层保存的来源，不表示模型已审阅全部材料。引用编号仅表示片段映射；AI 采用哪些引用见 AI 解释。模型是否收到这些片段需以本次实际调用记录核对。上传的输出记录与本报告固定材料版本一起保存，未独立认证运行环境、对应提交或本人贡献。</p><div className="mt-4 space-y-3">{item.evidenceList.map((evidence, index) => <div id={sourceLocationId(item.requirementId, evidence, index)} key={`${evidence.filePath}-${index}`} className={`scroll-mt-24 rounded-xl border p-4 ${evidence.citationId && item.aiCitationIds.includes(evidence.citationId) ? "border-indigo-300 bg-indigo-50/40" : "border-slate-200"}`}><p className="break-all text-xs font-medium text-slate-700">{!evidence.citationId && <span className="mr-2 text-slate-500">规则来源 {index + 1} · 无模型引用编号</span>}{evidence.citationId && <span className="mr-2 rounded bg-indigo-100 px-2 py-0.5 text-indigo-700">{evidence.citationId}</span>}{evidence.provenance === "reference" && <span className="mr-2 rounded bg-sky-100 px-2 py-0.5 text-sky-800">第三方参考 · 不计评级</span>}<SourceIdentity source={evidence} materials={report.materials} /> · 第 {evidence.lineStart}–{evidence.lineEnd} 行</p><p className="mt-2 text-xs leading-6 text-slate-500">{evidence.explanation}</p><EvidenceSnippet evidence={evidence} materials={report.materials} /><SourceIdentityDetails source={evidence} /></div>)}</div></details> : <p className="mt-4 text-sm text-slate-500">{item.verdict === "unsupported" ? "该技能超出当前规则覆盖范围，建议人工审阅。" : "本次材料中未找到支持证据，可补充作品、说明或在面试中核实。"}</p>}
      {item.evidenceId && user?.role === "student" && <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4"><summary className="cursor-pointer py-1 text-sm font-medium">本人核对记录（可选） · {REVIEW_LABELS[item.confirmationStatus ?? "pending"]}</summary><p className="mt-2 text-xs leading-6 text-slate-600">用于记录你对来源证据的意见，不是教师或企业认证；不核对也可以继续补证。驳回或标记修正会影响此报告的当前证据展示，原投递快照不变。</p><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">核对这条证据</p><span className="text-xs text-slate-500">{REVIEW_LABELS[item.confirmationStatus ?? "pending"]}</span></div><textarea className="mt-3 min-h-20 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm" maxLength={1000} placeholder="可选：记录采纳、驳回或修正原因" value={reviewNotes[item.requirementId] ?? item.reviewerNote ?? ""} onChange={event => setReviewNotes(notes => ({ ...notes, [item.requirementId]: event.target.value }))} /><div className="mt-3 flex flex-wrap gap-2"><button className="btn-secondary" disabled={reviewing === item.requirementId} onClick={() => review(item.requirementId, "accepted")}>采纳证据</button><button className="btn-secondary" disabled={reviewing === item.requirementId} onClick={() => review(item.requirementId, "rejected")}>驳回证据</button><button className="btn-secondary" disabled={reviewing === item.requirementId} onClick={() => review(item.requirementId, "corrected")}>标记已修正</button>{item.confirmationStatus !== "pending" && <button className="px-3 py-2 text-xs text-slate-500" disabled={reviewing === item.requirementId} onClick={() => review(item.requirementId, "pending")}>恢复待核对</button>}</div>{item.confirmedAt && <p className="mt-2 text-xs text-slate-400">核对时间：{new Date(item.confirmedAt).toLocaleString("zh-CN")}</p>}</details>}
      <p className="mt-4 text-xs text-slate-400">评级规则版本：{item.evidenceLevelVersion}</p>
    </article>)}</section>
  </div>;
}
