import json
from dataclasses import replace

import pytest

from app.agents.contracts import AIRequirementAnalysis, EvidenceAnalysis, validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts, execute_retrieval_tool
from app.agents.provider import evidence_analysis_messages
from app.tests.test_directed_retrieval import initial_result, long_file
from app.tools.function_coverage import function_coverage, missing_function_context_claim


def entry(start, end, citation="R1-E1", path="version/app.py", **extra):
    from app.agents.contracts import EvidenceCandidate

    return EvidenceCandidate(
        citation_id=citation,
        file_path=path,
        line_start=start,
        line_end=end,
        snippet="source",
        evidence_type="retrieved_context",
        strength="low",
        function_line_start=1,
        function_line_end=45,
        **extra,
    )


def test_ranges_union_without_duplicate_inflation_and_with_real_gaps():
    first = entry(1, 40)
    tail = entry(6, 45, "R1-E2")
    coverage = function_coverage([first, tail])[0]
    assert coverage["covered_line_count"] == 45 and coverage["fully_covered"]
    assert coverage["citation_ids"] == ["R1-E1", "R1-E2"]
    assert function_coverage([first, first])[0]["covered_line_count"] == 40
    gap = function_coverage([entry(1, 20), entry(22, 45, "R1-E2")])[0]
    assert gap["covered_line_count"] == 44 and not gap["fully_covered"]


def test_versions_functions_and_reference_sources_cannot_fill_personal_gap():
    first = entry(1, 40)
    other = entry(6, 45, "R1-E2", path="future/app.py")
    assert not any(row["fully_covered"] for row in function_coverage([first, other]))
    reference = entry(6, 45, "R1-E2", provenance="reference")
    assert not function_coverage([first, reference])[0]["fully_covered"]
    other_function = entry(41, 45, "R1-E2").model_copy(
        update={"function_line_start": 41, "function_line_end": 45}
    )
    rows = function_coverage([first, other_function])
    assert len(rows) == 2 and not rows[0]["fully_covered"]
    assert function_coverage([entry(1, 40).model_copy(update={"function_line_start": None})]) == []


@pytest.mark.parametrize(
    "text",
    [
        "未展示函数完整上下文。",
        "缺少当前函数的完整源码。",
        "未展示 store 的实现、函数完整上下文、实际运行结果。",
        "需补充该函数完整上下文。",
        "函数上下文不完整。",
    ],
)
def test_explicit_source_context_contradictions_are_detected(text):
    assert missing_function_context_claim(text)


@pytest.mark.parametrize(
    "text",
    [
        "函数原文已覆盖，但未给出 store 实现和运行记录。",
        "两个片段各有截取，合起来覆盖函数原文；本人贡献待核验。",
        "未展示外部依赖函数完整上下文。",
        "未展示 store.write 函数完整上下文。",
        "旧报告未展示函数完整上下文，本次已覆盖。",
        "不能说未展示函数完整上下文。",
        "函数完整上下文已提供，但完整项目依赖尚未给出。",
    ],
)
def test_real_unknowns_and_historical_statements_remain_allowed(text):
    assert not missing_function_context_claim(text)


def supplemented_context():
    from app.agents.contracts import RetrievalToolCall
    from app.tools.directed_retrieval import search_frozen_sources

    result = initial_result(long_file())
    contexts = build_evidence_contexts(result, max_evidence=2)
    candidates, _ = search_frozen_sources(
        result.retrieval_sources, "rollback", "Python", contexts[0].evidence
    )
    result = replace(
        result,
        items=[
            replace(
                result.items[0],
                evidence_list=[
                    *result.items[0].evidence_list,
                    *candidates,
                ],
            )
        ],
    )
    contexts, _ = execute_retrieval_tool(
        result,
        contexts,
        RetrievalToolCall(
            requirement_id=contexts[0].requirement_id,
            query="rollback",
        ),
    )
    return result, contexts[0]


def analysis_for(context, gap):
    # Keep rubric tests separate: this exercise targets source coverage consistency.
    context = context.model_copy(update={"rating_rubric": {}})
    analysis = EvidenceAnalysis(
        summary="材料包含可见代码，运行与本人贡献待核验。",
        model="offline",
        items=[
            AIRequirementAnalysis(
                requirement_id=context.requirement_id,
                explanation="原文包含回滚调用。",
                citation_ids=[entry.citation_id for entry in context.evidence],
                information_gap=gap,
                suggestion="补充依赖实现与可核验运行记录。",
                confidence=0.5,
            )
        ],
    )
    return context, analysis


def test_real_error_replay_is_rejected_and_corrected_gap_is_allowed():
    _, context = supplemented_context()
    assert all(not entry.context_complete for entry in context.evidence)
    assert context.function_source_coverage[0].fully_covered
    original_ceiling = context.rating_ceiling
    bad_context, bad = analysis_for(
        context, "未展示 store 的实现、函数完整上下文、实际运行结果，以及本人贡献。"
    )
    with pytest.raises(ValueError, match="jointly covered function"):
        validate_grounded_analysis([bad_context], bad)
    good_context, good = analysis_for(context, "函数原文已覆盖，依赖实现与运行、贡献待核验。")
    validate_grounded_analysis([good_context], good)
    assert context.rating_ceiling == original_ceiling <= 2
    messages = evidence_analysis_messages([context])
    payload = json.loads(messages[1]["content"])
    assert payload["requirements"][0]["function_source_coverage"] == [
        coverage.model_dump() for coverage in context.function_source_coverage
    ]
    assert "不自动提高" in messages[0]["content"]


def test_citing_only_partial_source_does_not_trigger_full_coverage_guard():
    _, context = supplemented_context()
    partial = context.model_copy(update={"evidence": context.evidence[:1]})
    limited, analysis = analysis_for(partial, "未展示函数完整上下文，运行结果待核验。")
    validate_grounded_analysis([limited], analysis)


@pytest.mark.asyncio
@pytest.mark.parametrize("repeat_error", [False, True])
async def test_joint_coverage_conflict_is_repaired_once_or_falls_back(monkeypatch, repeat_error):
    from app.agents.evidence_workflow import run_evidence_workflow
    from app.tests.test_directed_retrieval import OfflinePlanner, enable_offline_planner

    class RepairPlanner(OfflinePlanner):
        def __init__(self):
            super().__init__()
            self.answers = 0
            self.feedback = []

        async def analyze_evidence(self, *, contexts, **kwargs):
            self.answers += 1
            self.feedback.append(kwargs.get("validation_feedback"))
            answer = await super().analyze_evidence(contexts=contexts, **kwargs)
            gap = (
                "未展示 store 的实现、函数完整上下文、实际运行结果。"
                if repeat_error or self.answers == 1
                else "函数原文已覆盖，依赖实现、运行与贡献仍待核验。"
            )
            return answer.model_copy(
                update={
                    "items": [
                        answer.items[0].model_copy(
                            update={
                                "information_gap": gap,
                                "citation_ids": [
                                    entry.citation_id for entry in contexts[0].evidence
                                ],
                            }
                        ),
                    ]
                }
            )

    provider = RepairPlanner()
    enable_offline_planner(monkeypatch, provider)
    result = initial_result(long_file())
    outcome = await run_evidence_workflow(result)
    assert provider.answers == 2
    assert "jointly covered function" in provider.feedback[1]
    assert outcome.contexts[0].function_source_coverage[0].fully_covered
    assert outcome.retrieval_result.overall_score == result.overall_score
    assert outcome.fallback_used == repeat_error
    if repeat_error:
        assert outcome.analysis is None
    else:
        assert outcome.repaired and "原文已覆盖" in outcome.analysis.items[0].information_gap
