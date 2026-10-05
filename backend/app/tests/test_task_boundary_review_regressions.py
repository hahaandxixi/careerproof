"""Independent-review examples: keep legitimate plans and reject substitution."""

import pytest

from app.agents.contracts import (
    missing_cited_function_body_claim,
    runtime_plan_without_implementation_step,
)
from app.tools.task_boundaries import (
    conflicting_implementation_sources,
    task_boundary_error,
    unsupported_attribution,
)


@pytest.mark.parametrize("text", [
    "核对小组报告能否证明本人负责模块",
    "声称小组报告可证明本人贡献。此声明不作为事实，仅保留待核验。",
    "补充小组仓库中本人具名的提交记录作为个人贡献证明",
    "写明小组项目成果不能在缺少本人具名提交记录、模块分工表、时间戳与代码评审意见的验收流程中证明本人负责后端模块",
    "提交小组项目中本人具名提交记录作为个人贡献证明",
    "参考本人旧日志作为个人实践记录",
])
def test_review_legitimate_personal_or_pending_plans(text):
    assert not unsupported_attribution(text)


@pytest.mark.parametrize("text", [
    "将小组项目成果当作本人实践成果提交",
    "将参考实现视为本人实践成果",
    "将他人完成的导出模块计入个人实践成果",
    "将同学整理的接口文档视为本人接口能力证明",
    "小组报告作为本人贡献。其他声明待核验。",
])
def test_review_substitution_and_unrelated_disclaimer_rejected(text):
    assert unsupported_attribution(text)


@pytest.mark.parametrize("sources", [
    ["FastAPI未实现的部分已由本人补全，含过期分支。", "FastAPI已实现，支持过期与并发。"],
    ["导出功能尚未实现，2025年1月旧记录。", "导出功能已实现，支持CSV。"],
])
def test_explicit_historical_evolution_is_not_current_conflict(sources):
    assert not conflicting_implementation_sources(sources)


def test_pending_keywords_do_not_justify_selecting_a_conflicting_source():
    assert task_boundary_error(
        deliverable="导出功能冲突背景与归档说明",
        steps=["按已实现一侧归档导出结论，分别注明其余来源位置"],
        acceptance_checks=["版本差异后续待核验"],
        personal_source_texts=["导出功能已实现。", "导出功能尚未实现。"],
    ) is not None


@pytest.mark.parametrize("verb", ["补全", "补齐"])
def test_completion_before_execution_is_a_valid_implementation_step(verb):
    assert not runtime_plan_without_implementation_step(
        "FastAPI运行记录", [f"{verb}FastAPI过期分支实现后运行并记录输出"],
    )


def test_missing_body_claim_distinguishes_explicitly_different_function():
    assert not missing_cited_function_body_claim(
        "引用函数体已完整；仍不清楚相邻工具函数体是否包含参数校验"
    )
    assert missing_cited_function_body_claim("不清楚该函数体是否包含参数校验")
    assert missing_cited_function_body_claim(
        "不清楚相邻工具函数体是否有参数校验；无法确认当前函数体是否有过期分支"
    )
