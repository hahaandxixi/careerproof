"""Narrow visible-code conflict guards, not a semantic accuracy score."""

import copy

import pytest

from app.schemas.analysis import CareerPlanAnalysis, JobRecommendationView
from app.services.career_planning import _planning_input, validate_plan
from app.tools.visible_checks import (
    VisibleCodeFactConflict,
    conflicts_with_visible_checks,
    parameter_error_fact,
    visible_code_facts,
)
from evals.verify_two_sided_api import CODE


@pytest.mark.parametrize(
    "source,expected",
    [
        (CODE, True),
        ("def f(name):\n    if not name: raise HTTPException(status_code=422)\n", True),
        ('async def f(name):\n    if name == "": raise fastapi.HTTPException(400)\n', True),
        ("def f(name):\n    pass\n", False),
        ('def f(name):\n    return "if not name: raise HTTPException(400)"\n', False),
        ("def f(name):\n    if cache: raise HTTPException(400)\n", False),
        ("def f(name):\n    if not name: raise HTTPException(200)\n", False),
        ("def f(name):\n    if not name: raise HTTPException(ERROR_STATUS)\n", False),
        ('@app.get("/health")', False),
    ],
)
def test_only_bounded_parameter_error_syntax_is_reported(source, expected):
    assert parameter_error_fact(source) is expected


@pytest.mark.parametrize(
    "text,conflict",
    [
        ("输入校验与错误响应、接口测试及运行记录在材料中尚未展示。", True),
        ("材料中未展示输入校验。", True),
        ("缺少错误响应代码。", True),
        ("看不到输入校验。", True),
        ("代码中输入校验缺失。", True),
        ("尚未展示完整的输入校验与错误响应实现。", False),
        ("输入校验的测试代码和运行记录未展示。", False),
        ("未展示输入校验的运行记录。", False),
        ("输入校验的测试代码缺失。", False),
        ("异常处理的运行记录缺失。", False),
        ("参数校验是否覆盖全部边界仍待核验。", False),
        ("无法确认输入校验覆盖全部边界。", False),
        ("不能说输入校验未展示。", False),
        ("已见参数判断，其他异常覆盖仍待核验。", False),
        ("其余参数校验未展示。", False),
        ("本片段之外的输入校验未展示。", False),
        # Known narrow boundary: bare 无 is ambiguous (无法/无论/并非无) and is
        # deliberately not treated as a visibility negative.
        ("该函数无输入校验。", False),
    ],
)
def test_missing_wording_distinguishes_code_from_coverage_and_execution(text, conflict):
    facts = [{"kind": "parameter_error_branch"}]
    assert conflicts_with_visible_checks(text, facts) is conflict
    assert not conflicts_with_visible_checks(text, [])


def job_fixture():
    return JobRecommendationView(
        job_id="12345678-1234-4321-8765-abcdef123456",
        job_title="合成岗位",
        company_name="合成企业",
        category="software",
        city="深圳",
        employment_type="internship",
        priority="medium",
        assessed_count=1,
        requirement_count=1,
        supported_count=1,
        claimed_count=0,
        evidence=[
            {
                "citation_id": "J1-E1",
                "skill": "FastAPI",
                "file_path": "version/app.py",
                "line_start": 1,
                "line_end": len(CODE.splitlines()),
                "strength": "medium",
                "explanation": "可见代码",
                "snippet": CODE,
            }
        ],
    )


@pytest.mark.parametrize("field", ["comparison", "reason", "key_gap", "next_task", "task_steps"])
def test_plan_rejects_known_visible_fact_conflict_in_each_output_field(field):
    job = job_fixture()
    analysis = CareerPlanAnalysis.model_validate(
        {
            "comparison": "已见参数判断与HTTPException，实际运行仍待核验。",
            "focusJobId": str(job.job_id),
            "advice": [
                {
                    "jobId": str(job.job_id),
                    "reason": "片段包含条件判断与异常声明。",
                    "keyGap": "运行与完整覆盖仍需核验。",
                    "nextTask": "提交正常和异常请求运行记录。",
                    "citationIds": ["J1-E1"],
                    "taskPlan": {
                        "deliverable": "运行记录",
                        "steps": ["记录请求与响应"],
                        "acceptanceChecks": ["记录含请求与响应"],
                    },
                }
            ],
        }
    )
    validate_plan(analysis, [job])
    conflict = "输入校验与错误响应、接口测试及运行记录尚未展示。"
    if field == "comparison":
        analysis.comparison = conflict
    elif field == "task_steps":
        analysis.advice[0].task_plan.steps = [conflict]
    else:
        setattr(analysis.advice[0], field, conflict)
    with pytest.raises(VisibleCodeFactConflict):
        validate_plan(analysis, [job])


def test_fact_context_keeps_current_citations_and_original_source():
    job = job_fixture()
    original = copy.deepcopy(job.model_dump())
    facts = visible_code_facts(job)
    assert len(facts) == 1 and facts[0]["citationIds"] == ["J1-E1"]
    assert _planning_input([job], [])["jobs"][0]["visibleCodeFacts"] == facts
    assert job.model_dump() == original
