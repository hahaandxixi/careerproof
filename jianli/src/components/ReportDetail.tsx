"use client";

import { evidenceWorkspace } from "@/lib/evidence-workspace";
import { displayMaterialTitle } from "@/lib/demo-display-identity.js";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import AccessGate, { ErrorNotice } from "./AccessGate";
import { createReportReviewSession, initialReportReviewState } from "@/lib/report-review-session";
import { useAuth } from "./AuthProvider";
import SourceCoverage from "./SourceCoverage";
import EvidenceLink from "./EvidenceLink";
import ReportPaperHeader from "./ReportPaperHeader";
import ReportVersionPicker from "./ReportVersionPicker";
import { reportListHref, reportListQuery, reportOrigin } from "@/lib/report-navigation";
import ReportComparisonPanel from "./ReportComparisonPanel";
import McpAccessPanel from "./McpAccessPanel";
import ApplicationSubmit from "./ApplicationSubmit";
import ReportEvidenceWorkspace, { RequirementActionPanel } from "./ReportEvidenceWorkspace";
import ReportAgentEvidence from "./ReportAgentEvidence";
import ReportRequirementHeatmap from "./ReportRequirementHeatmap";
import SkillRadar from "./SkillRadar";
import { navigateEvidenceFragment } from "@/lib/evidence-anchor";
import { adoptedReportExplanation, filterForRequirement, initialWorkspaceFilter, workspaceRequirements, workspaceStatusLabel, type WorkspaceFilter } from "@/lib/report-workspace";
import ReportAiExplanation from "./ReportAiExplanation";
import ReportSourcePanel from "./ReportSourcePanel";
import ReportSections from "./ReportSections";
import { RequirementSupplementTarget } from "./RequirementSupplement";
import { materialReportContext, readWorkspaceFilter } from "@/lib/material-report-link";
import PracticeEntry from "./PracticeEntry";

import { initialReportRequirement, reportEntryRequirement } from "@/lib/report-reader";


const CRITERION_LABELS: Record<string, string> = { relevance: "与要求相关", operation: "实质操作", task: "完整任务" };
const REVIEW_LABELS: Record<string, string> = { pending: "待本人核对", accepted: "本人已采纳", rejected: "本人已驳回", corrected: "本人标记已修正" };
export default function ReportDetail({ id }: { id: string }) {
  const { user } = useAuth();
  return <AccessGate><ReportWorkspace key={`${user?.id}:${user?.role}:${id}`} id={id}/></AccessGate>;
}
function ReportWorkspace({ id }: { id: string }) {
  const { user } = useAuth();
  const params = useSearchParams();
  const compareBase = params.get("compareBase") || "";
  const origin = reportListQuery(reportOrigin(params.get("from"))).toString();
  const [state, setState] = useState(initialReportReviewState);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [reportFilter, setReportFilter] = useState<WorkspaceFilter>();
  const [activeRequirementId, setActiveRequirementId] = useState<string | null | undefined>(undefined);
  const session = useMemo(() => createReportReviewSession(id, {
    get: api.getReport, review: api.reviewEvidence, errorMessage,
  }, setState), [id]);
  useEffect(() => { session.activate(); void session.load(); return () => session.dispose(); }, [session]);
  useEffect(() => {
    if (!state.report) return;
    const items = state.report.items;
    const sync = () => {
      const locationParams = new URLSearchParams(window.location.search);
      const savedFilter = readWorkspaceFilter(locationParams.get("filter"));
      const fromLocation = reportEntryRequirement(items, window.location.hash, window.location.search);
      if (fromLocation) {
        setActiveRequirementId(fromLocation);
        setReportFilter(filterForRequirement(items, savedFilter ?? (items.length <= 8 ? "all" : initialWorkspaceFilter(items)), fromLocation));
        return;
      }
      if (savedFilter) {
        setReportFilter(savedFilter);
        const visible = workspaceRequirements(items, savedFilter);
        setActiveRequirementId(previous => visible.find(item => item.requirementId === previous)?.requirementId ?? visible[0]?.requirementId ?? null);
        return;
      }
      if (!window.location.hash) {
        setActiveRequirementId(initialReportRequirement(items));
        setReportFilter(undefined);
        return;
      }
      // Section and unknown legacy anchors do not invent a second selection.
      // A zero-result filter has already cleared the shared selection explicitly.
      setActiveRequirementId(previous => previous === undefined ? initialReportRequirement(items) : previous);
    };
    sync();
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => { window.removeEventListener("hashchange", sync); window.removeEventListener("popstate", sync); };
  }, [state.report]);
  const { report, error, reviewing, issues, needsSync } = state;
  if (error) return <div className="space-y-3"><ErrorNotice message={error} retry={() => void session.load()} /><Link className="btn-secondary" href={reportListHref(reportOrigin(origin))}>返回我的报告</Link></div>;
  if (!report) return <p className="py-12 text-center text-slate-500">正在加载报告…</p>;
  const projectMaterials = report.materials.filter(material => material.kind === "project");
  const supplementItems = report.items.filter(item => {
    const state = evidenceWorkspace([item]);
    return state.gaps.length > 0;
  });
  const referenceCount = report.items.reduce((count, item) => count + item.evidenceList.filter(evidence => evidence.provenance === "reference").length, 0);
  const radarRequirementId = activeRequirementId === undefined ? initialReportRequirement(report.items) : activeRequirementId;
  const filter = reportFilter ?? (report.items.length <= 8 ? "all" : initialWorkspaceFilter(report.items));
  const materialContext = materialReportContext(report.id, undefined, undefined, filter, origin);
  const changeFilter = (next: WorkspaceFilter) => {
    const matches = workspaceRequirements(report.items, next);
    const selection = matches.find(item => item.requirementId === radarRequirementId) ?? matches[0];
    setReportFilter(next);
    setActiveRequirementId(selection?.requirementId ?? null);
    const url = new URL(window.location.href);
    url.searchParams.set("filter", next);
    url.hash = selection ? `requirement-${selection.requirementId}` : "report-matching";
    if (url.href !== window.location.href) {
      window.history.pushState(window.history.state, "", url);
      window.dispatchEvent(new Event("hashchange"));
    }
  };
  const radarDimensions = report.items.map(item => ({ requirementId:item.requirementId, title:item.requirementTitle, skill:item.skill, score:item.finalScore, verdict:item.verdict, weight:item.weight, evidenceLevel:item.evidenceLevel ?? null, evidenceLevelSource:item.evidenceLevelSource ?? null, evidenceLevelVersion:item.evidenceLevelVersion ?? null, formulaVersion:item.formulaVersion }));

  const review = (requirementId: string, status: "pending" | "accepted" | "rejected" | "corrected") =>
    session.review(requirementId, status, reviewNotes[requirementId] ?? report.items.find(item => item.requirementId === requirementId)?.reviewerNote ?? undefined);
  const studentOverview = user?.role === "student" ? <div className="report-overview-band">
      <ReportRequirementHeatmap items={report.items} selectedRequirementId={radarRequirementId} />
      <section className="report-radar-side" aria-label="岗位技能雷达">
        <div className="report-radar-side-head"><h2>技能雷达</h2></div><div className="report-radar-legend" aria-label="雷达图例"><span data-state="supported">有证据支持</span><span data-state="claimed">仅简历声明</span><span data-state="gap">材料待补充</span><span data-state="unsupported">规则暂未支持</span>{report.items.some(item => item.confirmationStatus === "rejected" || item.confirmationStatus === "corrected") && <span>需复核（不绘点）</span>}</div>
        {radarRequirementId ? <SkillRadar dimensions={radarDimensions} items={report.items} initialRequirementId={radarRequirementId} selectedRequirementId={radarRequirementId} onRequirementChange={id=>navigateEvidenceFragment(`#requirement-${id}`)} variant="overview" /> : <p className="report-radar-empty">当前筛选没有可显示的要求。</p>}
      </section>
    </div> : null;
  return <div className="review-workspace report-recording-layout report-desk layout-closeout min-w-0">
    <ReportSections header={<ReportPaperHeader report={report} backHref={reportListHref(reportOrigin(origin))} versionTools={user?.role === "student" && <ReportVersionPicker report={report} origin={origin} />} />} sections={[
      { id: "report-matching", label: "岗位对照", content: <>
    {referenceCount > 0 && <aside className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm leading-7 text-sky-950">含 {referenceCount} 条第三方参考，仅供技术参考，不计入个人评级。</aside>}
    <ReportEvidenceWorkspace key={`requirements-${report.id}`} report={report} overview={studentOverview} selectedRequirementId={activeRequirementId} onRequirementChange={setActiveRequirementId} filter={filter} onFilterChange={changeFilter}>{report.items.map(item => <article id={`requirement-${item.requirementId}`} key={item.requirementId} className={`requirement-reading-panel workspace-sheet scroll-mt-24 ${item.evidenceList.length ? "requirement-has-sources" : ""}`}><div className="review-section-heading requirement-document-heading"><div className="min-w-0 flex-1">
      <h3 tabIndex={-1} className={`requirement-title ${evidenceWorkspace([item]).supported.length ? "conclusion-supported" : "conclusion-attention"}`}>

        <span>{item.skill || "岗位要求"}<span className="requirement-title-state">，{workspaceStatusLabel(item)}</span></span>
      </h3>
      <blockquote className="requirement-original">{item.requirementTitle}</blockquote>
      <p className="text-sm text-slate-500">岗位权重 {item.weight} / 5</p>
      {user?.role === "student" && <PracticeEntry reportId={report.id} requirementId={item.requirementId} />}
      </div></div>
      <RequirementActionPanel
        report={report} item={item} role={user?.role}
        explanationVisible={!!adoptedReportExplanation(report, item)}
        explanationPanel={<ReportAiExplanation report={report} item={item} />}
        sourcePanel={<ReportSourcePanel report={report} item={item} canOpenMaterial={user?.role === "student"} filter={filter} origin={origin} />}
      />
      <details className="mt-4 border-t border-slate-200 pt-2"><summary className="disclosure">判据与核对记录</summary><div id={`judgement-${item.requirementId}`} className="min-w-0 scroll-mt-24">
      <details className="mt-3 text-sm"><summary className="disclosure">规则判断原文</summary><p className="mt-2 whitespace-pre-wrap break-words reading-copy">{item.explanation}</p></details>
<details className="mt-3 rounded-xl border border-slate-200 p-3"><summary className="cursor-pointer py-1 text-sm font-medium text-[#1d4a40]">判据、声明与覆盖范围</summary><p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">{item.claimed ? `简历声明：${item.claimText || item.skill}` : "未从简历中识别到该技能声明"}</p>
      <div className="mt-3 break-words rounded-lg bg-slate-50 p-3 text-sm leading-6"><p className="mb-2 text-xs text-[#1d4a40]">{item.skillPath?.join(" → ")} · {item.evidenceLevelSource === "ai_preliminary" ? "AI 初评 · 待独立核验" : item.evidenceLevelSource === "review_suspended" ? "人工复核已暂停等级" : "规则评级 · 未采用 AI 评级"}</p><p>{item.evidenceLevelLabel}：{item.evidenceLevelReason}</p><p className="mt-1 text-slate-600">仍缺少：{item.evidenceLevelGap}</p><p className="mt-2 text-xs text-slate-500">等级规则 {item.evidenceLevelVersion}</p></div>
      {item.aiStatus === "validated" && !report.aiFallbackUsed && !!item.ratingCriteria?.length && <ul className="mt-3 space-y-2 text-sm">{item.ratingCriteria.map(criterion => <li key={criterion.criterion} className="rounded-lg border border-slate-200 p-3"><strong>{CRITERION_LABELS[criterion.criterion] ?? criterion.criterion}：{criterion.supported ? "AI 判断支持" : "尚未支持"}</strong><p className="mt-1 text-slate-600">{criterion.reason}</p><div className="mt-2 flex gap-3">{criterion.citation_ids.map(citation => <EvidenceLink className="text-xs text-[#245c50] underline" key={citation} citationId={citation}>{citation}</EvidenceLink>)}</div></li>)}</ul>}
      <SourceCoverage item={item} materials={report.materials} />
      </details>
      {item.evidenceId && user?.role === "student" && <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4"><summary className="cursor-pointer py-1 text-sm font-medium">记录你对本项证据的意见（可选） · {REVIEW_LABELS[item.confirmationStatus ?? "pending"]}</summary><p className="mt-2 text-xs leading-6 text-slate-600">不是教师或企业认证；不记录也可以继续补证。</p><textarea aria-label={`${item.requirementTitle}的证据意见`} className="mt-3 min-h-20 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm" maxLength={1000} placeholder="可选：记录采纳、驳回或修正原因" value={reviewNotes[item.requirementId] ?? item.reviewerNote ?? ""} onChange={event => setReviewNotes(notes => ({ ...notes, [item.requirementId]: event.target.value }))} /><div className="mt-3 flex flex-wrap gap-2"><button className="btn-secondary" disabled={reviewing !== null || needsSync} onClick={() => review(item.requirementId, "accepted")}>采纳证据</button><button className="btn-secondary" disabled={reviewing !== null || needsSync} onClick={() => review(item.requirementId, "rejected")}>驳回证据</button><button className="btn-secondary" disabled={reviewing !== null || needsSync} onClick={() => review(item.requirementId, "corrected")}>标记已修正</button>{item.confirmationStatus !== "pending" && <button className="btn-quiet" disabled={reviewing !== null || needsSync} onClick={() => review(item.requirementId, "pending")}>恢复待核对</button>}</div><p className="mt-2 text-xs leading-6 text-slate-600">驳回或标记修正：将更新当前报告的证据展示，已投递快照不变。</p>{reviewing === item.requirementId && <p role="status" className="mt-2 text-sm text-slate-600">正在同步核对记录…</p>}{issues[item.requirementId] && <div role="alert" className="mt-3 space-y-2 text-sm text-rose-800"><p>{issues[item.requirementId].message}</p>{issues[item.requirementId].readRequired && <button type="button" className="btn-secondary" disabled={reviewing !== null} onClick={() => void session.refresh(item.requirementId)}>重新读取核对记录</button>}</div>}{item.confirmedAt && <p className="mt-2 text-xs text-slate-500">核对时间：{new Date(item.confirmedAt).toLocaleString("zh-CN")}</p>}</details>}
      </div></details>
    </article>)}</ReportEvidenceWorkspace>
    <ReportAgentEvidence report={report} canGrow={user?.role === "student"} />

    {user?.role === "student" && <McpAccessPanel key={id} reportId={id} />}
    {user?.role === "student" && <div id="report-comparison" className="scroll-mt-24"><ReportComparisonPanel report={report} initialBaseId={compareBase} origin={origin} revision={JSON.stringify(report.items.map(item => [item.confirmationStatus, item.confirmedAt, item.reviewerNote]))} /></div>}
    {!!report.visualClaims?.length && <section className="panel space-y-3"><h2 className="font-semibold">报告生成时的视觉记录</h2><p className="text-sm leading-6 text-slate-600">仅供核对，不计入评级。</p>{report.visualClaims.map(visual => <div key={visual.id} className="rounded-lg bg-slate-50 p-3 text-sm leading-6"><p>{visual.model} · {visual.reviewStatus === "accepted" ? "本人已采纳描述" : visual.reviewStatus === "rejected" ? "本人已驳回描述" : "待本人核对"}</p>{visual.observations?.observations.map((item, index) => <p key={index}>{item.description} · 待核验：{item.needs_verification}</p>)}{user?.role === "student" && <Link className="text-[#1d4a40] underline" href={`/materials/project/${visual.projectVersionId}?${materialContext}`}>查看原图与当前核对状态 →</Link>}</div>)}</section>}
      </> },
      { id: "report-materials", label: "材料来源", content: <>
        <h2 className="section-title">固定项目版本</h2>
        {projectMaterials.length > 0 ? <ul className="space-y-4">{projectMaterials.map(material => <li key={material.id} className="panel space-y-2">
          <h3 className="text-lg font-semibold">{displayMaterialTitle(material.title, material.id)} · 第 {material.versionNumber} 版</h3>
          <p>{material.materialRole === "reference" ? "第三方参考 · 不证明本人实践" : "个人项目 / 作品"}</p>
          {user?.role === "student" && <Link className="btn-secondary" href={`/materials/project/${material.id}?${materialContext}`}>预览此固定版本</Link>}
        </li>)}</ul> : <p className="reading-copy">这份报告没有记录固定项目版本。</p>}
      </> },
      ...(user?.role === "student" ? [
        { id: "report-supplement", label: "按需补证", content: <>
          <h2 className="section-title">按需补证 · {supplementItems.length} 项实际缺口</h2>
          <p className="reading-copy">补证是可选的。上传新版材料不会改写本报告，只有你核对预选版本并确认分析后才会生成新报告。</p>
          {supplementItems.length === 0 ? <div className="panel space-y-3"><p className="text-sm leading-6 text-slate-700">当前没有可补的材料缺口。规则未覆盖的要求请人工核对。</p><Link className="btn inline-flex min-h-11 items-center" href="#report-sharing">前往投递授权</Link></div> : supplementItems.map(item => <RequirementSupplementTarget key={item.requirementId} report={report} item={item} projectVersionId={item.evidenceList.find(source => source.projectVersionId)?.projectVersionId ?? (report.materials.filter(material => material.kind === "project").length === 1 ? report.materials.find(material => material.kind === "project")?.id : undefined)} />)}
        </> },
        { id: "report-sharing", label: "投递授权", content: <><h2 className="section-title">投递与授权</h2><ApplicationSubmit key={`${report.id}:${report.reviewRevision}`} reportId={report.id} reviewRevision={report.reviewRevision} blocked={reviewing !== null || needsSync} onRefresh={() => void session.load()} /></> },
      ] : []),
    ]} />
  </div>;
}
