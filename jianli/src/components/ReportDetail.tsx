"use client";

import { evidenceWorkspace } from "@/lib/evidence-workspace";
import { sourceLocationId } from "@/lib/source-label";
import { displayMaterialTitle, displayJobTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import { sourceContextVerified } from "@/lib/analysis-status";
import { reportAiRatedCount } from "@/lib/report-display";
import { agentProcessSummary } from "@/lib/agent-evidence";
import AccessGate, { ErrorNotice } from "./AccessGate";
import { createReportReviewSession, initialReportReviewState } from "@/lib/report-review-session";
import { useAuth } from "./AuthProvider";
import SourceCoverage from "./SourceCoverage";
import EvidenceLink from "./EvidenceLink";
import EvidenceAnchorRestore from "./EvidenceAnchorRestore";
import ReportComparisonPanel from "./ReportComparisonPanel";
import McpAccessPanel from "./McpAccessPanel";
import ApplicationSubmit from "./ApplicationSubmit";
import ReportEvidenceWorkspace, { RequirementActionPanel } from "./ReportEvidenceWorkspace";
import ReportAgentEvidence from "./ReportAgentEvidence";
import ReportOverview from "./ReportOverview";
import { adoptedReportExplanation, workspaceStatusLabel } from "@/lib/report-workspace";
import ReportAiExplanation from "./ReportAiExplanation";
import ReportSourcePanel from "./ReportSourcePanel";
import ReportSections from "./ReportSections";
import ReportFollowUpActions from "./ReportFollowUpActions";
import { followUpCopyText } from "@/lib/report-follow-up";
import { heatmapCellClass } from "@/lib/heatmap-cell.js";

const CRITERION_LABELS: Record<string, string> = { relevance: "与要求相关", operation: "实质操作", task: "完整任务" };
const REVIEW_LABELS: Record<string, string> = { pending: "待本人核对", accepted: "本人已采纳", rejected: "本人已驳回", corrected: "本人标记已修正" };
export default function ReportDetail({ id }: { id: string }) {
  const { user } = useAuth();
  return <AccessGate><ReportWorkspace key={`${user?.id}:${user?.role}:${id}`} id={id}/></AccessGate>;
}
function ReportWorkspace({ id }: { id: string }) {
  const { user } = useAuth();
  const [state, setState] = useState(initialReportReviewState);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const session = useMemo(() => createReportReviewSession(id, {
    get: api.getReport, review: api.reviewEvidence, errorMessage,
  }, setState), [id]);
  useEffect(() => { session.activate(); void session.load(); return () => session.dispose(); }, [session]);
  const { report, error, reviewing, issues, needsSync } = state;
  if (error) return <ErrorNotice message={error} retry={() => void session.load()} />;
  if (!report) return <p className="py-12 text-center text-slate-500">正在加载报告…</p>;
  const aiUsed = ["ai_evidence", "ai_evidence_manual"].includes(report.analysisMode) && !report.aiFallbackUsed;
  const aiRatedCount = reportAiRatedCount(report);
  const assessedCount = report.items.filter(item => item.verdict !== "unsupported").length;
  const referenceCount = report.items.reduce((count, item) => count + item.evidenceList.filter(evidence => evidence.provenance === "reference").length, 0);

  const review = (requirementId: string, status: "pending" | "accepted" | "rejected" | "corrected") =>
    session.review(requirementId, status, reviewNotes[requirementId] ?? report.items.find(item => item.requirementId === requirementId)?.reviewerNote ?? undefined);
  return <div className="review-workspace report-recording-layout report-desk layout-closeout min-w-0">
    <EvidenceAnchorRestore revision={report.id} />
    <div className="report-context-bar">
      <Link className="review-back" href="/reports">我的报告 /</Link><span className="min-w-0 truncate">{displayJobTitle(report.jobTitle, report.jobId)}</span>
    </div>
    <ReportSections versions={report.materials.map(material => <p key={material.id}>{material.kind === "project" ? "项目" : "简历"} V{material.versionNumber} · {material.id.slice(0, 8)}</p>)} sections={[
      { id: "report-matching", label: "岗位对照", content: <>
    <ReportOverview report={report} role={user?.role} workbench />
    {referenceCount > 0 && <aside className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm leading-7 text-sky-950">本次检索到 {referenceCount} 条第三方参考片段，可用于理解技术实现和补证方向；它们不计入个人实践评级，也不能证明本人贡献。</aside>}
    <ReportEvidenceWorkspace key={`requirements-${report.id}`} report={report}>{report.items.map(item => <article id={`requirement-${item.requirementId}`} key={item.requirementId} className="requirement-reading-panel workspace-sheet scroll-mt-24"><div className="review-section-heading requirement-document-heading"><div className="min-w-0 flex-1">
      <h3 tabIndex={-1} className={`requirement-title ${evidenceWorkspace([item]).supported.length ? "conclusion-supported" : "conclusion-attention"}`}>
        <span className={`requirement-state-icon ${heatmapCellClass(item.verdict)}`} aria-hidden="true">{evidenceWorkspace([item]).supported.length ? "✓" : "!"}</span>
        <span>{item.skill || "岗位要求"}<span className="requirement-title-state">，{workspaceStatusLabel(item)}</span></span>
      </h3>
      <blockquote className="requirement-original">{item.requirementTitle}</blockquote>
      <p className="text-sm text-slate-500">岗位权重 {item.weight} / 5</p>
      </div><div className="flex flex-wrap items-center gap-2">
            {item.evidenceList.length ? <EvidenceLink className="btn-secondary" targetId={sourceLocationId(item.requirementId, item.evidenceList[0], 0)}>核对来源</EvidenceLink> :
        user?.role === "student" && <EvidenceLink className="btn-secondary" targetId={`growth-${item.requirementId}`}>核对与补充材料</EvidenceLink>}
      </div></div>
      <RequirementActionPanel
        report={report} item={item} role={user?.role}
        explanationVisible={!!adoptedReportExplanation(report, item)}
        explanationPanel={<ReportAiExplanation report={report} item={item} />}
        sourcePanel={<ReportSourcePanel report={report} item={item} />}
      />
      <details className="mt-4 border-t border-slate-200 pt-2"><summary className="disclosure">判据与核对记录</summary><div id={`judgement-${item.requirementId}`} className="min-w-0 scroll-mt-24">
      <details className="mt-3 text-sm"><summary className="disclosure">规则判断原文</summary><p className="mt-2 whitespace-pre-wrap break-words reading-copy">{item.explanation}</p></details>
<details className="mt-3 rounded-xl border border-slate-200 p-3"><summary className="cursor-pointer py-1 text-sm font-medium text-indigo-700">判据、声明与覆盖范围</summary><p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">{item.claimed ? `简历声明：${item.claimText || item.skill}` : "未从简历中识别到该技能声明"}</p>
      <div className="mt-3 break-words rounded-lg bg-slate-50 p-3 text-sm leading-6"><p className="mb-2 text-xs text-indigo-700">{item.skillPath?.join(" → ")} · {item.evidenceLevelSource === "ai_preliminary" ? "AI 初评 · 待独立核验" : item.evidenceLevelSource === "review_suspended" ? "人工复核已暂停等级" : "规则评级 · 未采用 AI 评级"}</p><p>{item.evidenceLevelLabel}：{item.evidenceLevelReason}</p><p className="mt-1 text-slate-600">仍缺少：{item.evidenceLevelGap}</p><p className="mt-2 text-xs text-slate-500">等级规则 {item.evidenceLevelVersion} · 基于保存材料判定，不代表考试认证</p></div>
      {item.aiStatus === "validated" && !report.aiFallbackUsed && !!item.ratingCriteria?.length && <ul className="mt-3 space-y-2 text-sm">{item.ratingCriteria.map(criterion => <li key={criterion.criterion} className="rounded-lg border border-slate-200 p-3"><strong>{CRITERION_LABELS[criterion.criterion] ?? criterion.criterion}：{criterion.supported ? "AI 判断支持" : "尚未支持"}</strong><p className="mt-1 text-slate-600">{criterion.reason}</p><div className="mt-2 flex gap-3">{criterion.citation_ids.map(citation => <EvidenceLink className="text-xs text-indigo-600 underline" key={citation} citationId={citation}>{citation}</EvidenceLink>)}</div></li>)}</ul>}
      <SourceCoverage item={item} materials={report.materials} />
      </details>
      {item.evidenceId && user?.role === "student" && <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4"><summary className="cursor-pointer py-1 text-sm font-medium">本人核对记录（可选） · {REVIEW_LABELS[item.confirmationStatus ?? "pending"]}</summary><p className="mt-2 text-xs leading-6 text-slate-600">用于记录你对来源证据的意见，不是教师或企业认证；不核对也可以继续补证。驳回或标记修正会影响此报告的当前证据展示，原投递快照不变。</p><textarea aria-label={`${item.requirementTitle}的本人核对说明`} className="mt-3 min-h-20 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm" maxLength={1000} placeholder="可选：记录采纳、驳回或修正原因" value={reviewNotes[item.requirementId] ?? item.reviewerNote ?? ""} onChange={event => setReviewNotes(notes => ({ ...notes, [item.requirementId]: event.target.value }))} /><div className="mt-3 flex flex-wrap gap-2"><button className="btn-secondary" disabled={reviewing !== null || needsSync} onClick={() => review(item.requirementId, "accepted")}>采纳证据</button><button className="btn-secondary" disabled={reviewing !== null || needsSync} onClick={() => review(item.requirementId, "rejected")}>驳回证据</button><button className="btn-secondary" disabled={reviewing !== null || needsSync} onClick={() => review(item.requirementId, "corrected")}>标记已修正</button>{item.confirmationStatus !== "pending" && <button className="btn-quiet" disabled={reviewing !== null || needsSync} onClick={() => review(item.requirementId, "pending")}>恢复待核对</button>}</div>{reviewing === item.requirementId && <p role="status" className="mt-2 text-sm text-slate-600">正在同步核对记录…</p>}{issues[item.requirementId] && <div role="alert" className="mt-3 space-y-2 text-sm text-rose-800"><p>{issues[item.requirementId].message}</p>{issues[item.requirementId].readRequired && <button type="button" className="btn-secondary" disabled={reviewing !== null} onClick={() => void session.refresh(item.requirementId)}>重新读取核对记录</button>}</div>}{item.confirmedAt && <p className="mt-2 text-xs text-slate-500">核对时间：{new Date(item.confirmedAt).toLocaleString("zh-CN")}</p>}</details>}
      </div></details>
    </article>)}</ReportEvidenceWorkspace>
    <ReportAgentEvidence report={report} canGrow={user?.role === "student"} />

    {user?.role === "student" && <McpAccessPanel key={id} reportId={id} />}
    {user?.role === "student" && <div id="report-comparison" className="scroll-mt-24"><ReportComparisonPanel report={report} revision={JSON.stringify(report.items.map(item => [item.confirmationStatus, item.confirmedAt, item.reviewerNote]))} /></div>}
    {!!report.visualClaims?.length && <section className="panel space-y-3"><h2 className="font-semibold">图片观察附件</h2><p className="text-sm leading-6 text-slate-600">以下是生成报告时保存的视觉描述，不进入当前评级或代码引用白名单。本人核对不代表独立认证。</p>{report.visualClaims.map(visual => <div key={visual.id} className="rounded-lg bg-slate-50 p-3 text-sm leading-6"><p>{visual.model} · {visual.reviewStatus === "accepted" ? "本人已采纳描述" : visual.reviewStatus === "rejected" ? "本人已驳回描述" : "待本人核对"}</p>{visual.observations?.observations.map((item, index) => <p key={index}>{item.description} · 待核验：{item.needs_verification}</p>)}<Link className="text-indigo-700 underline" href={`/materials/project/${visual.projectVersionId}`}>查看原图与当前核对状态 →</Link></div>)}</section>}
    <details className="text-sm"><summary className="disclosure">材料判据</summary><div className="space-y-2 py-2 leading-7 text-slate-700"><p>保存的等级是材料判定：基础线索、局部操作、任务实现。名称沿用生成报告时的规则，具体原因见逐项判断记录，不代表能力认证。</p><p>规则结合相关性、实质操作及任务上下文判断；仅声明、无可定位证据、规则未覆盖或复核暂停时不评级。识别实现代码不等于平台执行了完整任务，测试文件也不等于测试已通过。</p><p>岗位权重表示要求的重要性；不按等级或引用数量汇总能力分。旧记录保留当时结果，不自动改用新规则。</p></div></details>

    <details className="panel text-sm" aria-label="报告处理与范围说明"><summary className="cursor-pointer py-1 font-medium text-slate-700">分析详情</summary><div id="report-analysis" className="scroll-mt-24"><p className="mt-3 text-sm text-slate-600">规则覆盖范围：{assessedCount}/{report.items.length} 项（不是证据支持数量）。{assessedCount === 0 ? "当前规则不覆盖该岗位要求，暂不评级，请人工审阅材料。" : assessedCount < report.items.length ? "未覆盖要求不评级。" : "全部要求有对应规则，不代表证据完整或能力已被证实。"}</p><p className="mt-3 text-sm text-slate-600">本报告 {aiRatedCount}/{report.items.length} 项完成 AI 判据初评；其余项显示规则结果或复核状态。历史报告不会自动补写 AI 等级。</p>
      <p className="mt-3 leading-7 text-slate-700">{aiUsed ? (sourceContextVerified(report.evidenceContextVersion) ? "生成时记录了来源定位校验；请以逐项异常提示核对当前解释。平台未执行代码，运行结果、测试质量和本人贡献均未认证。" : "历史报告仅核验引用编号，未通过本轮完整上下文与过度推断检查，建议重新生成报告。") : "有证据支持不等于能力认证；没有找到证据不代表没有能力。暂不支持的技能不评级。"}</p>
      {report.aiModel && <p className="mt-3 text-xs leading-6 text-slate-600">保存的模型：{report.aiModel}</p>}
      {(report.aiProcess?.planningSkippedReason || report.aiProcess?.skippedReason) && <p className="mt-3 text-sm text-slate-600">{agentProcessSummary(report)}</p>}
      {report.aiUsage && <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-600">
        {report.aiUsage.latency_ms != null && <div><dt>模型耗时</dt><dd>{Math.round(report.aiUsage.latency_ms / 100) / 10} 秒</dd></div>}
        {report.aiUsage.input_tokens != null && <div><dt>输入用量</dt><dd>{report.aiUsage.input_tokens} tokens</dd></div>}
        {report.aiUsage.output_tokens != null && <div><dt>输出用量</dt><dd>{report.aiUsage.output_tokens} tokens</dd></div>}
      </dl>}
      {user?.role !== "enterprise" && <Link className="btn-secondary mt-3" href={`/tasks/${report.taskId}`}>查看实际处理记录 →</Link>}</div>
    </details>
      </> },
      { id: "report-materials", label: "材料来源", content: <>
        <h2 className="section-title">本次使用的固定材料版本（{report.materials.length}份）</h2>
        <p className="reading-copy">以下为这份报告生成时使用的材料，不随新上传自动替换。</p>
        <ul className="space-y-4">{report.materials.map(material => <li key={`${material.kind}-${material.id}`} className="panel space-y-2">
          <h3 className="text-lg font-semibold">{displayMaterialTitle(material.title, material.id)} · 第 {material.versionNumber} 版</h3>
          <p>{material.kind === "resume" ? "简历" : material.materialRole === "reference" ? "第三方参考 · 不证明本人实践" : "个人项目 / 作品"} · 材料编号 {material.id.slice(0, 8)}</p>
          {user?.role === "student" && <Link className="btn-secondary" href={`/materials/${material.kind}/${material.id}`}>预览此固定版本</Link>}
          <details><summary className="disclosure">版本校验信息</summary><p className="break-all text-sm">版本：{material.id}<br />内容摘要：{material.contentHash}</p></details>
        </li>)}</ul>
      </> },
      ...(user?.role === "student" ? [
        { id: "report-supplement", label: "补充证据", content: <>
          <h2 className="section-title">按岗位要求补充证据</h2><p className="reading-copy">上传新版材料不会改写本报告，也不会自动生成新报告；完成后回到原岗位选择版本并重新分析。</p>
          {report.items.map(item => <section key={item.requirementId} className="panel space-y-3"><h3 className="text-lg font-semibold">{item.skill} · {workspaceStatusLabel(item)}</h3><p>{item.requirementTitle}</p><ReportFollowUpActions reportId={report.id} requirementId={item.requirementId} projectVersionId={item.evidenceList.find(source => source.projectVersionId)?.projectVersionId ?? (report.materials.filter(material => material.kind === "project").length === 1 ? report.materials.find(material => material.kind === "project")?.id : undefined)} text={followUpCopyText(report, item)} /></section>)}
        </> },
        { id: "report-sharing", label: "投递授权", content: <><h2 className="section-title">投递与授权</h2><ApplicationSubmit key={`${report.id}:${report.reviewRevision}`} reportId={report.id} reviewRevision={report.reviewRevision} blocked={reviewing !== null || needsSync} onRefresh={() => void session.load()} /></> },
      ] : []),
    ]} />
  </div>;
}
