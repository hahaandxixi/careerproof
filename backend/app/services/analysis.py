from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import suppress
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import (
    EvidenceAnalysis,
    EvidenceCandidate,
    RequirementEvidenceContext,
    validate_grounded_analysis,
)
from app.agents.evidence_workflow import citation_for_source, run_evidence_workflow
from app.agents.provider import (
    EVIDENCE_PROMPT_VERSION,
    evidence_analysis_messages,
)
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import AppError
from app.models.analysis import (
    AgentStep,
    AiUsageLog,
    AnalysisTask,
    EvidenceSource,
    MatchItem,
    MatchReport,
    SkillEvidence,
)
from app.models.enums import ConfirmationStatus, TaskStatus, VerificationStatus
from app.models.identity import User
from app.models.recruitment import Job, JobRequirement, Skill
from app.repositories.analysis import AnalysisRepository
from app.schemas.analysis import (
    AgentStepView,
    AnalysisTaskView,
    CodeEvidenceView,
    DeepSeekWebHandoff,
    DeepSeekWebImport,
    EvidenceReviewUpdate,
    MatchCreate,
    MatchItemView,
    MatchReportSummary,
    MatchReportView,
    TaskAccepted,
)
from app.services.matching_materials import analyze_materials, resolve_materials
from app.services.task_lifecycle import (
    claim_task,
    finish_task,
    heartbeat_task,
    reset_failed_task,
    update_task_progress,
)
from app.services.task_runner import run_isolated
from app.tools.code_analyzer import canonical_skill
from app.tools.evidence_levels import classify_evidence
from app.tools.matcher import FORMULA_VERSION, RequirementInput
from app.tools.skill_rubric import rubric_for

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.analysis = AnalysisRepository(session)

    async def create_match_task(self, request: MatchCreate, current_user: User) -> TaskAccepted:
        await self.session.scalar(select(User).where(User.id == current_user.id).with_for_update())
        materials = await resolve_materials(self.session, request, current_user)
        job = await self.session.scalar(
            select(Job).where(Job.id == request.job_id, Job.status == "published").with_for_update()
        )
        if not job:
            raise AppError("岗位不存在或尚未发布", code=4040, status_code=404)
        requirements = list(
            await self.session.scalars(
                select(JobRequirement)
                .where(JobRequirement.job_id == job.id)
                .order_by(JobRequirement.created_at)
            )
        )
        if not requirements:
            raise AppError("岗位尚未设置能力要求", code=4090, status_code=409)
        pending = list(
            await self.session.scalars(
                select(AnalysisTask).where(
                    AnalysisTask.created_by == current_user.id,
                    AnalysisTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
            )
        )
        for existing in pending:
            if existing.task_type == "job_match" and all(
                existing.input_snapshot.get(key) == value
                for key, value in request.model_dump(mode="json", by_alias=True).items()
            ):
                return TaskAccepted(task_id=existing.id, status=existing.status)
        if len(pending) >= 3:
            raise AppError("正在处理的任务较多，请等待完成后再提交", code=4290, status_code=429)
        snapshot = request.model_dump(mode="json", by_alias=True)
        snapshot.update(
            {
                "candidateId": str(current_user.id),
                "candidateName": current_user.display_name,
                "job": {
                    "title": job.title,
                    "category": job.category,
                    "requirements": [
                        {
                            "id": str(r.id),
                            "title": r.raw_text,
                            "skill": r.skill_name,
                            "weight": r.weight,
                        }
                        for r in requirements
                    ],
                },
                "materials": materials.snapshots,
            }
        )
        task = AnalysisTask(
            created_by=current_user.id,
            task_type="job_match",
            input_snapshot=snapshot,
            status=TaskStatus.PENDING,
            progress=0,
            current_step="等待分析真实材料",
        )
        self.session.add(task)
        await self.session.commit()
        return TaskAccepted(task_id=task.id, status=task.status)

    async def retry_match(self, task_id: UUID, user: User) -> TaskAccepted:
        task = await reset_failed_task(self.session, task_id, user)
        if task.task_type != "job_match" or not task.input_snapshot:
            raise AppError("旧任务未保存输入，请重新发起匹配", code=4094, status_code=409)
        await resolve_materials(self.session, MatchCreate.model_validate(task.input_snapshot), user)
        await self.session.commit()
        return TaskAccepted(task_id=task.id, status=task.status)

    async def get_task(self, task_id: UUID, user: User) -> AnalysisTaskView:
        task = await self.analysis.get_task(task_id)
        if not task or (task.created_by != user.id and user.role.value != "admin"):
            raise AppError("分析任务不存在或无权访问", code=4041, status_code=404)
        steps = await self.analysis.steps(task_id)
        report = await self.analysis.report_by_task(task_id)
        return AnalysisTaskView(
            id=task.id,
            task_type=task.task_type,
            status=task.status,
            progress=task.progress,
            current_step=task.current_step,
            error_message=task.error_message,
            total_cost_rmb=str(task.total_cost_rmb),
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            report_id=report.id if report else None,
            steps=[
                AgentStepView(
                    step=s.step_number,
                    event_type=s.event_type,
                    name=s.name,
                    detail=s.detail,
                    payload=s.payload,
                )
                for s in steps
            ],
        )

    @staticmethod
    def summary(report: MatchReport) -> MatchReportSummary:
        metadata = report.analysis_metadata or {}
        return MatchReportSummary(
            id=report.id,
            task_id=report.analysis_task_id,
            job_id=report.job_id,
            job_title=report.job_snapshot.get("title", "历史岗位"),
            job_category=report.job_snapshot.get("category", "other"),
            candidate_id=report.candidate_ref,
            candidate_name=report.candidate_name or "历史用户",
            overall_score=report.overall_score,
            summary=report.summary,
            analysis_mode=metadata.get("mode", "rules"),
            ai_provider=metadata.get("provider"),
            ai_model=metadata.get("model"),
            ai_fallback_used=metadata.get("fallbackUsed", False),
            evidence_context_version=metadata.get("evidenceContextVersion"),
            created_at=report.created_at,
        )

    async def list_reports(self, user: User, page: int = 1, page_size: int = 50):
        rows = await self.session.scalars(
            select(MatchReport)
            .join(AnalysisTask, AnalysisTask.id == MatchReport.analysis_task_id)
            .where(AnalysisTask.created_by == user.id)
            .order_by(MatchReport.created_at.desc(), MatchReport.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [self.summary(row) for row in rows]

    async def get_report(self, report_id: UUID, user: User) -> MatchReportView:
        report = await self.analysis.get_report(report_id)
        if not report:
            raise AppError("匹配报告不存在或无权访问", code=4042, status_code=404)
        await self.get_task(report.analysis_task_id, user)
        items = await self.analysis.report_items(report.id)
        evidence_ids = [item.evidence_id for item in items if item.evidence_id]
        evidence_by_id = {
            row.id: row
            for row in await self.session.scalars(
                select(SkillEvidence).where(SkillEvidence.id.in_(evidence_ids))
            )
        }
        return MatchReportView(
            **self.summary(report).model_dump(),
            materials=report.materials_snapshot,
            gaps=report.gaps,
            claimed_only=report.claimed_only,
            items=[self._item_view(item, evidence_by_id.get(item.evidence_id)) for item in items],
            ai_usage=(report.analysis_metadata or {}).get("usage"),
        )

    async def review_evidence(
        self,
        report_id: UUID,
        requirement_id: UUID,
        payload: EvidenceReviewUpdate,
        user: User,
    ) -> MatchItemView:
        report = await self.analysis.get_report(report_id)
        if not report:
            raise AppError("匹配报告不存在或无权访问", code=4042, status_code=404)
        await self.get_task(report.analysis_task_id, user)
        item = await self.session.scalar(
            select(MatchItem).where(
                MatchItem.report_id == report_id,
                MatchItem.requirement_id == requirement_id,
            )
        )
        if not item:
            raise AppError("报告要求项不存在", code=4047, status_code=404)
        if not item.evidence_id:
            raise AppError("该要求项没有可复核的材料证据", code=4096, status_code=409)
        evidence = await self.session.get(SkillEvidence, item.evidence_id)
        if not evidence or evidence.analysis_task_id != report.analysis_task_id:
            raise AppError("证据记录不存在", code=4048, status_code=404)
        if payload.status == ConfirmationStatus.PENDING:
            evidence.confirmed_by = None
            evidence.confirmed_at = None
        else:
            evidence.confirmed_by = user.id
            evidence.confirmed_at = datetime.now(UTC)
        evidence.confirmation_status = payload.status
        evidence.reviewer_note = payload.note or None
        await self.session.commit()
        await self.session.refresh(evidence)
        return self._item_view(item, evidence)

    async def _manual_ai_report(
        self, report_id: UUID, user: User
    ) -> tuple[MatchReport, list[MatchItem]]:
        report = await self.analysis.get_report(report_id)
        if not report:
            raise AppError("匹配报告不存在或无权访问", code=4042, status_code=404)
        await self.get_task(report.analysis_task_id, user)
        return report, await self.analysis.report_items(report.id)

    @staticmethod
    def _manual_ai_contexts(items: list[MatchItem]) -> list[RequirementEvidenceContext]:
        contexts: list[RequirementEvidenceContext] = []
        for item in items:
            snapshot = item.evidence_snapshot or {}
            evidence = []
            for raw in snapshot.get("evidenceList", [])[:3]:
                view = CodeEvidenceView.model_validate(raw)
                if not view.citation_id or not view.snippet.strip():
                    continue
                evidence.append(
                    EvidenceCandidate(
                        citation_id=view.citation_id,
                        file_path=view.file_path,
                        line_start=view.line_start,
                        line_end=view.line_end,
                        evidence_type=view.evidence_type,
                        strength=view.strength,
                        snippet=view.snippet,
                        context_complete=view.context_complete,
                        context_note=view.context_note,
                    )
                )
            contexts.append(
                RequirementEvidenceContext(
                    requirement_id=str(item.requirement_id),
                    requirement_title=snapshot.get("requirementTitle", ""),
                    skill=snapshot.get("skill", ""),
                    verdict=item.verdict,
                    rule_score=item.rule_base_score,
                    claimed=bool(snapshot.get("claimed", False)),
                    # Manual handoff deliberately excludes resume prose and identity.
                    claim_text=None,
                    evidence=evidence,
                    rating_rubric=rubric_for(snapshot.get("skill", "")),
                    rating_ceiling=classify_evidence(
                        {
                            "skill": snapshot.get("skill", ""),
                            "evidenceList": [entry.model_dump() for entry in evidence],
                        },
                        item.verdict,
                    )["evidence_level"],
                )
            )
        return contexts

    @staticmethod
    def _manual_ai_context_digest(contexts: list[RequirementEvidenceContext]) -> str:
        payload = json.dumps(
            [context.model_dump(mode="json") for context in contexts],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def deepseek_web_handoff(self, report_id: UUID, user: User) -> DeepSeekWebHandoff:
        _report, items = await self._manual_ai_report(report_id, user)
        contexts = self._manual_ai_contexts(items)
        messages = evidence_analysis_messages(contexts)
        prompt = "\n\n".join(f"【{message['role']}】\n{message['content']}" for message in messages)
        return DeepSeekWebHandoff(
            provider_url="https://chat.deepseek.com/",
            prompt=prompt,
            prompt_version=EVIDENCE_PROMPT_VERSION,
            privacy_notice=(
                "提示词不会主动加入账号身份或简历自述，但会包含岗位要求和最多三段项目证据原文；"
                "代码本身仍可能含有你写入的名称、地址或凭据。请逐段检查并删除敏感内容后再发送。"
                "发送后，内容将按 DeepSeek 的隐私政策处理。"
            ),
            requirement_count=len(contexts),
            context_digest=self._manual_ai_context_digest(contexts),
        )

    async def import_deepseek_web_analysis(
        self, report_id: UUID, payload: DeepSeekWebImport, user: User
    ) -> MatchReportView:
        report, items = await self._manual_ai_report(report_id, user)
        contexts = self._manual_ai_contexts(items)
        if payload.context_digest != self._manual_ai_context_digest(contexts):
            raise AppError("报告证据已变化，请重新生成 DeepSeek 提示词", code=4097, status_code=409)
        try:
            raw = dict(payload.response)
            raw["model"] = "deepseek-web-manual"
            raw["usage"] = {}
            analysis = EvidenceAnalysis.model_validate(raw)
            validate_grounded_analysis(contexts, analysis)
        except (ValueError, TypeError) as exc:
            raise AppError(
                f"DeepSeek 返回内容未通过证据校验：{exc}", code=4228, status_code=422
            ) from exc

        analysis_by_id = {entry.requirement_id: entry for entry in analysis.items}
        for item in items:
            result = analysis_by_id[str(item.requirement_id)]
            snapshot = dict(item.evidence_snapshot or {})
            snapshot["ai"] = {
                "status": "validated",
                "origin": "deepseek_web_manual",
                "explanation": result.explanation,
                "citationIds": result.citation_ids,
                "informationGap": result.information_gap,
                "suggestion": result.suggestion,
                "rating": result.rating.level if result.rating else None,
                "ratingRubric": result.rating.model_dump() if result.rating else None,
            }
            item.evidence_snapshot = snapshot
            item.ai_confidence = result.confidence

        metadata = dict(report.analysis_metadata or {})
        previous_manual = metadata.get("manualImport") or {}
        metadata.update(
            {
                "mode": "ai_evidence_manual",
                "provider": "deepseek_web",
                "model": "deepseek-web-manual",
                "fallbackUsed": False,
                "promptVersion": EVIDENCE_PROMPT_VERSION,
                "manualImport": {
                    "importedAt": datetime.now(UTC).isoformat(),
                    "requirementCount": len(contexts),
                    "ruleSummary": previous_manual.get("ruleSummary", report.summary),
                },
            }
        )
        report.analysis_metadata = metadata
        report.summary = analysis.summary
        await self.session.commit()
        return await self.get_report(report_id, user)

    @staticmethod
    def _item_view(item: MatchItem, evidence: SkillEvidence | None = None) -> MatchItemView:
        from app.tools.evidence_levels import classify_evidence

        snapshot = item.evidence_snapshot or {}
        ai = snapshot.get("ai") or {}
        return MatchItemView(
            **classify_evidence(
                snapshot, item.verdict, evidence.confirmation_status.value if evidence else None
            ),
            requirement_id=item.requirement_id,
            requirement_title=snapshot.get("requirementTitle", ""),
            skill=snapshot.get("skill", ""),
            claimed=snapshot.get("claimed", False),
            claim_text=snapshot.get("claimText"),
            evidence=CodeEvidenceView.model_validate(snapshot["evidence"])
            if snapshot.get("evidence")
            else None,
            evidence_list=[
                CodeEvidenceView.model_validate(e) for e in snapshot.get("evidenceList", [])
            ],
            verdict=item.verdict,
            ai_confidence=item.ai_confidence,
            rule_base_score=item.rule_base_score,
            weight=item.weight,
            final_score=item.final_score,
            explanation=item.explanation,
            formula_version=item.formula_version,
            evidence_id=item.evidence_id,
            confirmation_status=evidence.confirmation_status if evidence else None,
            confirmed_at=evidence.confirmed_at if evidence else None,
            reviewer_note=evidence.reviewer_note if evidence else None,
            ai_explanation=ai.get("explanation"),
            ai_citation_ids=ai.get("citationIds", []),
            ai_information_gap=ai.get("informationGap"),
            ai_suggestion=ai.get("suggestion"),
            ai_status=ai.get("status", "not_used"),
            ai_origin=ai.get("origin"),
        )


async def _skill_id(session: AsyncSession, name: str) -> UUID:
    name = canonical_skill(name) or name
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    await session.execute(
        insert(Skill).values(name=name).on_conflict_do_nothing(index_elements=["name"])
    )
    return await session.scalar(select(Skill.id).where(Skill.name == name))


async def execute_match_task(task_id: UUID) -> None:
    async with async_session_factory() as session:
        token = await claim_task(session, task_id, step="读取已上传的材料版本")
        if not token:
            return
        heartbeat = asyncio.create_task(heartbeat_task(task_id, token, async_session_factory))
        try:
            task = await session.get(AnalysisTask, task_id)
            snapshot = task.input_snapshot
            user = await session.get(User, task.created_by)
            if not user or not user.is_active:
                raise AppError("账号不可用", code=4032)
            materials = await resolve_materials(session, MatchCreate.model_validate(snapshot), user)
            requirements = [
                RequirementInput(UUID(r["id"]), r["title"], r["skill"], r["weight"])
                for r in snapshot["job"]["requirements"]
            ]
            if not await update_task_progress(
                session,
                task_id,
                token,
                progress=25,
                step="正在读取材料并检索候选证据",
            ):
                return
            result = await run_isolated(
                analyze_materials, requirements, materials, settings.storage_base_dir
            )
            if not await update_task_progress(
                session,
                task_id,
                token,
                progress=55,
                step="规则证据已生成，正在准备受控模型输入",
            ):
                return

            model_progress_value = 55

            async def model_progress(message: str) -> None:
                nonlocal model_progress_value
                requested_progress = (
                    62
                    if message.startswith("等待")
                    else 76
                    if "定向修正" in message
                    else 70
                    if "有限重试" in message
                    else 66
                )
                model_progress_value = max(model_progress_value, requested_progress)
                await update_task_progress(
                    session,
                    task_id,
                    token,
                    progress=model_progress_value,
                    step=message,
                )

            workflow = await run_evidence_workflow(result, progress=model_progress)
            if workflow.analysis:
                result = replace(result, summary=workflow.analysis.summary)
            if not await update_task_progress(
                session,
                task_id,
                token,
                progress=85,
                step=(
                    "模型引用已校验，正在保存报告"
                    if workflow.analysis
                    else (
                        "外部模型不可用，正在保存规则报告"
                        if workflow.fallback_used
                        else "正在保存规则报告"
                    )
                ),
            ):
                return
            ai_by_requirement = (
                {item.requirement_id: item for item in workflow.analysis.items}
                if workflow.analysis
                else {}
            )
            context_by_requirement = {
                context.requirement_id: context for context in workflow.contexts
            }
            usage_record = (
                workflow.analysis.usage if workflow.analysis else workflow.attempted_usage
            )
            usage = usage_record.model_dump() if usage_record else None
            analysis_metadata = {
                "mode": "ai_evidence" if workflow.analysis else "rules",
                "provider": workflow.provider if workflow.provider != "rules" else None,
                "model": workflow.model,
                "fallbackUsed": workflow.fallback_used,
                "fallbackReason": workflow.fallback_reason,
                "failureStage": workflow.failure_stage,
                "repairUsed": workflow.repaired,
                "citationValidation": "passed" if workflow.analysis else "not_run",
                "usage": usage,
                "evidenceContextVersion": None if result.grounding_error else "source-context-v2",
                "retrievalSteps": result.retrieval_steps,
            }
            if not await finish_task(session, task_id, token, step="材料支持度报告已生成"):
                await session.rollback()
                return
            report = MatchReport(
                analysis_task_id=task_id,
                job_id=UUID(snapshot["jobId"]),
                candidate_ref=snapshot["candidateId"],
                candidate_name=snapshot["candidateName"],
                job_snapshot=snapshot["job"],
                materials_snapshot=materials.snapshots,
                analysis_metadata=analysis_metadata,
                overall_score=result.overall_score,
                summary=result.summary,
                gaps=result.gaps,
                claimed_only=result.claimed_only,
            )
            session.add(report)
            await session.flush()
            if usage_record:
                session.add(
                    AiUsageLog(
                        analysis_task_id=task_id,
                        model=workflow.model or "unknown",
                        input_tokens=usage_record.input_tokens,
                        output_tokens=usage_record.output_tokens,
                        cache_hit_tokens=usage_record.cache_hit_tokens,
                        unit_price_snapshot={
                            "provider": workflow.provider,
                            "costCalculated": False,
                        },
                        cost_rmb=Decimal("0"),
                        latency_ms=usage_record.latency_ms,
                    )
                )
            file_map = {file["path"]: file for file in materials.files}
            # Acquire shared skill keys in a stable order across concurrent reports.
            skill_ids = {}
            for name in sorted(
                {
                    canonical_skill(item.skill) or item.skill
                    for item in result.items
                    if item.evidence_list
                }
            ):
                skill_ids[name] = await _skill_id(session, name)
            for item in result.items:
                requirement_key = str(item.requirement_id)
                ai_item = ai_by_requirement.get(requirement_key)
                context = context_by_requirement.get(requirement_key)
                evidence_list = []
                strongest_id = None
                for index, evidence in enumerate(item.evidence_list[:12]):
                    file = file_map[evidence.file_path]
                    source = EvidenceSource(
                        project_file_id=UUID(file["id"]),
                        content_hash=file["hash"],
                        locator={"lineStart": evidence.line_start, "lineEnd": evidence.line_end},
                        excerpt=evidence.snippet,
                        source_version=file["versionNumber"],
                    )
                    session.add(source)
                    await session.flush()
                    record = SkillEvidence(
                        analysis_task_id=task_id,
                        skill_id=skill_ids[canonical_skill(item.skill) or item.skill],
                        evidence_source_id=source.id,
                        confidence=item.rule_base_score,
                        verification_status=VerificationStatus.INFERRED,
                    )
                    session.add(record)
                    await session.flush()
                    if index == 0:
                        strongest_id = record.id
                    evidence_list.append(
                        {
                            **asdict(evidence),
                            "citation_id": citation_for_source(context, evidence),
                            "content_hash": file["hash"],
                            "project_file_id": file["id"],
                            "project_version_id": file["versionId"],
                            "source_id": str(source.id),
                        }
                    )
                session.add(
                    MatchItem(
                        report_id=report.id,
                        requirement_id=item.requirement_id,
                        evidence_id=strongest_id,
                        ai_confidence=ai_item.confidence if ai_item else None,
                        rule_base_score=item.rule_base_score,
                        weight=item.weight,
                        final_score=item.final_score,
                        verdict=item.verdict,
                        explanation=item.explanation,
                        formula_version=item.formula_version,
                        evidence_snapshot={
                            "requirementTitle": item.requirement_title,
                            "skill": item.skill,
                            "claimed": item.claimed,
                            "claimText": item.claim_text,
                            "evidence": evidence_list[0] if evidence_list else None,
                            "evidenceList": evidence_list,
                            "ai": {
                                "status": (
                                    "validated"
                                    if ai_item
                                    else "fallback"
                                    if workflow.fallback_used
                                    else "not_used"
                                ),
                                "explanation": ai_item.explanation if ai_item else None,
                                "citationIds": ai_item.citation_ids if ai_item else [],
                                "informationGap": (ai_item.information_gap if ai_item else None),
                                "suggestion": ai_item.suggestion if ai_item else None,
                                "rating": (
                                    ai_item.rating.model_dump()
                                    if ai_item and ai_item.rating
                                    else None
                                ),
                                "ratingRubric": context.rating_rubric if context else None,
                            },
                        },
                    )
                )
            evidence_count = sum(len(item.evidence_list) for item in result.items)
            step_rows = [
                (
                    "核对材料版本",
                    f"读取{len(materials.snapshots)}份本人材料，报告固定到所选版本",
                    {"materialCount": len(materials.snapshots)},
                ),
                (
                    "检索候选证据",
                    f"静态检查{len(materials.files)}个文件，找到{evidence_count}条候选证据",
                    {
                        "fileCount": len(materials.files),
                        "evidenceCount": evidence_count,
                        "contextRetrieval": result.retrieval_steps,
                    },
                ),
                (
                    "计算材料支持度",
                    f"使用{FORMULA_VERSION}规则；未支持的能力不参与评分",
                    {"engine": "rules", "formulaVersion": FORMULA_VERSION},
                ),
                (
                    "模型证据分析",
                    (
                        f"{workflow.model}完成{len(ai_by_requirement)}项解释"
                        if workflow.analysis
                        else "模型服务繁忙，已保留本地规则报告"
                        if workflow.fallback_reason == "provider_busy"
                        else "外部模型不可用，已回退本地规则"
                        if workflow.fallback_used
                        else "外部模型未启用"
                    ),
                    {
                        "provider": workflow.provider,
                        "promptVersion": EVIDENCE_PROMPT_VERSION,
                        "model": workflow.model,
                        "fallbackUsed": workflow.fallback_used,
                        "fallbackReason": workflow.fallback_reason,
                        "repairUsed": workflow.repaired,
                        "inputTokens": usage["input_tokens"] if usage else 0,
                        "outputTokens": usage["output_tokens"] if usage else 0,
                        "latencyMs": usage["latency_ms"] if usage else 0,
                    },
                ),
                (
                    "校验模型引用",
                    (
                        "要求编号与引用编号全部通过白名单校验"
                        if workflow.analysis
                        else "未采信模型输出，规则证据保持不变"
                    ),
                    {
                        "validation": analysis_metadata["citationValidation"],
                        "acceptedCitationCount": sum(
                            len(item.citation_ids) for item in ai_by_requirement.values()
                        ),
                    },
                ),
                (
                    "保存可追溯报告",
                    "保存材料版本、文件行号、证据哈希、模型解释与降级状态",
                    {"mode": analysis_metadata["mode"]},
                ),
            ]
            for retrieval in reversed(result.retrieval_steps):
                step_rows.insert(
                    2,
                    (
                        retrieval["name"],
                        (
                            f"一次补取，{retrieval.get('expandedCount', 0)}条多行原文；"
                            f"{retrieval.get('limitedCount', 0)}条仍为局部上下文；未执行上传代码"
                            if retrieval.get("sourceExact")
                            else "上下文核验失败，已保留规则报告"
                        ),
                        retrieval,
                    ),
                )
            for number, (name, detail, payload) in enumerate(step_rows, 1):
                session.add(
                    AgentStep(
                        analysis_task_id=task_id,
                        step_number=number,
                        event_type="tool.completed",
                        name=name,
                        detail=detail,
                        payload=payload,
                    )
                )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception("Match task failed: %s", task_id)
            message = (
                exc.message if isinstance(exc, AppError) else "分析失败，请稍后重试或重新上传材料"
            )
            if await finish_task(
                session,
                task_id,
                token,
                status=TaskStatus.FAILED,
                step="分析失败",
                error_message=message,
            ):
                await session.commit()
            else:
                await session.rollback()
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat


def format_sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
