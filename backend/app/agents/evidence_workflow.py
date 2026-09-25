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
from app.agents.provider import (
    OpenAICompatibleProvider,
    ProviderOutputTruncatedError,
    get_ai_provider,
)
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
    json_repair_count: int = 0
    model_requirement_count: int = 0
    provider_finish_reason: str | None = None


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
                provenance=source.provenance,
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


def novel_source_lines(candidate, evidence: list[EvidenceCandidate]) -> int:
    """Count nonblank candidate lines absent from already shown source ranges."""
    covered = {
        line
        for entry in evidence
        if entry.file_path == candidate.file_path
        for line in range(entry.line_start, entry.line_end + 1)
    }
    return sum(
        bool(text.strip()) and line not in covered
        for line, text in enumerate(candidate.snippet.splitlines(), candidate.line_start)
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
    if len(context.evidence) >= 3:
        raise ValueError("retrieval tool cannot exceed three citations per requirement")
    result_index = next(
        (
            index
            for index, entry in enumerate(result.items)
            if str(entry.requirement_id) == call.requirement_id
        ),
        None,
    )
    item = result.items[result_index] if result_index is not None else None
    if item is None:
        raise ValueError("retrieval tool requirement is absent from the match result")
    existing = {source_key(entry) for entry in context.evidence}
    candidates = [
        entry
        for entry in item.evidence_list
        if source_key(entry) not in existing and novel_source_lines(entry, context.evidence)
    ]
    tokens = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", call.query.lower()))

    def relevance(candidate) -> tuple[int, int, int]:
        text = " ".join(
            (candidate.file_path, candidate.evidence_type, candidate.snippet, candidate.explanation)
        ).lower()
        return (
            sum(token in text for token in tokens),
            novel_source_lines(candidate, context.evidence),
            len(candidate.snippet),
        )

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
            citation_id=f"R{result_index + 1}-E{len(context.evidence) + 1}",
            file_path=selected.file_path,
            line_start=selected.line_start,
            line_end=selected.line_end,
            evidence_type=selected.evidence_type,
            strength=selected.strength,
            snippet=selected.snippet,
            context_complete=selected.context_complete,
            context_note=selected.context_note,
            provenance=selected.provenance,
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
        if context is None or len(context.evidence) >= 3:
            continue
        existing = {source_key(entry) for entry in context.evidence}
        if any(
            source_key(entry) not in existing and novel_source_lines(entry, context.evidence)
            for entry in item.evidence_list
        ):
            return True
    return False


def eligible_retrieval_contexts(
    result: MatchResult, contexts: list[RequirementEvidenceContext]
) -> list[RequirementEvidenceContext]:
    return [context for context in contexts if has_retrieval_candidate(result, [context])]


def _fallback_reason(exc: Exception) -> str:
    if isinstance(exc, ProviderOutputTruncatedError):
        return "output_token_limit"
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
            model_contexts = [context for context in contexts if context.evidence]
            stage = "request"
            await _notify(progress, "等待可用的模型调用名额")
            async with _model_semaphore():
                if isinstance(provider, OpenAICompatibleProvider):
                    previous_retrieval: dict | None = None
                    for round_number in range(1, settings.ai_max_retrieval_calls + 1):
                        eligible = eligible_retrieval_contexts(result, model_contexts)
                        used = provider.combined_usage()
                        remaining_input = settings.ai_per_report_input_token_limit - (
                            used.input_tokens if used else 0
                        )
                        remaining_output = settings.ai_per_report_output_token_limit - (
                            used.output_tokens if used else 0
                        )
                        # Keep room for the final report even if the planner wants another lookup.
                        if not eligible or remaining_input <= 1500 or remaining_output <= 400:
                            break
                        stage = "tool_planning"
                        await _notify(progress, f"模型正在判断第 {round_number} 轮是否需要补充检索")
                        try:
                            request_count += 1
                            tool_call = await provider.plan_evidence_retrieval(
                                contexts=eligible,
                                previous_retrieval=previous_retrieval,
                                input_token_limit=remaining_input - 1000,
                                output_token_limit=remaining_output - 200,
                            )
                        except (ValidationError, ValueError, KeyError, TypeError):
                            tool_calls.append(
                                {
                                    "tool": "retrieve_more_evidence",
                                    "round": round_number,
                                    "status": "rejected",
                                    "reason": "invalid_tool_call",
                                    "scope": "current-upload-index",
                                }
                            )
                            await _notify(progress, "补检索请求未通过边界校验，继续使用现有证据")
                            break
                        if tool_call is None:
                            tool_calls.append(
                                {
                                    "tool": "retrieve_more_evidence",
                                    "round": round_number,
                                    "status": "not_requested",
                                    "reason": "planner_declined",
                                    "scope": "current-upload-index",
                                }
                            )
                            await _notify(progress, "模型判断现有证据足够，停止补检索")
                            break
                        stage = "tool_execution"
                        await _notify(progress, f"正在按模型第 {round_number} 轮请求补充证据")
                        model_contexts, tool_event = execute_retrieval_tool(
                            result, model_contexts, tool_call
                        )
                        tool_event["round"] = round_number
                        tool_calls.append(tool_event)
                        updated = {context.requirement_id: context for context in model_contexts}
                        contexts = [
                            updated.get(context.requirement_id, context) for context in contexts
                        ]
                        previous_retrieval = {
                            "requirement_id": tool_call.requirement_id,
                            "result_count": tool_event["resultCount"],
                            "citation_id": tool_event.get("citationId"),
                            "new_evidence_snippet": next(
                                evidence.snippet[:240]
                                for context in model_contexts
                                if context.requirement_id == tool_call.requirement_id
                                for evidence in context.evidence
                                if evidence.citation_id == tool_event.get("citationId")
                            ) if tool_event["resultCount"] else None,
                        }
                        if tool_event["resultCount"] == 0:
                            break
                stage = "request"
                await _notify(progress, "正在调用模型分析证据与评级判据")
                if isinstance(provider, OpenAICompatibleProvider):
                    provider.progress_callback = progress
                request_count += 1
                if isinstance(provider, OpenAICompatibleProvider):
                    planning_usage = provider.combined_usage()
                    remaining_input = settings.ai_per_report_input_token_limit - (
                        planning_usage.input_tokens if planning_usage else 0
                    )
                    remaining_output = settings.ai_per_report_output_token_limit - (
                        planning_usage.output_tokens if planning_usage else 0
                    )
                    analysis = await provider.analyze_evidence(
                        contexts=model_contexts,
                        input_token_limit=remaining_input,
                        output_token_limit=remaining_output,
                    )
                else:
                    analysis = await provider.analyze_evidence(contexts=model_contexts)
                stage = "validation"
                try:
                    validate_grounded_analysis(model_contexts, analysis)
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
                        contexts=model_contexts,
                        validation_feedback=str(validation_error),
                        previous_analysis=analysis,
                        input_token_limit=remaining_input,
                        output_token_limit=remaining_output,
                    )
                    validate_grounded_analysis(model_contexts, repaired_analysis)
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
            json_repair_count=(
                provider.json_repair_count
                if isinstance(provider, OpenAICompatibleProvider)
                else 0
            ),
            model_requirement_count=len(model_contexts),
            provider_finish_reason=(
                provider.last_finish_reason
                if isinstance(provider, OpenAICompatibleProvider)
                else None
            ),
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
            attempted_usage=(
                provider.combined_usage()
                if "provider" in locals()
                and isinstance(provider, OpenAICompatibleProvider)
                else analysis.usage
                if analysis
                else planning_usage
            ),
            failure_stage=stage,
            repaired=repaired,
            tool_calls=tuple(tool_calls),
            request_count=request_count,
            json_repair_count=(
                provider.json_repair_count
                if "provider" in locals()
                and isinstance(provider, OpenAICompatibleProvider)
                else 0
            ),
            model_requirement_count=(len(model_contexts) if "model_contexts" in locals() else 0),
            provider_finish_reason=(
                provider.last_finish_reason
                if "provider" in locals()
                and isinstance(provider, OpenAICompatibleProvider)
                else None
            ),
        )
