"""Compare authorized report snapshots without inference or model calls."""

from uuid import UUID

from sqlalchemy import and_, or_, select

from app.core.exceptions import AppError
from app.models.analysis import AnalysisTask, MatchReport
from app.schemas.report_comparison import ComparisonItem, ReportComparison
from app.services.analysis import AnalysisService
from app.tools.function_coverage import (
    redundant_source_request,
    task_plan_redundant_source_request,
)


def evidence_key(evidence):
    path = evidence.file_path
    head, separator, tail = path.partition("/")
    try:
        UUID(head)
        path = tail if separator else path
    except ValueError:
        pass
    # The hash may cover a whole file; include exact content and location.
    # Citation numbers and material-version UUIDs are report-local identities.
    return (evidence.content_hash, path, evidence.line_start, evidence.line_end,
            evidence.snippet, evidence.provenance)


def interpretation(item):
    if not item:
        return None, None
    validated = item.ai_status == "validated"
    return (
        (getattr(item, "ai_explanation", None) if validated else None)
        or getattr(item, "explanation", None),
        (getattr(item, "ai_information_gap", None) if validated else None)
        or getattr(item, "evidence_level_gap", None),
    )


def task_plan_warning(item):
    if not item:
        return None
    warning = getattr(item, "ai_task_plan_warning", None)
    if warning:
        return warning
    plan = getattr(item, "ai_task_plan", None)
    if plan and task_plan_redundant_source_request(
        plan.model_dump(mode="json", by_alias=True), item.evidence_list
    ):
        return "AI任务草稿重复要求提交已完整展示的源码，请重新核对。"
    return None


def usable_advice(item):
    if (not item or item.ai_status != "validated"
            or getattr(item, "ai_suggestion_redundant", False)
            or item.confirmation_status in {"rejected", "corrected"}):
        return None, None
    suggestion = getattr(item, "ai_suggestion", None)
    if suggestion and redundant_source_request(suggestion, item.evidence_list):
        return None, None
    plan = (
        getattr(item, "ai_task_plan", None)
        if suggestion and not task_plan_warning(item)
        else None
    )
    return suggestion, plan


def compare_views(base, target, base_snapshot, target_snapshot, *, allow_job_change=False):
    if base.candidate_id != target.candidate_id or (
        base.job_id != target.job_id and not allow_job_change
    ):
        raise AppError("只能对比同一用户同一岗位的报告", code=4097, status_code=409)
    if base.id == target.id:
        raise AppError("请选择两份不同的报告", code=4097, status_code=409)
    context = []
    if base.job_id != target.job_id:
        context.append("job")
    old_materials = [m.model_dump(mode="json", by_alias=True) for m in base.materials]
    new_materials = [m.model_dump(mode="json", by_alias=True) for m in target.materials]
    material_key = lambda rows: sorted(  # noqa: E731
        (r["kind"], r["id"], r["contentHash"]) for r in rows
    )
    if material_key(old_materials) != material_key(new_materials):
        context.append("materials")
    old_req = {str(r["id"]): r for r in base_snapshot.get("requirements", [])}
    new_req = {str(r["id"]): r for r in target_snapshot.get("requirements", [])}
    if old_req != new_req:
        context.append("requirements")
    if base.evidence_context_version != target.evidence_context_version:
        context.append("retrieval_version")
    if (base.ai_model, base.analysis_mode, base.ai_fallback_used) != (
        target.ai_model, target.analysis_mode, target.ai_fallback_used
    ):
        context.append("model_or_mode")
    old_items = {item.requirement_id: item for item in base.items}
    new_items = {item.requirement_id: item for item in target.items}
    result = []
    for requirement_id in dict.fromkeys([*old_items, *new_items]):
        old = old_items.get(requirement_id)
        new = new_items.get(requirement_id)
        before = {evidence_key(e): e for e in old.evidence_list} if old else {}
        after = {evidence_key(e): e for e in new.evidence_list} if new else {}
        old_explanation, old_gap = interpretation(old)
        new_explanation, new_gap = interpretation(new)
        old_suggestion, old_plan = usable_advice(old)
        new_suggestion, new_plan = usable_advice(new)
        changes = []
        if old_req.get(str(requirement_id)) != new_req.get(str(requirement_id)):
            changes.append("requirement")
        if not old or not new:
            changes.append("item_added" if new else "item_removed")
        else:
            if (old.formula_version, old.evidence_level_version) != (
                new.formula_version, new.evidence_level_version
            ):
                changes.append("rule_version")
                if "rule_version" not in context:
                    context.append("rule_version")
            if (old.confirmation_status, old.reviewer_note) != (
                new.confirmation_status, new.reviewer_note
            ):
                changes.append("review")
            if old.ai_status != new.ai_status:
                changes.append("ai_status")
            if old.evidence_level != new.evidence_level:
                changes.append("level")
            if (old_explanation, old_gap) != (new_explanation, new_gap):
                changes.append("interpretation")
            if (old_suggestion, old_plan) != (new_suggestion, new_plan):
                changes.append("advice")
        if before.keys() != after.keys():
            changes.append("evidence")
        result.append(ComparisonItem(
            requirement_id=requirement_id, title=(new or old).requirement_title,
            status="added" if not old else "removed" if not new else "existing",
            base_requirement=old_req.get(str(requirement_id)),
            target_requirement=new_req.get(str(requirement_id)),
            base_level=old.evidence_level if old else None,
            target_level=new.evidence_level if new else None,
            base_ai_status=old.ai_status if old else None,
            target_ai_status=new.ai_status if new else None,
            base_review=old.confirmation_status if old else None,
            target_review=new.confirmation_status if new else None,
            base_explanation=old_explanation, target_explanation=new_explanation,
            base_information_gap=old_gap, target_information_gap=new_gap,
            base_suggestion=old_suggestion, target_suggestion=new_suggestion,
            base_task_plan_warning=task_plan_warning(old),
            target_task_plan_warning=task_plan_warning(new),
            base_task_plan=old_plan, target_task_plan=new_plan,
            added_evidence=[e for key, e in after.items() if key not in before],
            removed_evidence=[e for key, e in before.items() if key not in after],
            changes=changes,
        ))
    return ReportComparison(
        base_id=base.id, target_id=target.id, context_changes=context,
        base_job_id=base.job_id, target_job_id=target.job_id,
        base_job_title=getattr(base, "job_title", None),
        target_job_title=getattr(target, "job_title", None),
        base_materials=old_materials, target_materials=new_materials, items=result,
        limitations=[
            "变化标签只说明同时发生的变化，不证明等级变化的因果关系或本人能力提升。",
            "等级采用当前报告读取口径；部分历史规则等级未在生成时冻结。",
            "历史岗位快照可能缺少必要性字段；无法还原未保存的属性。",
            "复核状态是当前状态，不代表报告生成时的状态。",
            "引用减少仅表示目标报告未再展示，不代表原文件被删除。",
        ],
    )


async def compare_reports(session, base_id, target_id, user):
    service = AnalysisService(session)
    # Check both before exposing snapshots or even cross-report relationship.
    base = await service.get_report(base_id, user)
    target = await service.get_report(target_id, user)
    base_row = await session.get(MatchReport, base_id)
    target_row = await session.get(MatchReport, target_id)
    return compare_views(base, target, base_row.job_snapshot or {}, target_row.job_snapshot or {})


async def previous_comparison(session, target_id, user):
    service = AnalysisService(session)
    target = await service.get_report(target_id, user)
    row = await session.scalar(
        select(MatchReport)
        .join(AnalysisTask, AnalysisTask.id == MatchReport.analysis_task_id)
        .where(
            AnalysisTask.created_by == user.id,
            MatchReport.job_id == target.job_id,
            MatchReport.candidate_ref == target.candidate_id,
            or_(MatchReport.created_at < target.created_at,
                and_(MatchReport.created_at == target.created_at, MatchReport.id < target_id)),
        )
        .order_by(MatchReport.created_at.desc(), MatchReport.id.desc()).limit(1)
    )
    return await compare_reports(session, row.id, target_id, user) if row else None
