"""Student-private answer drafts; they never touch reports, deliveries or analysis inputs."""

from datetime import UTC
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.models.growth_answer import GrowthAnswerDraft
from app.schemas.analysis import MatchReportView, ReportMaterial
from app.schemas.growth_answer import AnswerDraftSave
from app.services.analysis import AnalysisService
from app.services.evidence_growth import EvidenceGrowthService

BOUNDARY = (
    "私人草稿仅本人可见；不会发送给企业、不进入投递快照，也不改变任务进度、评级或分析输入。"
    "引用只是你核对过的原文线索，复制使用前请先预览确认。"
)


class GrowthAnswerService:
    def __init__(self, session):
        self.session = session
        self._growth = EvidenceGrowthService(session)

    async def get(self, task_id, user):
        task = await self._growth._owned(task_id, user)
        draft = await self._draft(task.id)
        if draft is None:
            return None
        base_view = self._base_view(task)
        target_id, target_view = await self._validated_target(task, user)
        return self._view(task, draft, base_view, target_id, target_view)

    async def save(self, task_id, payload: AnswerDraftSave, user):
        # Parent-task lock order (User → growth) serializes first-create and updates.
        task = await self._growth._owned(task_id, user, lock=True)
        draft = await self._draft(task.id)
        if draft is None:
            if payload.expected_revision != 0:
                raise AppError(
                    "草稿尚不存在，首次保存需使用expectedRevision=0", code=4240, status_code=409
                )
        elif draft.revision != payload.expected_revision:
            raise AppError(
                "草稿已在其他保存中更新，请刷新读取最新版本后重试", code=4240, status_code=409
            )
        base_view = self._base_view(task)
        target_id, target_view = await self._validated_target(task, user)
        references = await self._validated_references(
            task, payload.references, base_view, target_id, target_view
        )
        if draft is None:
            draft = GrowthAnswerDraft(
                growth_task_id=task.id, text=payload.text, references=references
            )
            self.session.add(draft)
        else:
            draft.text = payload.text
            draft.references = references
            draft.revision += 1
        await self.session.commit()
        return self._view(task, draft, base_view, target_id, target_view)

    async def selectable_references(self, task_id, user):
        """Server-validated citation options for picking references before a draft exists.

        Baseline options come from the frozen task snapshot; the target report is
        listed only when its analysis completed AND it still passes the same
        consistency checks as EvidenceGrowthService.view with the task's original
        requirement present — a same-name skill on another job can never replace it.
        """
        task = await self._growth._owned(task_id, user)
        base_view = self._base_view(task)
        target_id, target_view = await self._validated_target(task, user)
        entries = []
        for kind, report_id, view in (
            ("base", task.base_report_id, base_view),
            ("target", target_id, target_view),
        ):
            report_item = None
            if report_id is not None and view is not None:
                report_item = next(
                    (i for i in view.items if i.requirement_id == task.requirement_id), None
                )
            if report_item is None:
                continue
            for evidence in report_item.evidence_list:
                if not evidence.citation_id:
                    continue
                entries.append(
                    {
                        "reportId": str(report_id),
                        "requirementId": str(task.requirement_id),
                        "citationId": evidence.citation_id,
                        "reportKind": kind,
                        "filePath": evidence.file_path,
                        "lineStart": evidence.line_start,
                        "lineEnd": evidence.line_end,
                        "provenance": evidence.provenance,
                    }
                )
        return entries

    async def _draft(self, task_id):
        return await self.session.scalar(
            select(GrowthAnswerDraft).where(GrowthAnswerDraft.growth_task_id == task_id)
        )

    def _base_view(self, task) -> MatchReportView | None:
        # Baseline citations validate against the frozen snapshot only.
        try:
            return MatchReportView.model_validate(task.base_snapshot["report"])
        except (ValidationError, KeyError):
            return None

    async def _validated_target(self, task, user):
        """Resolve the current completed target report with the same consistency
        checks as EvidenceGrowthService.view: owner authorization, the analysis
        input's fixed jobId, the report's own jobId and the frozen material
        selection must all still match this task. Any drift yields no valid
        target, so saved references degrade to unavailable instead of failing.
        """
        if not task.analysis_task_id:
            return None, None
        analysis = await self.session.get(AnalysisTask, task.analysis_task_id)
        if analysis is None or analysis.status != TaskStatus.COMPLETED:
            return None, None
        target = await self.session.scalar(
            select(MatchReport).where(MatchReport.analysis_task_id == task.analysis_task_id)
        )
        if target is None or target.id == task.base_report_id:
            return None, None
        target_job_id = self._target_job_id(task)
        if target_job_id is None:
            return None, None
        if (analysis.input_snapshot or {}).get("jobId") != str(target_job_id):
            return None, None
        try:
            view = await AnalysisService(self.session).get_report(target.id, user)
        except AppError:
            return None, None
        if view.job_id != target_job_id:
            return None, None
        if view.materials != [ReportMaterial.model_validate(m) for m in task.materials]:
            return None, None
        return target.id, view

    @staticmethod
    def _target_job_id(task) -> UUID | None:
        base_job_id = (task.base_snapshot.get("report") or {}).get("jobId")
        if task.target_job_id:
            return task.target_job_id
        return UUID(base_job_id) if base_job_id else None

    async def _validated_references(self, task, refs, base_view, target_id, target_view):
        seen = set()
        views: dict[UUID, MatchReportView | None] = {}
        for item in refs:
            key = (str(item.report_id), str(item.requirement_id), item.citation_id)
            if key in seen:
                raise AppError("引用存在重复条目，请合并后提交", code=4241, status_code=422)
            seen.add(key)
            if item.requirement_id != task.requirement_id:
                raise AppError(
                    "引用要求必须与补证任务的原要求一致", code=4241, status_code=422
                )
            if item.report_id != task.base_report_id and item.report_id != target_id:
                raise AppError(
                    "只能引用本任务的基准报告或当前已完成的对照报告", code=4241, status_code=422
                )
            if item.report_id not in views:
                views[item.report_id] = (
                    target_view if item.report_id == target_id else base_view
                )
            view = views[item.report_id]
            if view is None:
                raise AppError("引用的报告当前不可用", code=4241, status_code=422)
            report_item = next(
                (i for i in view.items if i.requirement_id == task.requirement_id), None
            )
            if report_item is None:
                raise AppError("所选报告不包含本任务的原要求", code=4241, status_code=422)
            if not any(e.citation_id == item.citation_id for e in report_item.evidence_list):
                raise AppError(
                    "引用编号不在该要求已核验的证据列表中，请从报告中选择真实条目",
                    code=4241,
                    status_code=422,
                )
        return [
            {
                "reportId": str(item.report_id),
                "requirementId": str(item.requirement_id),
                "citationId": item.citation_id,
            }
            for item in refs
        ]

    def _view(self, task, draft, base_view, target_id, target_view):
        views: dict[UUID, MatchReportView | None] = {}
        references = []
        for ref in draft.references:
            entry = {
                "reportId": ref["reportId"],
                "requirementId": ref["requirementId"],
                "citationId": ref["citationId"],
                "available": False,
                "snippet": None,
                "filePath": None,
                "lineStart": None,
                "lineEnd": None,
                "provenance": None,
            }
            report_id = UUID(ref["reportId"])
            if report_id in {task.base_report_id, target_id}:
                if report_id not in views:
                    views[report_id] = (
                        target_view if report_id == target_id else base_view
                    )
                view = views[report_id]
                report_item = None
                if view is not None:
                    report_item = next(
                        (
                            i
                            for i in view.items
                            if str(i.requirement_id) == ref["requirementId"]
                        ),
                        None,
                    )
                evidence = None
                if report_item is not None:
                    evidence = next(
                        (
                            e
                            for e in report_item.evidence_list
                            if e.citation_id == ref["citationId"]
                        ),
                        None,
                    )
                if evidence is not None:
                    entry.update(
                        available=True,
                        snippet=evidence.snippet,
                        filePath=evidence.file_path,
                        lineStart=evidence.line_start,
                        lineEnd=evidence.line_end,
                        provenance=evidence.provenance,
                    )
            references.append(entry)
        updated_at = draft.updated_at
        if updated_at.tzinfo is None:  # SQLite drops tzinfo on reload; wall time is UTC.
            updated_at = updated_at.replace(tzinfo=UTC)
        return {
            "taskId": str(task.id),
            "requirementId": str(task.requirement_id),
            "text": draft.text,
            "references": references,
            "revision": draft.revision,
            "updatedAt": updated_at.isoformat(),
            "boundary": BOUNDARY,
        }
