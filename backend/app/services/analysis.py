from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import suppress
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.evidence_workflow import citation_for_source, run_evidence_workflow
from app.agents.provider import EVIDENCE_PROMPT_VERSION
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
from app.models.enums import ConfirmationStatus, TaskStatus, UserRole, VerificationStatus
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.identity import StudentProfile, User
from app.models.portfolio import Project, ProjectVersion, Resume, ResumeVersion
from app.models.recruitment import Job, JobRequirement, Skill
from app.repositories.analysis import AnalysisRepository
from app.schemas.analysis import (
    AgentStepView,
    AnalysisTaskView,
    CareerTaskPlan,
    CodeEvidenceView,
    EvidenceReviewUpdate,
    MatchCreate,
    MatchItemView,
    MatchReportSummary,
    MatchReportView,
    TaskAccepted,
)
from app.services.action_plan import build_action_plan
from app.services.ai_budget import SharedBudgetService
from app.services.ai_request_attempts import (
    AttemptContext,
    AttemptService,
    DurableRequestObserver,
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
from app.tools.evidence_levels import VERSION as EVIDENCE_LEVEL_VERSION
from app.tools.function_coverage import (
    redundant_source_request,
    task_plan_redundant_source_request,
)
from app.tools.matcher import FORMULA_VERSION, RequirementInput
from app.tools.semantic_retrieval import VERSION as SEMANTIC_VERSION
from app.tools.semantic_retrieval import model_available

logger = logging.getLogger(__name__)

USAGE_LEDGER_TIMEOUT_SECONDS = 5


def _log_ledger_outcome(booking: asyncio.Task) -> None:
    if not booking.cancelled() and booking.exception():
        logger.error(
            "Usage ledger booking failed after decoupling: %s",
            booking.exception(),
            exc_info=booking.exception(),
        )


async def _materials_still_frozen(
    session: AsyncSession, owner_id: UUID, frozen_materials: list
) -> bool:
    """Every frozen material version must still exist, still belong to the
    owner, and still carry its frozen version number and content hash."""
    if not frozen_materials:
        return False
    for material in frozen_materials:
        try:
            version_id = UUID(str(material.get("id")))
        except (TypeError, ValueError, AttributeError):
            return False
        scope = (
            select(ResumeVersion.id)
            .join(Resume, Resume.id == ResumeVersion.resume_id)
            .join(StudentProfile, StudentProfile.id == Resume.student_id)
            .where(
                ResumeVersion.id == version_id,
                ResumeVersion.version_number == material.get("versionNumber"),
                ResumeVersion.content_hash == material.get("contentHash"),
                ResumeVersion.parse_status == "completed",
                StudentProfile.user_id == owner_id,
            )
            if material.get("kind") == "resume"
            else select(ProjectVersion.id)
            .join(Project, Project.id == ProjectVersion.project_id)
            .join(StudentProfile, StudentProfile.id == Project.student_id)
            .where(
                ProjectVersion.id == version_id,
                ProjectVersion.version_number == material.get("versionNumber"),
                ProjectVersion.content_hash == material.get("contentHash"),
                ProjectVersion.analysis_status == "completed",
                StudentProfile.user_id == owner_id,
            )
        )
        if material.get("kind") not in {"resume", "project"}:
            return False
        # Stable for this short transaction; released before any HTTP.
        if await session.scalar(scope.with_for_update(key_share=True)) is None:
            return False
    return True


async def _authorize_matching_snapshot(
    session: AsyncSession,
    task_id: UUID,
    owner_id: UUID,
    run_token: UUID,
    frozen_snapshot: dict,
) -> None:
    # User -> Task -> materials, both before sending and before publication.
    # Neither transaction contains network calls.
    owner = await session.scalar(
        select(User).where(User.id == owner_id).with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if not owner or not owner.is_active or owner.role != UserRole.STUDENT:
        raise AppError("账号不可用", code=4032, status_code=403)
    task_row = await session.scalar(
        select(AnalysisTask).where(AnalysisTask.id == task_id)
        .with_for_update(key_share=True).execution_options(populate_existing=True)
    )
    if (not task_row or task_row.created_by != owner_id
            or task_row.task_type != "job_match" or task_row.status != TaskStatus.RUNNING
            or task_row.run_token != run_token):
        raise AppError("任务执行授权已失效", code=4096, status_code=409)
    current = task_row.input_snapshot or {}
    if any(current.get(key) != frozen_snapshot.get(key) for key in (
        "job", "materials", "externalAiConsent", "jobId", "candidateId",
        "resumeVersionId", "projectVersionIds", "usePreviousReport", "previousReportId",
    )):
        raise AppError("任务固定输入已被替换，禁止发送或保存AI结果", code=4096, status_code=409)
    if not await _materials_still_frozen(
        session, owner_id, frozen_snapshot.get("materials") or [],
    ):
        raise AppError("任务固定材料版本已失效", code=4096, status_code=409)


class _DurableMatchingLedger:
    """Attempt services created for one claimed match run.

    Facts are keyed by (task_id, run_token), so settlement and summary work
    through whichever service was created last; steps only label the rows.
    """

    def __init__(self) -> None:
        self.services: list[AttemptService] = []

    @property
    def installed(self) -> bool:
        return bool(self.services)

    @property
    def active_service(self) -> AttemptService:
        return self.services[-1]


def _matching_observer_factory(
    session_factory,
    task_id: UUID,
    owner_id: UUID,
    run_token: UUID,
    frozen_snapshot: dict,
    ledger: _DurableMatchingLedger,
):
    """Server-side binding of task/owner/run_token/provider/model per step.

    The authorize callback re-checks, fresh before every physical send, that
    the owner is an active student, the frozen material versions still belong
    to them unchanged, and the task's fixed job/materials/consent fields were
    not replaced. Routing authorization is never treated as permanent.
    """

    async def authorize_attempt(attempt_session: AsyncSession) -> None:
        await _authorize_matching_snapshot(
            attempt_session, task_id, owner_id, run_token, frozen_snapshot,
        )

    def factory(provider, step):
        service = AttemptService(
            session_factory,
            AttemptContext(task_id, owner_id, run_token, step, provider.name, provider.model),
            authorize=authorize_attempt,
            budget=SharedBudgetService(),
        )
        ledger.services.append(service)
        return DurableRequestObserver(service)

    return factory


async def _settle_durable_receipts(ledger: _DurableMatchingLedger) -> int:
    """Book trustworthy durable receipts in their own short transactions.

    Bounded and shielded like the verification chain: the write never shares
    the business finish/report transaction, and a failure leaves
    received_unbooked rows for reconciliation without resending any HTTP.
    """

    async def bounded_booking() -> int:
        return await asyncio.wait_for(
            ledger.active_service.reconcile(), timeout=USAGE_LEDGER_TIMEOUT_SECONDS
        )

    booking = asyncio.create_task(bounded_booking())
    booking.add_done_callback(_log_ledger_outcome)
    return await asyncio.shield(booking)


def _configured_ai_identity() -> tuple[str, str | None]:
    if not settings.ai_external_enabled or settings.ai_provider == "mock":
        return "rules", None
    model = (
        settings.deepseek_model
        if settings.ai_provider == "deepseek"
        else settings.zhipu_model
        if settings.ai_provider == "zhipu"
        else settings.bailian_model
    )
    return settings.ai_provider, model


def _analysis_cache_key(snapshot: dict) -> str:
    provider, model = _configured_ai_identity()
    payload = {
        "job": snapshot.get("job"),
        "materials": snapshot.get("materials"),
        "provider": provider,
        "model": model,
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "formulaVersion": FORMULA_VERSION,
        "evidenceLevelVersion": EVIDENCE_LEVEL_VERSION,
        "externalAiConsent": snapshot.get("externalAiConsent", False),
        "usePreviousReport": snapshot.get("usePreviousReport", False),
        "previousReportId": snapshot.get("previousReportId"),
        "visualClaims": snapshot.get("visualClaims", []),
        "cacheVersion": "report-context-v8-actionable-evidence-gaps",
        "semanticEngine": (
            SEMANTIC_VERSION
            if settings.semantic_retrieval_enabled
            and model_available(settings.semantic_model_cache_dir)
            else None
        ),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _retrieval_step_detail(retrieval: dict) -> str:
    if retrieval.get("status") == "visual_excluded_from_rating":
        return "图片及OCR文字不进入代码实践评级；视觉描述单独保存，需对照原图核对"
    if retrieval.get("status") == "excluded_from_personal_rating":
        return (
            f"识别{retrieval.get('referenceFileCount', 0)}个第三方参考文件；"
            "可用于检索与学习建议，不计入个人实践评级"
        )
    if retrieval.get("engine") == SEMANTIC_VERSION:
        return (
            f"本地模型检索{retrieval.get('windowCount', 0)}段项目文档，"
            f"返回{retrieval.get('candidateCount', 0)}条低强度线索；不改变规则分数"
            if retrieval.get("status") == "active"
            else "本地语义模型不可用，已保留词法检索与规则报告"
        )
    if retrieval.get("engine") == "hybrid-lexical-v1":
        return (
            f"规则检测后补充{retrieval.get('candidateCount', 0)}条低强度候选原文；"
            "候选不改变规则分数，需经引用校验与模型判断"
        )
    if retrieval.get("sourceExact"):
        return (
            f"一次补取，{retrieval.get('expandedCount', 0)}条多行原文；"
            f"{retrieval.get('limitedCount', 0)}条仍为局部上下文；未执行上传代码"
        )
    return "上下文核验失败，已保留规则报告"


async def _daily_ai_budget(session: AsyncSession, user_id: UUID) -> tuple[bool, str | None, dict]:
    # Serialize external calls for the same account so concurrent tasks cannot
    # both pass the same daily budget snapshot before either usage row is saved.
    # Serialize this user's model budget without blocking notification FK checks
    # for the same recipient while a provider request is in flight.
    await session.scalar(select(User.id).where(User.id == user_id).with_for_update(key_share=True))
    local_now = datetime.now(timezone(timedelta(hours=8)))
    start_utc = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    row = (
        await session.execute(
            select(
                # One ledger row per real model request since B-08; a task with
                # several requests still counts as exactly one report.
                func.count(func.distinct(AiUsageLog.analysis_task_id)),
                func.coalesce(func.sum(AiUsageLog.input_tokens), 0),
                func.coalesce(func.sum(AiUsageLog.output_tokens), 0),
            )
            .join(AnalysisTask, AnalysisTask.id == AiUsageLog.analysis_task_id)
            .where(
                AnalysisTask.created_by == user_id,
                AiUsageLog.created_at >= start_utc,
            )
        )
    ).one()
    report_count, input_tokens, output_tokens = map(int, row)
    stats = {
        "reportCount": report_count,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
    }
    if report_count >= settings.ai_daily_report_limit:
        return False, "daily_report_limit", stats
    if (
        input_tokens + settings.ai_per_report_input_token_limit
        > settings.ai_daily_input_token_limit
    ):
        return False, "daily_input_token_limit", stats
    if (
        output_tokens + settings.ai_per_report_output_token_limit
        > settings.ai_daily_output_token_limit
    ):
        return False, "daily_output_token_limit", stats
    return True, None, stats


async def _shared_budget_display(session: AsyncSession, user_id: UUID) -> dict:
    """Advisory snapshot; atomic physical-request admission makes the decision."""
    budget = SharedBudgetService()
    capacity = await budget.capacity(session, user_id, day=budget.today())
    return {"reportCount": len(capacity.task_ids), "inputTokens": capacity.inputs,
            "outputTokens": capacity.outputs, "admissionMode": "shared_daily_v1",
            "tokenBasis": "capacity_actual_plus_unknown_bounds",
            "knownInputTokens": capacity.known_inputs, "knownOutputTokens": capacity.known_outputs,
            "heldInputBound": capacity.held_inputs, "heldOutputBound": capacity.held_outputs,
            "adjustedInputCapacity": capacity.adjusted_inputs,
            "adjustedOutputCapacity": capacity.adjusted_outputs,
            "unknownReservationCount": capacity.unknown_count}


class AnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.analysis = AnalysisRepository(session)

    async def create_match_task(
        self, request: MatchCreate, current_user: User, *, commit: bool = True
    ) -> TaskAccepted:
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
        if request.external_ai_consent and request.use_previous_report:
            from app.services.report_history import select_history_report_id

            snapshot["previousReportId"] = await select_history_report_id(
                self.session, current_user.id, job.id
            )
        from app.services.visual_evidence import visual_attachments

        snapshot["visualClaims"] = await visual_attachments(
            self.session, request.project_version_ids, current_user
        )
        cache_key = _analysis_cache_key(snapshot)
        snapshot["analysisCacheKey"] = cache_key
        cached_rows = await self.session.execute(
            select(AnalysisTask, MatchReport)
            .join(MatchReport, MatchReport.analysis_task_id == AnalysisTask.id)
            .where(
                AnalysisTask.created_by == current_user.id,
                AnalysisTask.status == TaskStatus.COMPLETED,
            )
            .order_by(MatchReport.created_at.desc())
            .limit(20)
        )
        for cached_task, cached_report in cached_rows.all():
            metadata = cached_report.analysis_metadata or {}
            if (
                metadata.get("analysisCacheKey") == cache_key
                and metadata.get("mode") == "ai_evidence"
                and not metadata.get("fallbackUsed")
            ):
                return TaskAccepted(task_id=cached_task.id, status=cached_task.status)
        task = AnalysisTask(
            created_by=current_user.id,
            task_type="job_match",
            input_snapshot=snapshot,
            status=TaskStatus.PENDING,
            progress=0,
            current_step="等待分析真实材料",
        )
        self.session.add(task)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return TaskAccepted(task_id=task.id, status=task.status)

    async def retry_match(self, task_id: UUID, user: User) -> TaskAccepted:
        # Growth attaches/analyzes under the same user lock. Do not let the
        # generic retry endpoint bypass its explicit reselect-and-save workflow.
        await self.session.scalar(select(User.id).where(User.id == user.id).with_for_update())
        original = await self.session.scalar(
            select(AnalysisTask)
            .where(AnalysisTask.id == task_id, AnalysisTask.created_by == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not original:
            raise AppError("分析任务不存在或无权访问", code=4041, status_code=404)
        growth = await self.session.scalar(
            select(EvidenceGrowthTask.id).where(EvidenceGrowthTask.analysis_task_id == task_id)
        )
        if original.input_snapshot.get("growthRequiresReselect") or growth:
            raise AppError(
                "补证分析失败记录需保留；请回到补证任务重新核对并保存材料与目标岗位后发起分析",
                code=4099, status_code=409,
            )
        task = await reset_failed_task(self.session, task_id, user)
        if task.task_type != "job_match" or not task.input_snapshot:
            raise AppError("旧任务未保存输入，请重新发起匹配", code=4094, status_code=409)
        await resolve_materials(self.session, MatchCreate.model_validate(task.input_snapshot), user)
        await self.session.commit()
        return TaskAccepted(task_id=task.id, status=task.status)

    async def get_task(self, task_id: UUID, user: User) -> AnalysisTaskView:
        task = await self.analysis.get_task(task_id)
        if not task or (task.created_by != user.id and user.role is not UserRole.ADMIN):
            raise AppError("分析任务不存在或无权访问", code=4041, status_code=404)
        if task.task_type == "application_verification":
            from app.services.application_verification import ensure_verification_task_access

            await ensure_verification_task_access(self.session, task, user)
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
        item_views = [self._item_view(item, evidence_by_id.get(item.evidence_id)) for item in items]
        return MatchReportView(
            **self.summary(report).model_dump(),
            materials=report.materials_snapshot,
            gaps=report.gaps,
            claimed_only=report.claimed_only,
            items=item_views,
            ai_usage=(report.analysis_metadata or {}).get("usage"),
            ai_tool_calls=(report.analysis_metadata or {}).get("modelToolCalls") or [],
            action_plan=build_action_plan(item_views),
            visual_claims=(report.analysis_metadata or {}).get("visualClaims", []),
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

    @staticmethod
    def _item_view(item: MatchItem, evidence: SkillEvidence | None = None) -> MatchItemView:
        from app.tools.evidence_levels import classify_evidence

        snapshot = item.evidence_snapshot or {}
        ai = snapshot.get("ai") or {}
        evidence_list = [
            CodeEvidenceView.model_validate(e) for e in snapshot.get("evidenceList", [])
        ]
        raw_task_plan = ai.get("taskPlan")
        task_plan = None
        task_plan_warning = None
        if raw_task_plan is not None:
            try:
                task_plan = CareerTaskPlan.model_validate(raw_task_plan)
                if task_plan_redundant_source_request(
                    task_plan.model_dump(mode="json", by_alias=True), evidence_list
                ):
                    task_plan_warning = "AI任务草稿重复要求提交已完整展示的源码，请重新核对。"
            except (TypeError, ValueError):
                task_plan_warning = "AI任务草稿格式无效，请重新核对原建议。"
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
            evidence_list=evidence_list,
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
            ai_task_plan=task_plan,
            ai_task_plan_warning=task_plan_warning,
            ai_suggestion_redundant=bool(
                ai.get("suggestion") and redundant_source_request(ai["suggestion"], evidence_list)
            ),
            ai_status=ai.get("status", "not_used"),
            ai_origin=ai.get("origin"),
            function_source_coverage=ai.get("functionSourceCoverage", []),
            file_source_coverage=ai.get("fileSourceCoverage", []),
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
        ledger = _DurableMatchingLedger()
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

            external_allowed = True
            external_skip_reason = None
            budget_stats = {"reportCount": 0, "inputTokens": 0, "outputTokens": 0}
            if settings.ai_external_enabled and settings.ai_provider != "mock":
                if not snapshot.get("externalAiConsent", False):
                    external_allowed = False
                    external_skip_reason = "consent_not_granted"
                else:
                    budget_stats = await _shared_budget_display(session, task.created_by)
            from app.services.report_history import prepare_history_tool

            history_loader = None
            if (external_allowed and snapshot.get("externalAiConsent", False)
                    and snapshot.get("usePreviousReport", False)):
                history_loader = await prepare_history_tool(
                    session,
                    task,
                    snapshot["job"]["requirements"],
                    session_factory=async_session_factory,
                )
            # The budget check locks the creator row inside this session.
            # Release the main session and its authorization transaction before
            # any external HTTP: the model call must never run while this
            # worker holds a borrowed database transaction open.
            await session.commit()
            observer_factory = _matching_observer_factory(
                async_session_factory, task_id, task.created_by, token, snapshot, ledger
            )
            workflow = await run_evidence_workflow(
                result,
                progress=model_progress,
                external_allowed=external_allowed,
                external_skip_reason=external_skip_reason,
                **({"history_loader": history_loader} if history_loader else {}),
                durable_observer_factory=observer_factory,
            )
            durable_summary = None
            if ledger.installed:
                try:
                    await _settle_durable_receipts(ledger)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Durable receipt settlement failed for task %s; "
                        "known usage may stay unbooked for reconciliation",
                        task_id,
                    )
                durable_summary = await ledger.active_service.summary()
            if workflow.retrieval_result is not None:
                result = workflow.retrieval_result
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
                        "本报告 AI 输入用量不足，正在保存规则报告"
                        if workflow.fallback_reason == "input_token_limit"
                        else "本报告 AI 输出用量不足，正在保存规则报告"
                        if workflow.fallback_reason == "output_token_limit"
                        else "外部模型不可用，正在保存规则报告"
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
            if durable_summary is not None:
                # Durable receipts replace in-memory sums for display. With no
                # trusted receipt there is no usage view at all — never a
                # fabricated zero total for an ambiguous physical request.
                usage = (
                    {
                        "input_tokens": durable_summary["inputTokens"],
                        "output_tokens": durable_summary["outputTokens"],
                        "cache_hit_tokens": durable_summary["cacheHitTokens"],
                        "latency_ms": durable_summary["latencyMs"],
                    }
                    if durable_summary["trustedReceiptCount"]
                    else None
                )
            analysis_metadata = {
                "mode": "ai_evidence" if workflow.analysis else "rules",
                "provider": workflow.provider if workflow.provider != "rules" else None,
                "model": workflow.model,
                "fallbackUsed": workflow.fallback_used,
                "fallbackReason": workflow.fallback_reason,
                "skippedReason": workflow.skipped_reason,
                "failureStage": workflow.failure_stage,
                "inputBudgetStop": workflow.input_budget_stop,
                "inputPreflights": list(workflow.input_preflights),
                "repairUsed": workflow.repaired,
                "requestCount": workflow.request_count,
                "planningSkippedReason": workflow.planning_skipped_reason,
                "jsonRepairCount": workflow.json_repair_count,
                "modelRequirementCount": workflow.model_requirement_count,
                "providerFinishReason": workflow.provider_finish_reason,
                "citationValidation": "passed" if workflow.analysis else "not_run",
                "usage": usage,
                "evidenceContextVersion": (
                    None if result.grounding_error else "source-context-v8-actionable-evidence-gaps"
                ),
                "retrievalSteps": result.retrieval_steps,
                "modelToolCalls": list(workflow.tool_calls),
                "promptVersion": EVIDENCE_PROMPT_VERSION,
                "analysisCacheKey": snapshot.get("analysisCacheKey"),
                "dailyBudgetBeforeRun": budget_stats,
                "visualClaims": snapshot.get("visualClaims", []),
                "privacy": {
                    "externalAiConsent": bool(snapshot.get("externalAiConsent", False)),
                    "directIdentifierRedaction": "email-phone-id-name-label-v2-python-annotations",
                    "candidateIdentitySent": False,
                    "rawFilesSent": False,
                },
            }
            if durable_summary is not None:
                # Durable accounting mode: report usage facts come from the
                # persisted attempt summary, and the legacy aggregate write
                # below stays off so the ledger stays the single source.
                analysis_metadata["usageKnown"] = durable_summary["usageKnown"]
                analysis_metadata["usageBooked"] = durable_summary["usageBooked"]
                analysis_metadata["attemptSummary"] = durable_summary
                # Logical workflow calls include rejected admission and omit
                # physical retries. Durable reports count persisted send intents;
                # an intent without a receipt remains ambiguous, never known zero.
                analysis_metadata["requestCount"] = durable_summary["intentCount"]
                # Fees are already settled independently. Fresh authorization
                # can prevent publication without erasing a physical receipt.
                await _authorize_matching_snapshot(
                    session, task_id, task.created_by, token, snapshot,
                )
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
            if usage_record and durable_summary is None:
                # Legacy accounting path only. Durable mode books each trusted
                # physical request through its attempt service instead.
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
                        confidence=(
                            item.rule_base_score if evidence.provenance == "portfolio" else 0
                        ),
                        verification_status=VerificationStatus.INFERRED,
                    )
                    session.add(record)
                    await session.flush()
                    if index == 0 and evidence.provenance == "portfolio":
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
                            "ruleClassificationVersion": EVIDENCE_LEVEL_VERSION,
                            "requirementTitle": item.requirement_title,
                            "skill": item.skill,
                            "claimed": item.claimed,
                            "claimText": item.claim_text,
                            "evidence": evidence_list[0] if strongest_id else None,
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
                                "taskPlan": (
                                    {
                                        "deliverable": ai_item.task_plan.deliverable,
                                        "steps": ai_item.task_plan.steps,
                                        "acceptanceChecks": ai_item.task_plan.acceptance_checks,
                                    }
                                    if ai_item and ai_item.task_plan else None
                                ),
                                "rating": (
                                    ai_item.rating.model_dump()
                                    if ai_item and ai_item.rating
                                    else None
                                ),
                                "ratingRubric": context.rating_rubric if context else None,
                                "fileSourceCoverage": [
                                    coverage.model_dump()
                                    for coverage in context.file_source_coverage
                                ] if context else [],
                                "functionSourceCoverage": [
                                    coverage.model_dump()
                                    for coverage in context.function_source_coverage
                                ] if context else [],
                            },
                        },
                    )
                )
            evidence_count = sum(len(item.evidence_list) for item in result.items)
            # An unknown durable request displays no total instead of a fake zero.
            absent_usage = None if durable_summary is not None else 0
            step_rows = [
                (
                    "核对材料版本",
                    f"读取{len(materials.snapshots)}份所选材料，报告固定到所选版本",
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
                        else "当前材料没有可引用证据，已跳过外部模型"
                        if workflow.skipped_reason == "no_evidence"
                        else "已达到当天 AI 用量上限，已保留本地规则报告"
                        if workflow.skipped_reason
                        in {
                            "daily_report_limit",
                            "daily_input_token_limit",
                            "daily_output_token_limit",
                        }
                        else "未获得外部 AI 授权，已保留本地规则报告"
                        if workflow.skipped_reason == "consent_not_granted"
                        else "模型服务繁忙，已保留本地规则报告"
                        if workflow.fallback_reason == "provider_busy"
                        else "本报告 AI 输入用量不足，已保留本地规则报告"
                        if workflow.fallback_reason == "input_token_limit"
                        else "本报告 AI 输出用量不足，已保留本地规则报告"
                        if workflow.fallback_reason == "output_token_limit"
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
                        "failureStage": workflow.failure_stage,
                        "inputBudgetStop": workflow.input_budget_stop,
                        "inputPreflights": list(workflow.input_preflights),
                        "skippedReason": workflow.skipped_reason,
                        "repairUsed": workflow.repaired,
                        "requestCount": analysis_metadata["requestCount"],
                        "planningSkippedReason": workflow.planning_skipped_reason,
                        "jsonRepairCount": workflow.json_repair_count,
                        "modelRequirementCount": workflow.model_requirement_count,
                        "providerFinishReason": workflow.provider_finish_reason,
                        "modelToolCalls": list(workflow.tool_calls),
                        "inputTokens": usage["input_tokens"] if usage else absent_usage,
                        "outputTokens": usage["output_tokens"] if usage else absent_usage,
                        "latencyMs": usage["latency_ms"] if usage else absent_usage,
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
                        _retrieval_step_detail(retrieval),
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
        except asyncio.CancelledError:
            # Cancellation still settles what the durable receipts already saw.
            # If teardown races the bounded booking, it keeps running detached
            # and its outcome is logged by the done callback.
            await session.rollback()
            if ledger.installed:
                try:
                    with suppress(asyncio.CancelledError):
                        await _settle_durable_receipts(ledger)
                except Exception:
                    logger.exception(
                        "Durable receipt settlement failed after cancellation for task %s; "
                        "preserving cancellation and recoverable receipt facts",
                        task_id,
                    )
            raise
        except Exception as exc:
            await session.rollback()
            logger.exception("Match task failed: %s", task_id)
            if ledger.installed:
                try:
                    await _settle_durable_receipts(ledger)
                except Exception:
                    logger.exception(
                        "Durable receipt settlement failed for failed task %s; "
                        "known usage may stay unbooked for reconciliation",
                        task_id,
                    )
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
