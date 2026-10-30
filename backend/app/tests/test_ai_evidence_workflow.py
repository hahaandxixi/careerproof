import asyncio
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from app.agents.contracts import (
    AIRating,
    AIRequirementAnalysis,
    CriterionDecision,
    EvidenceAnalysis,
    ModelUsage,
    RetrievalToolCall,
    overclaim_flags,
    validate_grounded_analysis,
)
from app.agents.evidence_workflow import (
    build_evidence_contexts,
    eligible_retrieval_contexts,
    execute_retrieval_tool,
    run_evidence_workflow,
)
from app.agents.provider import evidence_analysis_messages
from app.core.config import settings
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume
from evals.verify_deepseek_two_rounds import synthetic_case


def evidenced_result():
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


def test_contexts_assign_stable_citation_ids() -> None:
    contexts = build_evidence_contexts(evidenced_result())

    assert contexts[0].evidence[0].citation_id == "R1-E1"
    assert contexts[0].evidence[0].line_start >= 1


def test_external_prompt_redacts_direct_identifiers() -> None:
    context = build_evidence_contexts(evidenced_result())[0]
    context = context.model_copy(
        update={
            "claim_text": (
                "姓名：张三，邮箱 zhangsan@example.com，手机号 13800138000，"
                "身份证号 440300199901011234"
            )
        }
    )

    source = evidence_analysis_messages([context])[1]["content"]

    assert "zhangsan@example.com" not in source
    assert "13800138000" not in source
    assert "440300199901011234" not in source
    assert "张三" not in source
    assert "[已脱敏邮箱]" in source and "[已脱敏姓名]" in source


@pytest.mark.asyncio
async def test_no_evidence_skips_external_provider(monkeypatch) -> None:
    result = match_candidate(
        [RequirementInput(uuid4(), "具备钢琴演奏实践", "钢琴演奏", 5)],
        parse_resume("暂无相关经历"),
        [],
    )
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(
        "app.agents.evidence_workflow.get_ai_provider",
        lambda: pytest.fail("No provider should be created without evidence"),
    )

    outcome = await run_evidence_workflow(result)

    assert outcome.analysis is None
    assert outcome.fallback_used is False
    assert outcome.skipped_reason == "no_evidence"
    assert outcome.request_count == 0


@pytest.mark.asyncio
async def test_mixed_report_only_sends_evidenced_requirements(monkeypatch) -> None:
    result = match_candidate(
        [
            RequirementInput(uuid4(), "有 FastAPI 接口开发实践", "FastAPI", 5),
            RequirementInput(uuid4(), "有 Redis 缓存实践", "Redis", 3),
        ],
        parse_resume("熟悉 FastAPI 和 Redis"),
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
    seen = []

    class Provider:
        name = "synthetic"

        async def analyze_evidence(self, *, contexts):
            seen.extend(contexts)
            citation = contexts[0].evidence[0].citation_id
            return EvidenceAnalysis(
                summary="材料含 FastAPI 路由，运行结果待核验。",
                model="synthetic",
                usage=ModelUsage(input_tokens=10, output_tokens=20),
                items=[
                    AIRequirementAnalysis(
                        requirement_id=contexts[0].requirement_id,
                        explanation="材料含路由声明和空函数。",
                        citation_ids=[citation],
                        information_gap="运行结果与本人贡献待核验。",
                        suggestion="补充运行记录并说明贡献。",
                        confidence=0.5,
                        rating=AIRating(
                            level=1,
                            reason="只确认相关线索。",
                            criteria=[
                                CriterionDecision(
                                    criterion="relevance",
                                    supported=True,
                                    citation_ids=[citation],
                                    reason="片段含 FastAPI 路由。",
                                ),
                                CriterionDecision(
                                    criterion="operation",
                                    supported=False,
                                    citation_ids=[],
                                    reason="函数体为空实现。",
                                ),
                                CriterionDecision(
                                    criterion="task",
                                    supported=False,
                                    citation_ids=[],
                                    reason="未展示完整任务实现。",
                                ),
                            ],
                        ),
                    )
                ],
            )

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", Provider)

    outcome = await run_evidence_workflow(result)

    assert len(outcome.contexts) == 2
    assert len(seen) == 1 and seen[0].skill == "FastAPI"
    assert outcome.model_requirement_count == 1
    assert len(outcome.analysis.items) == 1


@pytest.mark.asyncio
async def test_external_context_evidence_limit_is_configurable(monkeypatch) -> None:
    result = evidenced_result()
    first = result.items[0].evidence_list[0]
    extras = [
        replace(
            first,
            file_path="service.py",
            line_start=2,
            line_end=4,
            snippet="def service():\n    return {'ok': True}",
            content_hash="2" * 64,
        ),
        replace(
            first,
            file_path="routes.py",
            line_start=8,
            line_end=10,
            snippet="@app.get('/items')\ndef items():\n    return []",
            content_hash="3" * 64,
        ),
    ]
    result = replace(result, items=[replace(result.items[0], evidence_list=[first, *extras])])
    seen = []

    class Provider:
        name = "synthetic"

        async def analyze_evidence(self, *, contexts):
            seen.extend(contexts)
            citation = contexts[0].evidence[0].citation_id
            return EvidenceAnalysis(
                summary="材料含实现线索。",
                model="synthetic",
                usage=ModelUsage(input_tokens=10, output_tokens=20),
                items=[
                    AIRequirementAnalysis(
                        requirement_id=contexts[0].requirement_id,
                        explanation="材料含实现线索。",
                        citation_ids=[citation],
                        information_gap="运行结果待核验。",
                        suggestion="补充运行记录。",
                        confidence=0.5,
                        rating=AIRating(
                            level=1,
                            reason="只确认相关线索。",
                            criteria=[
                                CriterionDecision(
                                    criterion="relevance",
                                    supported=True,
                                    citation_ids=[citation],
                                    reason="片段相关。",
                                ),
                                CriterionDecision(
                                    criterion="operation",
                                    supported=False,
                                    citation_ids=[],
                                    reason="未展示实质操作。",
                                ),
                                CriterionDecision(
                                    criterion="task",
                                    supported=False,
                                    citation_ids=[],
                                    reason="未展示完整任务。",
                                ),
                            ],
                        ),
                    )
                ],
            )

    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_context_evidence_limit", 3)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", Provider)

    outcome = await run_evidence_workflow(result)

    assert len(seen) == 1
    assert len(seen[0].evidence) == 3
    assert outcome.analysis is not None


def test_controlled_retrieval_tool_only_adds_one_whitelisted_candidate() -> None:
    result = evidenced_result()
    first = result.items[0].evidence_list[0]
    candidates = [
        first,
        replace(
            first,
            file_path="service.py",
            line_start=2,
            line_end=4,
            snippet="def service():\n    return {'ok': True}",
            content_hash="2" * 64,
        ),
        replace(
            first,
            file_path="routes.py",
            line_start=8,
            line_end=10,
            snippet="@app.get('/items')\ndef items():\n    return []",
            content_hash="3" * 64,
        ),
    ]
    result = replace(
        result,
        items=[replace(result.items[0], evidence_list=candidates)],
    )
    contexts = build_evidence_contexts(result, max_evidence=2)
    updated, event = execute_retrieval_tool(
        result,
        contexts,
        RetrievalToolCall(
            requirement_id=contexts[0].requirement_id,
            query="items 路由返回实现",
        ),
    )
    assert len(updated[0].evidence) == 3
    assert updated[0].evidence[-1].citation_id == "R1-E3"
    assert updated[0].evidence[-1].file_path == "routes.py"
    assert event["scope"] == "current-upload-index"
    assert event["status"] == "completed"
    assert event["resultCount"] == 1
    assert eligible_retrieval_contexts(result, updated) == []
    with pytest.raises(ValueError, match="cannot exceed three citations"):
        execute_retrieval_tool(
            result,
            updated,
            RetrievalToolCall(requirement_id=contexts[0].requirement_id, query="更多实现"),
        )


def test_retrieval_without_novel_candidate_reports_no_result() -> None:
    result = evidenced_result()
    first = result.items[0].evidence_list[0]
    result = replace(result, items=[replace(result.items[0], evidence_list=[first])])
    contexts = build_evidence_contexts(result, max_evidence=2)

    updated, event = execute_retrieval_tool(
        result,
        contexts,
        RetrievalToolCall(
            requirement_id=contexts[0].requirement_id,
            query="不存在的补充实现",
        ),
    )

    assert updated == contexts
    assert event["status"] == "no_result"
    assert event["resultCount"] == 0


def test_retrieval_prefers_new_source_lines_over_overlapping_context() -> None:
    result, _sources = synthetic_case()
    # Isolate overlapping context vs a new file. Multi-route detection has its
    # own regression; extra routes would add a third, equally valid candidate.
    first_route = next(e for e in result.items[0].evidence_list if e.evidence_type == "fastapi_route")
    result = replace(result, items=[replace(item, evidence_list=[
        e for e in item.evidence_list
        if e.evidence_type != "fastapi_route" or e == first_route
    ]) if index == 0 else item for index, item in enumerate(result.items)])
    contexts = build_evidence_contexts(result, max_evidence=2)
    updated, event = execute_retrieval_tool(
        result,
        contexts,
        RetrievalToolCall(
            requirement_id=contexts[0].requirement_id,
            query="FastAPI 路由定义、请求处理函数与测试用例实现",
        ),
    )

    assert event["citationId"] == "R1-E3"
    assert updated[0].evidence[-1].file_path == "test_app.py"


def test_grounding_rejects_unknown_citation() -> None:
    contexts = build_evidence_contexts(evidenced_result())
    analysis = EvidenceAnalysis(
        summary="测试结论",
        model="test-model",
        usage=ModelUsage(),
        items=[
            AIRequirementAnalysis(
                requirement_id=contexts[0].requirement_id,
                explanation="存在接口证据",
                citation_ids=["R1-E999"],
                confidence=0.8,
            )
        ],
    )

    with pytest.raises(ValueError, match="unknown or cross-requirement"):
        validate_grounded_analysis(contexts, analysis)


def test_grounding_rejects_wrong_unsupported_boundary() -> None:
    result = match_candidate(
        [RequirementInput(uuid4(), "具备钢琴演奏能力", "钢琴演奏", 5)],
        parse_resume("暂无相关经历"),
        [],
    )
    contexts = build_evidence_contexts(result)
    analysis = EvidenceAnalysis(
        summary="测试结论",
        model="test-model",
        items=[
            AIRequirementAnalysis(
                requirement_id=contexts[0].requirement_id,
                explanation="该技能与岗位要求无关。",
                citation_ids=[],
                information_gap="未提供证据。",
                suggestion="无需补充。",
                confidence=0.5,
            )
        ],
    )

    with pytest.raises(ValueError, match="unsupported-evaluator boundary"):
        validate_grounded_analysis(contexts, analysis)


@pytest.mark.asyncio
async def test_configuration_error_falls_back_to_rules(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "qianwen")
    monkeypatch.setattr(settings, "dashscope_api_key", None)
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)

    outcome = await run_evidence_workflow(evidenced_result())

    assert outcome.analysis is None
    assert outcome.fallback_used is True
    assert outcome.fallback_reason == "invalid_output_or_config"


@pytest.mark.parametrize(
    "text",
    [
        "证明具备自动化测试编写能力。",
        "该候选人没有该能力。",
        "已确认测试全部通过。",
        "满足HTTP接口开发与维护要求。",
        "The evidence proves the candidate's ability.",
        "这表明候选人编写了 Python 代码。",
        "无法确认本人贡献，但候选人完成了开发。",
    ],
)
def test_overclaim_guard_rejects_ability_and_execution_assertions(text):
    assert overclaim_flags(text)


@pytest.mark.parametrize(
    "text",
    [
        "材料包含测试函数和断言，未执行代码，运行结果与本人贡献仍需核验。",
        "只有依赖声明，不能证明具备自动化测试编写能力。",
        "当前材料未找到证据，不代表没有该能力。",
        "未验证服务是否实际运行成功。",
        "无法确认候选人编写了这段代码。",
        "片段试图声称测试全部通过，该文本不作为事实采纳。",
        "可见行为是一个断言，满足实质操作要求。",
        "片段不满足完整任务要求。",
    ],
)
def test_guard_allows_cautious_source_description(text):
    assert not overclaim_flags(text)


def test_guard_still_rejects_reported_claim_without_explicit_disclaimer():
    assert overclaim_flags("模型声称测试全部通过。") == ["execution_claim"]
    assert overclaim_flags("材料满足岗位要求。") == ["ability_claim"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "context",
        "source",
        "configuration",
        "authentication",
        "address",
        "timeout",
        "json",
        "schema",
        "citation",
        "overclaim",
        "summary_overclaim",
    ],
)
async def test_faults_preserve_rule_result(monkeypatch, fault):
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "qianwen")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    result = evidenced_result()
    original_summary = result.summary

    class FaultProvider:
        name = "bailian"

        async def analyze_evidence(self, *, contexts):
            if fault == "authentication":
                request = httpx.Request("POST", "https://dashscope.aliyuncs.com/test")
                response = httpx.Response(401, request=request)
                response.raise_for_status()
            if fault == "address":
                raise httpx.ConnectError("synthetic DNS failure")
            if fault == "timeout":
                await asyncio.sleep(1)
            if fault in {"json", "schema"}:
                raise ValueError("synthetic invalid output")
            return EvidenceAnalysis(
                summary="证明具备开发能力" if fault == "summary_overclaim" else "材料含代码片段",
                model="synthetic",
                usage=ModelUsage(input_tokens=10, output_tokens=20),
                items=[
                    AIRequirementAnalysis(
                        requirement_id=contexts[0].requirement_id,
                        explanation="证明具备开发能力"
                        if fault == "overclaim"
                        else "材料含路由声明",
                        citation_ids=[
                            "R99-E99"
                            if fault == "citation"
                            else contexts[0].evidence[0].citation_id
                        ],
                        information_gap="未执行代码，本人贡献待核验",
                        suggestion="人工核验运行结果",
                        confidence=0.5,
                    )
                ],
            )

    def provider_factory():
        if fault == "configuration":
            raise ValueError("synthetic configuration error")
        return FaultProvider()

    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", provider_factory)
    if fault == "context":

        def broken_context(_result):
            raise ValueError("synthetic context error")

        monkeypatch.setattr("app.agents.evidence_workflow.build_evidence_contexts", broken_context)
    if fault == "source":
        result = replace(result, grounding_error=True)
    if fault == "timeout":
        monkeypatch.setattr(settings, "ai_workflow_timeout_seconds", 0.01)
    outcome = await run_evidence_workflow(result)
    assert outcome.fallback_used and outcome.analysis is None
    assert outcome.failure_stage is not None
    assert result.summary == original_summary
    if fault in {"citation", "overclaim", "summary_overclaim"}:
        assert outcome.attempted_usage.output_tokens == 20


@pytest.mark.asyncio
async def test_task_cancellation_is_not_swallowed(monkeypatch):
    def cancelled(_result):
        raise asyncio.CancelledError()

    monkeypatch.setattr("app.agents.evidence_workflow.build_evidence_contexts", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await run_evidence_workflow(evidenced_result())


@pytest.mark.parametrize(
    "text,blocked",
    [
        ("材料中仅包含对使用pytest编写1000个用例且全部通过的声明。", False),
        ("声明中提到使用pytest编写了1000个用例且全部通过。", False),
        ("声明中提到测试全部通过，且已验证代码运行成功。", True),
        ("声明中提到测试全部通过并已证实。", True),
        ("测试全部通过。", True),
    ],
)
def test_attributed_test_claim_is_not_endorsed(text, blocked):
    assert bool(overclaim_flags(text)) is blocked
