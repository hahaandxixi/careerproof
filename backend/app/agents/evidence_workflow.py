from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from app.agents.contracts import (
    EvidenceAnalysis,
    EvidenceCandidate,
    ModelUsage,
    RequirementEvidenceContext,
    RetrievalToolCall,
    validate_grounded_analysis,
)
from app.agents.provider import OpenAICompatibleProvider, get_ai_provider
from app.core.config import settings
from app.tools.evidence_context import source_key
from app.tools.evidence_levels import classify_evidence
from app.tools.matcher import MatchResult
from app.tools.skill_rubric import rubric_for


@dataclass(frozen=True, slots=True)
class EvidenceWorkflowOutcome:
    contexts: list[RequirementEvidenceContext]
    analysis: EvidenceAnalysis | None
    provider: str
    model: str | None
    fallback_used: bool
    fallback_reason: str | None
    skipped_reason: str | None = None
    attempted_usage: ModelUsage | None = None
    failure_stage: str | None = None
    repaired: bool = False
    tool_calls: tuple[dict, ...] = ()
    request_count: int = 0


_MODEL_SEMAPHORE: asyncio.Semaphore | None = None
_MODEL_SEMAPHORE_SIZE: int | None = None


def _model_semaphore() -> asyncio.Semaphore:
    global _MODEL_SEMAPHORE, _MODEL_SEMAPHORE_SIZE
    if _MODEL_SEMAPHORE is None or settings.ai_model_concurrency != _MODEL_SEMAPHORE_SIZE:
        _MODEL_SEMAPHORE = asyncio.Semaphore(settings.ai_model_concurrency)
        _MODEL_SEMAPHORE_SIZE = settings.ai_model_concurrency
    return _MODEL_SEMAPHORE


async def _notify(progress: Callable[[str], Awaitable[None]] | None, message: str) -> None:
    if progress:
        await progress(message)


def build_evidence_contexts(
    result: MatchResult, *, max_evidence: int = 3
) -> list[RequirementEvidenceContext]:
    if max_evidence < 1 or max_evidence > 3:
        raise ValueError("max_evidence must be between 1 and 3")
    contexts: list[RequirementEvidenceContext] = []
    for requirement_index, item in enumerate(result.items, 1):
        evidence = [
            EvidenceCandidate(
                citation_id=f"R{requirement_index}-E{evidence_index}",
                file_path=source.file_path,
                line_start=source.line_start,
                line_end=source.line_end,
                evidence_type=source.evidence_type,
                strength=source.strength,
                snippet=source.snippet,
                context_complete=source.context_complete,
                context_note=source.context_note,
            )
            for evidence_index, source in enumerate(item.evidence_list[:max_evidence], 1)
            if source.snippet.strip()
        ]
        contexts.append(
            RequirementEvidenceContext(
                requirement_id=str(item.requirement_id),
                requirement_title=item.requirement_title,
                skill=item.skill,
                verdict=item.verdict,
                rule_score=item.rule_base_score,
                claimed=item.claimed,
                claim_text=item.claim_text[:500] if item.claim_text else None,
                evidence=evidence,
                rating_rubric=rubric_for(item.skill),
                rating_ceiling=classify_evidence(
                    {"skill": item.skill, "evidenceList": [e.model_dump() for e in evidence]},
                    item.verdict,
                )["evidence_level"],
            )
        )
    return contexts


def citation_for_source(context: RequirementEvidenceContext | None, source) -> str | None:
    if context is None:
        return None
    return next(
        (
            e.citation_id
            for e in context.evidence
            if source_key(e) == source_key(source) and e.snippet == source.snippet
        ),
        None,
    )


def execute_retrieval_tool(
    result: MatchResult,
    contexts: list[RequirementEvidenceContext],
    call: RetrievalToolCall,
) -> tuple[list[RequirementEvidenceContext], dict]:
    """Execute one model-selected lookup over the current upload's bounded candidates."""
    context_index = next(
        (
            index
            for index, context in enumerate(contexts)
            if context.requirement_id == call.requirement_id
        ),
        None,
    )
    if context_index is None:
        raise ValueError("retrieval tool targeted an unknown requirement")
    context = contexts[context_index]
    item = next(
        (entry for entry in result.items if str(entry.requirement_id) == call.requirement_id),
        None,
    )
    if item is None:
        raise ValueError("retrieval tool requirement is absent from the match result")
    existing = {source_key(entry) for entry in context.evidence}
    candidates = [entry for entry in item.evidence_list if source_key(entry) not in existing]
    tokens = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", call.query.lower()))

    def relevance(candidate) -> tuple[int, int]:
        text = " ".join(
            (candidate.file_path, candidate.evidence_type, candidate.snippet, candidate.explanation)
        ).lower()
        return sum(token in text for token in tokens), len(candidate.snippet)

    selected = max(candidates, key=relevance) if candidates else None
    event = {
        "tool": "retrieve_more_evidence",
        "requirementId": call.requirement_id,
        "query": call.query,
        "resultCount": 1 if selected else 0,
        "scope": "current-upload-index",
    }
    if selected is None:
        return contexts, event
    evidence = [
        *context.evidence,
        EvidenceCandidate(
            citation_id=f"R{context_index + 1}-E{len(context.evidence) + 1}",
            file_path=selected.file_path,
            line_start=selected.line_start,
            line_end=selected.line_end,
            evidence_type=selected.evidence_type,
            strength=selected.strength,
            snippet=selected.snippet,
            context_complete=selected.context_complete,
            context_note=selected.context_note,
        ),
    ]
    updated = context.model_copy(
        update={
            "evidence": evidence,
            "rating_ceiling": classify_evidence(
                {
                    "skill": context.skill,
                    "evidenceList": [entry.model_dump() for entry in evidence],
                },
                context.verdict,
            )["evidence_level"],
        }
    )
    copied = list(contexts)
    copied[context_index] = updated
    event["citationId"] = evidence[-1].citation_id
    return copied, event


def has_retrieval_candidate(
    result: MatchResult, contexts: list[RequirementEvidenceContext]
) -> bool:
    """Avoid paying for a planner call when the local index has nothing new to return."""
    by_requirement = {context.requirement_id: context for context in contexts}
    for item in result.items:
        context = by_requirement.get(str(item.requirement_id))
        if context is None:
            continue
        existing = {source_key(entry) for entry in context.evidence}
        if any(source_key(entry) not in existing for entry in item.evidence_list):
            return True
    return False


def _fallback_reason(exc: Exception) -> str:
    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return "authentication"
        if status == 429:
            try:
                if str(exc.response.json().get("error", {}).get("code")) == "1305":
                    return "provider_busy"
            except (ValueError, AttributeError, TypeError):
                pass
            return "rate_limit"
        return "provider_http_error"
    if isinstance(exc, httpx.NetworkError):
        return "network"
    if isinstance(exc, ValidationError | ValueError | KeyError | TypeError):
        return "invalid_output_or_config"
    return "provider_error"


async def run_evidence_workflow(
    result: MatchResult,
    progress: Callable[[str], Awaitable[None]] | None = None,
    *,
    external_allowed: bool = True,
    external_skip_reason: str | None = None,
) -> EvidenceWorkflowOutcome:
    contexts: list[RequirementEvidenceContext] = []
    configured_provider = settings.ai_provider if settings.ai_external_enabled else "rules"
    configured_model = (
        settings.deepseek_model
        if configured_provider == "deepseek"
        else settings.zhipu_model
        if configured_provider == "zhipu"
        else settings.bailian_model
        if configured_provider != "rules"
        else None
    )
    analysis = None
    repaired = False
    tool_calls: list[dict] = []
    planning_usage: ModelUsage | None = None
    request_count = 0
    stage = "context"
    try:
        async with asyncio.timeout(settings.ai_workflow_timeout_seconds):
            if result.grounding_error:
                raise ValueError("source context validation failed")
            if len(result.items) > settings.ai_max_requirements:
                raise ValueError("requirement count exceeds AI_MAX_REQUIREMENTS")
            contexts = build_evidence_contexts(result)
            if not external_allowed:
                return EvidenceWorkflowOutcome(
                    contexts,
                    None,
                    "rules",
                    None,
                    False,
                    None,
                    skipped_reason=external_skip_reason or "usage_budget",
                )
            if settings.ai_skip_when_no_evidence and not any(
                context.evidence for context in contexts
            ):
                return EvidenceWorkflowOutcome(
                    contexts,
                    None,
                    "rules",
                    None,
                    False,
                    None,
                    skipped_reason="no_evidence",
                )
            stage = "configuration"
            provider = get_ai_provider()
            if provider.name == "mock":
                return EvidenceWorkflowOutcome(contexts, None, "rules", None, False, None)
            contexts = build_evidence_contexts(result, max_evidence=2)
            stage = "request"
            await _notify(progress, "等待可用的模型调用名额")
            async with _model_semaphore():
                if isinstance(provider, OpenAICompatibleProvider) and has_retrieval_candidate(
                    result, contexts
                ):
                    stage = "tool_planning"
                    await _notify(progress, "模型正在判断是否需要补充检索")
                    try:
                        request_count += 1
                        tool_call = await provider.plan_evidence_retrieval(contexts=contexts)
                    except (ValidationError, ValueError, KeyError, TypeError):
                        tool_call = None
                        tool_calls.append(
                            {
                                "tool": "retrieve_more_evidence",
                                "status": "rejected",
                                "reason": "invalid_tool_call",
                                "scope": "current-upload-index",
                            }
                        )
                        await _notify(progress, "补检索请求未通过边界校验，继续使用现有证据")
                    planning_usage = provider.planning_usage
                    if tool_call:
                        stage = "tool_execution"
                        await _notify(progress, "正在按模型请求从当前材料补充一条证据")
                        contexts, tool_event = execute_retrieval_tool(result, contexts, tool_call)
                        tool_calls.append(tool_event)
                stage = "request"
                await _notify(progress, "正在调用模型分析证据与评级判据")
                if isinstance(provider, OpenAICompatibleProvider):
                    provider.progress_callback = progress
                request_count += 1
                if isinstance(provider, OpenAICompatibleProvider):
                    remaining_input = settings.ai_per_report_input_token_limit - (
                        planning_usage.input_tokens if planning_usage else 0
                    )
                    remaining_output = settings.ai_per_report_output_token_limit - (
                        planning_usage.output_tokens if planning_usage else 0
                    )
                    analysis = await provider.analyze_evidence(
                        contexts=contexts,
                        input_token_limit=remaining_input,
                        output_token_limit=remaining_output,
                    )
                else:
                    analysis = await provider.analyze_evidence(contexts=contexts)
                stage = "validation"
                try:
                    validate_grounded_analysis(contexts, analysis)
                except ValueError as validation_error:
                    if not isinstance(provider, OpenAICompatibleProvider):
                        raise
                    await _notify(progress, "模型输出存在冲突，正在进行一次定向修正")
                    first_usage = analysis.usage
                    stage = "repair"
                    request_count += 1
                    remaining_input = settings.ai_per_report_input_token_limit - (
                        (planning_usage.input_tokens if planning_usage else 0)
                        + first_usage.input_tokens
                    )
                    remaining_output = settings.ai_per_report_output_token_limit - (
                        (planning_usage.output_tokens if planning_usage else 0)
                        + first_usage.output_tokens
                    )
                    repaired_analysis = await provider.analyze_evidence(
                        contexts=contexts,
                        validation_feedback=str(validation_error),
                        previous_analysis=analysis,
                        input_token_limit=remaining_input,
                        output_token_limit=remaining_output,
                    )
                    validate_grounded_analysis(contexts, repaired_analysis)
                    repaired = True
                    analysis = repaired_analysis.model_copy(
                        update={
                            "usage": repaired_analysis.usage.model_copy(
                                update={
                                    "input_tokens": first_usage.input_tokens
                                    + repaired_analysis.usage.input_tokens,
                                    "output_tokens": first_usage.output_tokens
                                    + repaired_analysis.usage.output_tokens,
                                    "cache_hit_tokens": first_usage.cache_hit_tokens
                                    + repaired_analysis.usage.cache_hit_tokens,
                                    "latency_ms": first_usage.latency_ms
                                    + repaired_analysis.usage.latency_ms,
                                }
                            )
                        }
                    )
                if planning_usage:
                    usage = analysis.usage
                    analysis = analysis.model_copy(
                        update={
                            "usage": usage.model_copy(
                                update={
                                    "input_tokens": planning_usage.input_tokens
                                    + usage.input_tokens,
                                    "output_tokens": planning_usage.output_tokens
                                    + usage.output_tokens,
                                    "cache_hit_tokens": planning_usage.cache_hit_tokens
                                    + usage.cache_hit_tokens,
                                    "latency_ms": planning_usage.latency_ms + usage.latency_ms,
                                }
                            )
                        }
                    )
        return EvidenceWorkflowOutcome(
            contexts=contexts,
            analysis=analysis,
            provider=provider.name,
            model=analysis.model,
            fallback_used=False,
            fallback_reason=None,
            repaired=repaired,
            tool_calls=tuple(tool_calls),
            request_count=request_count,
        )
    except Exception as exc:
        if not settings.ai_local_fallback_enabled:
            raise
        return EvidenceWorkflowOutcome(
            contexts=contexts,
            analysis=None,
            provider=configured_provider,
            model=configured_model,
            fallback_used=True,
            fallback_reason=_fallback_reason(exc),
            attempted_usage=analysis.usage if analysis else planning_usage,
            failure_stage=stage,
            repaired=repaired,
            tool_calls=tuple(tool_calls),
            request_count=request_count,
        )
