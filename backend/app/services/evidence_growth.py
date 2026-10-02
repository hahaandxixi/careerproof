"""Student-owned evidence workflow; never updates a submitted application."""

from sqlalchemy import select

from app.agents.provider import redact_external_text
from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus, UserRole
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.identity import StudentProfile, User
from app.models.recruitment import Application
from app.schemas.analysis import MatchCreate, MatchReportView, ReportMaterial
from app.services.action_plan import build_action_plan
from app.services.analysis import AnalysisService
from app.services.applications import reply_context_for_requirement
from app.services.matching_materials import resolve_materials
from app.services.report_comparison import compare_views, task_plan_warning
from app.tools.function_coverage import redundant_source_request


def material_key(rows):
    # Identical content in a new version is not evidence of a material change.
    return sorted((m["kind"], m["contentHash"], m.get("materialRole") or "") for m in rows)


class EvidenceGrowthService:
    def __init__(self, session):
        self.session = session

    async def _student(self, user, lock=False):
        if user.role != UserRole.STUDENT:
            raise AppError("请使用学生账号管理本人补证任务", code=4037, status_code=403)
        if lock:
            await self.session.scalar(select(User.id).where(User.id == user.id).with_for_update())

    async def _owned(self, task_id, user, lock=False):
        await self._student(user, lock)
        statement = select(EvidenceGrowthTask).where(
            EvidenceGrowthTask.id == task_id, EvidenceGrowthTask.created_by == user.id
        )
        if lock:
            statement = statement.with_for_update()
        row = await self.session.scalar(statement)
        if not row:
            raise AppError("补证任务不存在或无权访问", code=4049, status_code=404)
        return row

    async def create(self, report_id, payload, user):
        await self._student(user, True)
        report = await AnalysisService(self.session).get_report(report_id, user)
        requirement = next(
            (i for i in report.items if i.requirement_id == payload.requirement_id), None
        )
        if not requirement:
            raise AppError("原报告中不存在该要求", code=4047, status_code=404)
        existing = await self.session.scalar(
            select(EvidenceGrowthTask).where(
                EvidenceGrowthTask.created_by == user.id,
                EvidenceGrowthTask.base_report_id == report_id,
                EvidenceGrowthTask.requirement_id == payload.requirement_id,
            )
        )
        if existing:
            return await self.view(existing, user)
        report_row = await self.session.get(MatchReport, report_id)
        plan = payload.model_dump(mode="json", by_alias=True)
        plan["deliverable"] = redact_external_text(plan["deliverable"])
        for key in ("steps", "acceptanceChecks"):
            plan[key] = [redact_external_text(text) for text in plan[key]]
        row = EvidenceGrowthTask(
            created_by=user.id,
            base_report_id=report_id,
            requirement_id=payload.requirement_id,
            base_snapshot={
                "report": report.model_dump(mode="json", by_alias=True),
                "job": report_row.job_snapshot or {},
            },
            plan=plan,
            materials=[],
            status="planned",
        )
        self.session.add(row)
        await self.session.commit()
        return await self.view(row, user)

    async def existing(self, report_id, requirement_id, user):
        await self._student(user)
        report = await AnalysisService(self.session).get_report(report_id, user)
        if not any(i.requirement_id == requirement_id for i in report.items):
            raise AppError("原报告中不存在该要求", code=4047, status_code=404)
        row = await self.session.scalar(
            select(EvidenceGrowthTask).where(
                EvidenceGrowthTask.created_by == user.id,
                EvidenceGrowthTask.base_report_id == report_id,
                EvidenceGrowthTask.requirement_id == requirement_id,
            )
        )
        return await self.view(row, user) if row else None

    async def get(self, task_id, user):
        return await self.view(await self._owned(task_id, user), user)

    async def enterprise_reply(self, report_id, requirement_id, user):
        await self._student(user)
        report = await AnalysisService(self.session).get_report(report_id, user)
        if not any(item.requirement_id == requirement_id for item in report.items):
            raise AppError("原报告中不存在该要求", code=4047, status_code=404)
        return await self._enterprise_reply(report_id, requirement_id, user)

    async def _enterprise_reply(self, report_id, requirement_id, user):
        application = await self.session.scalar(
            select(Application)
            .join(StudentProfile, Application.student_id == StudentProfile.id)
            .where(
                StudentProfile.user_id == user.id,
                Application.report_id == report_id,
                Application.consent_at.is_not(None),
                Application.reply_text.is_not(None),
            )
        )
        return reply_context_for_requirement(application, requirement_id) if application else None

    async def list(self, user):
        await self._student(user)
        rows = await self.session.scalars(
            select(EvidenceGrowthTask)
            .where(EvidenceGrowthTask.created_by == user.id)
            .order_by(EvidenceGrowthTask.created_at.desc(), EvidenceGrowthTask.id.desc())
            .limit(100)
        )
        return [await self.view(row, user) for row in rows]

    async def attach(self, task_id, payload, user):
        row = await self._owned(task_id, user, True)
        if row.analysis_task_id:
            analysis = await self.session.get(AnalysisTask, row.analysis_task_id)
            if analysis.status not in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
                raise AppError(
                    "分析已开始，材料选择已固定；请保留结果并从新报告创建后续任务",
                    code=4099,
                    status_code=409,
                )
        materials = await resolve_materials(self.session, payload, user)
        if material_key(materials.snapshots) == material_key(
            row.base_snapshot["report"]["materials"]
        ):
            raise AppError(
                "所选材料与基准内容相同，请补充新版或明确调整证据范围", code=4099, status_code=409
            )
        row.materials = materials.snapshots
        row.analysis_task_id = None
        row.status = "materials_selected"
        await self.session.commit()
        return await self.view(row, user)

    async def analyze(self, task_id, payload, user):
        row = await self._owned(task_id, user, True)
        if row.analysis_task_id:
            analysis = await AnalysisService(self.session).get_task(row.analysis_task_id, user)
            if analysis.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
                raise AppError(
                    "此前分析失败已保留。请重新核对并保存材料后再发起，不自动重试",
                    code=4099,
                    status_code=409,
                )
            return await self.view(row, user)
        if not row.materials:
            raise AppError("请先保存已解析完成的补证材料版本", code=4099, status_code=409)
        resume = next(m for m in row.materials if m["kind"] == "resume")
        request = MatchCreate(
            job_id=row.base_snapshot["report"]["jobId"],
            resume_version_id=resume["id"],
            project_version_ids=[m["id"] for m in row.materials if m["kind"] == "project"],
            external_ai_consent=payload.external_ai_consent,
            use_previous_report=False,
        )
        current = await resolve_materials(self.session, request, user)
        if current.snapshots != row.materials:
            raise AppError("保存后的材料依据发生变化，请重新核对版本", code=4099, status_code=409)
        accepted = await AnalysisService(self.session).create_match_task(
            request, user, commit=False
        )
        row.analysis_task_id = accepted.task_id
        row.status = "analyzing"
        await self.session.commit()
        return await self.view(row, user)

    async def view(self, row, user):
        base = MatchReportView.model_validate(row.base_snapshot["report"])
        requirement = next(i for i in base.items if i.requirement_id == row.requirement_id)
        action = build_action_plan([requirement], limit=1)[0]
        action_needs_recheck = bool(
            action.source == "ai_suggestion"
            and requirement.ai_suggestion
            and redundant_source_request(requirement.ai_suggestion, requirement.evidence_list)
        )
        plan_warning = task_plan_warning(requirement)
        task_plan_needs_recheck = bool(plan_warning)
        action_needs_recheck = action_needs_recheck or task_plan_needs_recheck
        status, target_id, analysis_status, comparison, analysis_error = (
            row.status,
            None,
            None,
            None,
            None,
        )
        if row.analysis_task_id:
            task = await AnalysisService(self.session).get_task(row.analysis_task_id, user)
            analysis_status = task.status.value
            if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
                status = "analysis_failed"
                analysis_error = "本次分析失败或已取消，记录保留；请核对材料及处理记录。"
            elif task.status == TaskStatus.COMPLETED:
                target = await self.session.scalar(
                    select(MatchReport).where(MatchReport.analysis_task_id == row.analysis_task_id)
                )
                if target:
                    view = await AnalysisService(self.session).get_report(target.id, user)
                    if view.id == base.id or view.materials != [
                        ReportMaterial.model_validate(m) for m in row.materials
                    ]:
                        raise AppError("新报告与本次补证版本不一致", code=4099, status_code=409)
                    comparison = compare_views(
                        base, view, row.base_snapshot["job"], target.job_snapshot or {}
                    )
                    comparison.limitations[3] = (
                        "基准是创建补证任务时固定的复核状态；目标报告采用当前复核状态。"
                    )
                    target_id, status = str(target.id), "compared"
        return {
            "id": str(row.id),
            "baseReportId": str(row.base_report_id),
            "jobId": str(base.job_id),
            "jobTitle": base.job_title,
            "requirementId": str(row.requirement_id),
            "requirementTitle": requirement.requirement_title,
            "gap": action.evidence_gap,
            "originalAction": action.action,
            "actionSource": action.source,
            "actionCitationIds": action.citation_ids,
            "actionNeedsRecheck": action_needs_recheck,
            "taskPlanNeedsRecheck": task_plan_needs_recheck,
            "taskPlanWarning": plan_warning,
            "enterpriseReply": await self._enterprise_reply(
                row.base_report_id, row.requirement_id, user
            ),
            "plan": row.plan,
            "baseMaterials": row.base_snapshot["report"]["materials"],
            "materials": row.materials,
            "status": status,
            "analysisTaskId": str(row.analysis_task_id) if row.analysis_task_id else None,
            "analysisStatus": analysis_status,
            "analysisError": analysis_error,
            "targetReportId": target_id,
            "comparison": comparison.model_dump(mode="json", by_alias=True) if comparison else None,
            "createdAt": row.created_at.isoformat(),
            "boundary": (
                "任务进度不代表能力通过；新报告不更新企业已收到的投递快照。"
                "变化不证明能力提升或本人贡献。"
            ),
        }
