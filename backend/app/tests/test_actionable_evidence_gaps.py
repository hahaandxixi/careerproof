import pytest

from app.agents.contracts import (
    AIRequirementAnalysis,
    EvidenceAnalysis,
    EvidenceCandidate,
    EvidenceTaskPlan,
    RequirementEvidenceContext,
    execution_plan_skips_explicitly_missing_implementation,
    validate_grounded_analysis,
)
from app.tests.test_function_coverage import analysis_for, entry, supplemented_context
from app.tools.function_coverage import (
    file_coverage,
    internal_rating_reason,
    redundant_source_request,
    task_plan_redundant_source_request,
)


def test_function_complete_is_not_file_complete_and_unknown_counts_stay_unknown():
    partial_file = entry(3, 5).model_copy(
        update={
            "function_line_start": 3,
            "function_line_end": 5,
            "source_line_count": 8,
        }
    )
    assert not file_coverage([partial_file])[0]["fully_covered"]
    assert not redundant_source_request("请提交该函数的完整文件，核对顶部导入。", [partial_file])
    assert redundant_source_request("请补充该函数的完整源码。", [partial_file])
    unknown = partial_file.model_copy(update={"source_line_count": None})
    assert file_coverage([unknown]) == []
    assert not redundant_source_request("请提交该函数的完整文件。", [unknown])


def test_file_union_counts_overlap_and_rejects_conflicting_counts_or_reference_fill():
    head = entry(1, 40).model_copy(update={"source_line_count": 45})
    tail = entry(6, 45, "R1-E2").model_copy(update={"source_line_count": 45})
    assert file_coverage([head, tail, head])[0]["covered_line_count"] == 45
    assert file_coverage([head, tail])[0]["fully_covered"]
    mismatch = tail.model_copy(update={"source_line_count": 46})
    assert file_coverage([head, mismatch]) == []
    reference = tail.model_copy(update={"provenance": "reference"})
    assert not file_coverage([head, reference])[0]["fully_covered"]
    another_version = tail.model_copy(update={"file_path": "future/app.py"})
    assert not any(row["fully_covered"] for row in file_coverage([head, another_version]))


def test_saved_task_plan_rechecks_every_text_field_against_visible_source():
    source = entry(1, 2).model_copy(
        update={
            "provenance": "portfolio",
            "source_line_count": 2,
            "function_line_start": 1,
            "function_line_end": 2,
        }
    )
    repeated = {
        "deliverable": "具名运行记录",
        "steps": ["再次提交该函数源码"],
        "acceptanceChecks": ["输出可定位"],
    }
    assert task_plan_redundant_source_request(repeated, [source])
    assert not task_plan_redundant_source_request(
        {
            "deliverable": "具名运行记录",
            "steps": ["运行接口并保存请求与响应"],
            "acceptanceChecks": ["响应状态与来源可定位"],
        },
        [source],
    )


def test_explicitly_unimplemented_skill_requires_implementation_before_runtime_plan():
    source = EvidenceCandidate(
        citation_id="R1-E1", file_path="README.md", line_start=1, line_end=2,
        evidence_type="retrieved_context", strength="low",
        snippet="Redis 未实现，当前只有缓存需求说明。",
    )
    context = RequirementEvidenceContext(
        requirement_id="redis-gap", requirement_title="实现 Redis 缓存读写并记录运行结果",
        skill="Redis", verdict="claimed_only", rule_score=0.1, claimed=True,
        evidence=[source],
    )
    runtime_only = EvidenceTaskPlan(
        deliverable="Redis 运行日志", steps=["执行缓存读写并保存输出"],
        acceptance_checks=["日志显示返回状态"],
    )
    implementation_first = EvidenceTaskPlan(
        deliverable="Redis 读写实现片段及运行记录",
        steps=["补充 Redis 客户端调用和读写处理代码", "运行后保存脱敏输出"],
        acceptance_checks=["实现与运行记录可对应"],
    )
    assert execution_plan_skips_explicitly_missing_implementation(context, runtime_only)
    assert not execution_plan_skips_explicitly_missing_implementation(
        context, implementation_first
    )

    def analysis(plan):
        return EvidenceAnalysis(
            summary="仅检查合成任务计划。", model="synthetic-probe",
            items=[AIRequirementAnalysis(
                requirement_id="redis-gap", explanation="材料明确说明 Redis 未实现。",
                citation_ids=[], information_gap="缺少缓存读写实现和运行结果。",
                suggestion="先补充读写实现，再核对运行结果。", task_plan=plan,
                confidence=0,
            )],
        )

    with pytest.raises(ValueError, match="execution before missing implementation"):
        validate_grounded_analysis([context], analysis(runtime_only))
    validate_grounded_analysis([context], analysis(implementation_first))

    historical = context.model_copy(update={
        "evidence": [source.model_copy(update={
            "snippet": "旧版 Redis 未实现；当前实现另见其他材料。",
        })],
    })
    assert not execution_plan_skips_explicitly_missing_implementation(
        historical, runtime_only
    )


@pytest.mark.parametrize(
    "suggestion",
    [
        "可提交该函数的完整文件与运行日志，核对store接口实现。",
        "请补充当前函数的完整源码，再核验运行。",
        "建议提供该文件的完整源码。",
    ],
)
def test_repeated_source_request_is_rejected_even_with_new_log_request(suggestion):
    _, context = supplemented_context()
    limited, answer = analysis_for(context, "依赖和运行记录待核验。")
    answer = answer.model_copy(
        update={"items": [answer.items[0].model_copy(update={"suggestion": suggestion})]}
    )
    with pytest.raises(ValueError, match="source already fully shown"):
        validate_grounded_analysis([limited], answer)


@pytest.mark.parametrize(
    "suggestion",
    [
        "请再次提交该函数源码，并核对运行记录。",
        "请重新上传当前函数实现代码。",
        "请重复提供该文件原文作为补证。",
    ],
)
def test_explicit_repeat_paraphrases_cannot_bypass_source_coverage(suggestion):
    _, context = supplemented_context()
    limited, answer = analysis_for(context, "依赖和运行记录待核验。")
    answer = answer.model_copy(
        update={"items": [answer.items[0].model_copy(update={"suggestion": suggestion})]}
    )
    with pytest.raises(ValueError, match="source already fully shown"):
        validate_grounded_analysis([limited], answer)


@pytest.mark.parametrize(
    "suggestion",
    [
        "请重新提交该函数源码的新版本，补上输入校验。",
        "请再次提供该函数代码的运行日志。",
        "请重新上传外部依赖函数源码，核验调用。",
    ],
)
def test_explicit_repeat_words_do_not_block_new_or_external_evidence(suggestion):
    _, context = supplemented_context()
    limited, answer = analysis_for(context, "依赖和运行记录待核验。")
    answer = answer.model_copy(
        update={"items": [answer.items[0].model_copy(update={"suggestion": suggestion})]}
    )
    validate_grounded_analysis([limited], answer)


def test_structured_task_draft_is_checked_against_visible_source_and_overclaims():
    _, context = supplemented_context()
    limited, answer = analysis_for(context, "运行结果和本人贡献待核验。")
    valid = EvidenceTaskPlan(
        deliverable="具名运行记录",
        steps=["运行合成接口并保存脱敏日志"],
        acceptance_checks=["日志与材料版本可对应"],
    )
    item = answer.items[0].model_copy(update={"task_plan": valid})
    validate_grounded_analysis([limited], answer.model_copy(update={"items": [item]}))

    repeated = valid.model_copy(update={"deliverable": "再次提交该函数源码"})
    with pytest.raises(ValueError, match="source already fully shown"):
        bad = item.model_copy(update={"task_plan": repeated})
        validate_grounded_analysis(
            [limited], answer.model_copy(update={"items": [bad]})
        )

    overclaimed = valid.model_copy(update={"acceptance_checks": ["测试已通过，证明具备能力"]})
    with pytest.raises(ValueError, match="unsupported ability or execution claim"):
        bad = item.model_copy(update={"task_plan": overclaimed})
        validate_grounded_analysis(
            [limited], answer.model_copy(update={"items": [bad]})
        )

    with pytest.raises(ValueError, match="omitted the evidence suggestion"):
        bad = item.model_copy(update={"suggestion": None})
        validate_grounded_analysis(
            [limited], answer.model_copy(update={"items": [bad]})
        )


@pytest.mark.parametrize(
    "suggestion",
    [
        "补充store实现文件与异常分支运行日志。",
        "提供该函数完整源码的运行记录。",
        "补充完整文件的提交历史，核验本人贡献。",
        "提供外部依赖函数的完整源码。",
        "补充该函数非空实现的验证材料。",
    "提交该函数完整文件的新版本，补上输入校验。",
    ],
)
def test_new_runtime_dependency_or_contribution_material_is_allowed(suggestion):
    _, context = supplemented_context()
    limited, answer = analysis_for(context, "依赖、运行和贡献待核验。")
    answer = answer.model_copy(
        update={"items": [answer.items[0].model_copy(update={"suggestion": suggestion})]}
    )
    validate_grounded_analysis([limited], answer)


@pytest.mark.parametrize(
    "text",
    [
        "完整任务实现仍受上限限制。",
        "由于rating_ceiling，只能给2级。",
        "context_complete为false。",
        "受评级上限限制。",
    ],
)
def test_internal_reason_cannot_replace_evidence_explanation(text):
    assert internal_rating_reason(text)
    _, context = supplemented_context()
    limited, answer = analysis_for(context, "依赖实现待核验。")
    answer = answer.model_copy(
        update={"items": [answer.items[0].model_copy(update={"explanation": text})]}
    )
    with pytest.raises(ValueError, match="implementation-only"):
        validate_grounded_analysis([limited], answer)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["repeat_source", "internal_reason"])
@pytest.mark.parametrize("repeat_error", [False, True])
async def test_actionable_gap_fault_repairs_once_or_preserves_rule_report(
    monkeypatch,
    fault,
    repeat_error,
):
    from app.agents.evidence_workflow import run_evidence_workflow
    from app.tests.test_directed_retrieval import (
        OfflinePlanner,
        enable_offline_planner,
        initial_result,
        long_file,
    )

    class RepairPlanner(OfflinePlanner):
        def __init__(self):
            super().__init__()
            self.answers = 0
            self.feedback = []

        async def analyze_evidence(self, *, contexts, **kwargs):
            self.answers += 1
            self.feedback.append(kwargs.get("validation_feedback"))
            answer = await super().analyze_evidence(contexts=contexts, **kwargs)
            item = answer.items[0]
            if repeat_error or self.answers == 1:
                if fault == "repeat_source":
                    item = item.model_copy(
                        update={
                            "suggestion": "可提交该函数的完整文件与运行日志。",
                            "citation_ids": [e.citation_id for e in contexts[0].evidence],
                        }
                    )
                else:
                    item = item.model_copy(
                        update={
                            "rating": item.rating.model_copy(
                                update={"reason": "当前评级受上限限制。"}
                            )
                        }
                    )
            return answer.model_copy(update={"items": [item]})

    provider = RepairPlanner()
    enable_offline_planner(monkeypatch, provider)
    result = initial_result(long_file())
    outcome = await run_evidence_workflow(result)
    assert provider.answers == 2 and provider.feedback[1]
    assert outcome.fallback_used == repeat_error
    assert outcome.retrieval_result.overall_score == result.overall_score
    if repeat_error:
        assert outcome.analysis is None
    else:
        assert outcome.repaired and outcome.analysis is not None


def test_omitting_a_citation_cannot_make_already_visible_file_missing():
    _, context = supplemented_context()
    limited, answer = analysis_for(context, "外部依赖与运行记录待核验。")
    answer = answer.model_copy(
        update={
            "items": [
                answer.items[0].model_copy(
                    update={
                        "citation_ids": [context.evidence[-1].citation_id],
                        "suggestion": "请提交该函数的完整文件。",
                    }
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="source already fully shown"):
        validate_grounded_analysis([limited], answer)
