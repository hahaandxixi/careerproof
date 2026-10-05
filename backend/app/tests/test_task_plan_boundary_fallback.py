"""Workflow regressions: an invalid task plan must never be stored.

Offline only. Providers are in-process synthetic fakes returning authored
analyses; no network, no database, no browser, no real model. The boundary
guards live in contracts/task_boundaries; here the regression is the workflow
behavior: reject the plan, attempt the single named repair round, and when the
repair still violates the boundary, degrade to the rule result with
``analysis=None`` so no invalid plan can reach a storable report.
"""

from uuid import uuid4

import pytest

from app.agents.contracts import (
    AIRating,
    AIRequirementAnalysis,
    CriterionDecision,
    EvidenceAnalysis,
    EvidenceTaskPlan,
    ModelUsage,
)
from app.agents.evidence_workflow import run_evidence_workflow
from app.core.config import settings
from app.tests.test_directed_retrieval import OfflinePlanner, enable_offline_planner
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume

# Authored fixtures mirroring the case-library boundary families; the invalid
# plans are the negative drafts, the valid ones keep the explicit refusal /
# pending-verification / future-supplement boundary wording.
INVALID_GROUP_PLAN = {
    "deliverable": "小组报告个人贡献证明",
    "steps": ["直接提交小组项目报告作为个人贡献"],
    "acceptance_checks": ["小组报告可证明本人负责后端模块"],
}
VALID_GROUP_PLAN = {
    "deliverable": "个人负责模块的提交与边界说明",
    "steps": ["列出本人提交的模块文件与对应提交记录", "标注与他人协作部分的接口边界"],
    "acceptance_checks": ["每项职责可对应到具名提交", "协作边界有双方确认记录"],
}
INVALID_CONFLICT_PLAN = {
    "deliverable": "导出功能验收说明",
    "steps": ["按导出功能说明归档结论"],
    "acceptance_checks": ["导出功能按已实现归档"],
}
VALID_CONFLICT_PLAN = {
    "deliverable": "冲突材料核验记录",
    "steps": [
        "并列两处陈述的出处与行号",
        "将结论状态标记为待核验",
        "分别核实来源后再更新结论",
    ],
    "acceptance_checks": ["结论前保留冲突待核验标记", "不单独采信任一来源"],
}


def fastapi_result():
    return match_candidate(
        [RequirementInput(uuid4(), "有 FastAPI 接口开发实践", "FastAPI", 5)],
        parse_resume("熟悉 FastAPI"),
        [
            ProjectFileSnapshot(
                "app.py",
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                '@app.get("/health")\n'
                "def health(): pass",
            )
        ],
    )


def conflicting_export_result():
    # Two same-subject implementation-state statements that contradict.
    return match_candidate(
        [RequirementInput(uuid4(), "核实导出功能的实现状态并说明依据", "Python", 5)],
        parse_resume("负责 Python 后端的导出模块。"),
        [
            ProjectFileSnapshot(
                "docs/export.md",
                "# 导出功能说明\n\n导出功能已实现，支持 CSV 格式。\n",
            ),
            ProjectFileSnapshot(
                "docs/known-issues.md",
                "# 已知问题\n\n导出功能尚未实现，页面按钮为占位。\n等待下一版本处理。\n",
            ),
        ],
    )


def authored_analysis(context, plan: dict) -> EvidenceAnalysis:
    citations = (
        [source.citation_id for source in context.evidence if source.provenance == "portfolio"]
        if context.verdict in {"supported", "partial"}
        else []
    )
    return EvidenceAnalysis(
        summary="离线合成输出，仅用于契约与降级回归，不是模型结果。",
        model="synthetic",
        usage=ModelUsage(input_tokens=10, output_tokens=20),
        items=[
            AIRequirementAnalysis(
                requirement_id=context.requirement_id,
                explanation="材料只含来源陈述，结论与运行结果待核验。",
                citation_ids=citations,
                information_gap="执行结果与本人贡献待核验。",
                suggestion="补充可核验记录后人工核对。",
                confidence=0,
                task_plan=EvidenceTaskPlan(**plan),
                # Neutral rubric rating, mirroring the runner's draft_probe
                # envelope: the guard is not a semantic opinion about the plan.
                rating=AIRating(
                    level=None,
                    reason="仅为草稿契约检查，不作语义评级。",
                    criteria=[
                        CriterionDecision(
                            criterion=key, supported=False, citation_ids=[],
                            reason="草稿契约检查未作语义评级。",
                        )
                        for key in ("relevance", "operation", "task")
                    ],
                ),
            )
        ],
    )


class BoundaryPlanProvider(OfflinePlanner):
    """Synthetic OpenAI-compatible provider emitting authored task plans."""

    def __init__(self, plans: list[dict]):
        super().__init__()
        self.plans = plans
        self.calls = 0
        self.feedback: list[str | None] = []

    async def plan_evidence_retrieval(self, *, contexts, **kwargs):
        return None

    async def analyze_evidence(self, *, contexts, **kwargs):
        self.calls += 1
        self.feedback.append(kwargs.get("validation_feedback"))
        return authored_analysis(contexts[0], self.plans[min(self.calls, len(self.plans)) - 1])


def analysis_json(outcome) -> str:
    return outcome.analysis.model_dump_json() if outcome.analysis else ""


@pytest.mark.asyncio
async def test_invalid_task_plan_falls_back_and_is_not_stored(monkeypatch) -> None:
    seen = []

    class Provider:
        name = "synthetic"

        async def analyze_evidence(self, *, contexts):
            seen.append(contexts)
            return authored_analysis(contexts[0], INVALID_GROUP_PLAN)

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", Provider)

    outcome = await run_evidence_workflow(fastapi_result())

    assert len(seen) == 1 and seen[0][0].evidence
    assert outcome.fallback_used is True
    # Safe degradation: no analysis object survives, so the invalid plan cannot
    # reach any storable report; the rule evidence stays intact.
    assert outcome.analysis is None
    assert outcome.failure_stage == "validation"
    assert outcome.fallback_reason == "invalid_output_or_config"
    assert outcome.repaired is False
    assert outcome.request_count == 1
    assert outcome.contexts[0].evidence
    # The only place a task plan could be stored is the analysis; it is None.
    assert outcome.analysis is None
    assert analysis_json(outcome) == ""


@pytest.mark.asyncio
async def test_valid_personal_boundary_plan_is_kept(monkeypatch) -> None:
    class Provider:
        name = "synthetic"

        async def analyze_evidence(self, *, contexts):
            return authored_analysis(contexts[0], VALID_GROUP_PLAN)

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", Provider)

    outcome = await run_evidence_workflow(fastapi_result())

    assert outcome.fallback_used is False and outcome.repaired is False
    assert outcome.analysis is not None
    plan = outcome.analysis.items[0].task_plan
    assert plan.deliverable == "个人负责模块的提交与边界说明"
    assert plan.steps == VALID_GROUP_PLAN["steps"]


@pytest.mark.asyncio
async def test_boundary_plan_repair_still_invalid_falls_back_without_storing(monkeypatch) -> None:
    provider = BoundaryPlanProvider([INVALID_CONFLICT_PLAN, INVALID_CONFLICT_PLAN])
    enable_offline_planner(monkeypatch, provider)

    outcome = await run_evidence_workflow(conflicting_export_result())

    assert provider.calls == 2
    assert provider.feedback[0] is None
    # The repair round received the named boundary error as feedback.
    assert "omits unresolved implementation-source conflict" in provider.feedback[1]
    assert outcome.fallback_used is True
    assert outcome.analysis is None
    assert outcome.failure_stage == "repair"
    assert outcome.repaired is False
    assert outcome.request_count == 2
    assert outcome.contexts[0].evidence
    assert analysis_json(outcome) == ""


@pytest.mark.asyncio
async def test_boundary_plan_repair_accepts_pending_verification_plan(monkeypatch) -> None:
    provider = BoundaryPlanProvider([INVALID_CONFLICT_PLAN, VALID_CONFLICT_PLAN])
    enable_offline_planner(monkeypatch, provider)

    outcome = await run_evidence_workflow(conflicting_export_result())

    assert provider.calls == 2
    assert outcome.fallback_used is False
    assert outcome.repaired is True
    assert outcome.analysis is not None
    plan = outcome.analysis.items[0].task_plan
    assert plan.deliverable == "冲突材料核验记录"
    assert any("待核验" in step for step in plan.steps)
    assert any("并列" in step for step in plan.steps)


@pytest.mark.asyncio
async def test_boundary_plan_first_shot_valid_needs_no_repair(monkeypatch) -> None:
    provider = BoundaryPlanProvider([VALID_CONFLICT_PLAN])
    enable_offline_planner(monkeypatch, provider)

    outcome = await run_evidence_workflow(conflicting_export_result())

    assert provider.calls == 1
    assert outcome.fallback_used is False and outcome.repaired is False
    assert outcome.analysis is not None
    assert outcome.analysis.items[0].task_plan.acceptance_checks == [
        "结论前保留冲突待核验标记", "不单独采信任一来源",
    ]
