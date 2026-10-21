import json

import httpx
import pytest

from app.agents.contracts import EvidenceAnalysis, validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.input_budget import estimate_wire_input_bytes
from app.agents.provider import (
    ProviderInputBudgetError,
    evidence_analysis_messages,
    sanitize_outgoing_messages,
)
from app.core.config import settings
from app.tests.test_ai_evidence_workflow import evidenced_result
from app.tests.test_deepseek_provider import provider
from app.tests.test_report_input_budget import answer, response


@pytest.fixture
def context():
    return build_evidence_contexts(evidenced_result(), max_evidence=2)[0]


@pytest.fixture
def previous(context):
    return EvidenceAnalysis.model_validate({
        **answer(context),
        "model": "synthetic-old-model",
        "usage": {"input_tokens": 6101, "output_tokens": 1582,
                  "cache_hit_tokens": 1792, "latency_ms": 7110},
    })


def repair_messages(context, previous):
    return evidence_analysis_messages(
        [context], validation_feedback="Synthetic criterion conflict",
        previous_analysis=previous,
    )


def test_compact_prompt_preserves_all_evidence_and_history_fields(context):
    snippet = "def example():\n    value = 'a  b'\n    return value\n"
    evidence = context.evidence[0].model_copy(update={"snippet": snippet})
    context = context.model_copy(update={"evidence": [evidence]})
    history = {"previousReportId": "synthetic-old-report",
               "historicalOnly": True, "content_hash": "synthetic-hash",
               "citation_ids": ["history-R1-E1"], "explanation": "Reference only"}
    messages = evidence_analysis_messages([context], history_context=history)
    payload = json.loads(messages[1]["content"])

    requirement = dict(payload["requirements"][0])
    policy = requirement.pop("citation_policy")
    assert requirement == context.model_dump()
    assert payload["historicalContext"] == history
    assert policy == {
        "allowed_ids": [entry.citation_id for entry in context.evidence],
        "personal_citation_required": True,
    }
    assert payload["requirements"][0]["evidence"][0]["snippet"] == snippet
    assert messages[1]["content"] == json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )
    assert len(messages[1]["content"]) < len(json.dumps(payload, ensure_ascii=False))
    assert sanitize_outgoing_messages(messages) == messages


def test_repair_omits_only_transport_metadata(context, previous):
    messages = repair_messages(context, previous)
    payload = json.loads(messages[1]["content"])
    requirement = dict(payload["requirements"][0])
    requirement.pop("citation_policy")
    assert requirement == context.model_dump()
    assert payload["rejectedOutput"] == previous.model_dump(exclude={"model", "usage"})
    assert payload["rejectedOutput"]["items"] == previous.model_dump()["items"]
    assert payload["validationFeedback"] == "Synthetic criterion conflict"
    assert previous.model == "synthetic-old-model"
    assert previous.usage.input_tokens == 6101
    assert "synthetic-old-model" not in messages[1]["content"]


def test_compact_repair_keeps_personal_data_filtering(context, previous):
    raw_email = "synthetic.person@example.com"
    raw_phone = "13800138000"
    unsafe = previous.model_copy(update={"summary": f"Contact {raw_email} {raw_phone}"})
    messages = evidence_analysis_messages(
        [context], previous_analysis=unsafe,
        validation_feedback=f"Check {raw_email}",
        history_context={"explanation": f"Historical contact {raw_phone}"},
    )
    outgoing = sanitize_outgoing_messages(messages)
    serialized = json.dumps(outgoing)
    assert raw_email not in serialized and raw_phone not in serialized
    assert unsafe.summary == f"Contact {raw_email} {raw_phone}"
    requirement = dict(json.loads(outgoing[1]["content"])["requirements"][0])
    requirement.pop("citation_policy")
    assert requirement == context.model_dump()


def test_unevidenced_policy_allows_only_current_reference_citations(context):
    portfolio = context.evidence[0]
    reference = portfolio.model_copy(update={"citation_id": "R1-E2", "provenance": "reference"})
    context = context.model_copy(update={
        "verdict": "claimed_only", "evidence": [portfolio, reference],
    })
    payload = json.loads(evidence_analysis_messages([context])[1]["content"])
    assert payload["requirements"][0]["citation_policy"] == {
        "allowed_ids": ["R1-E2"], "personal_citation_required": False,
    }
    assert len(payload["requirements"][0]["evidence"]) == 2


def test_correction_feedback_names_requirement_without_relaxing_guard(context, previous):
    context = context.model_copy(update={"verdict": "gap"})
    with pytest.raises(ValueError, match="personal evidence for an unevidenced") as error:
        validate_grounded_analysis([context], previous)
    assert f"requirement_id={context.requirement_id}" in str(error.value)
    assert "permitted citation_ids=[]" in str(error.value)
    assert "Do not increase the rating" in str(error.value)


def wire_bound(messages):
    return estimate_wire_input_bytes({
        "model": "deepseek-flash",
        "temperature": 0.1,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "messages": sanitize_outgoing_messages(messages),
    })


@pytest.mark.asyncio
async def test_compact_repair_fits_budget_that_rejected_legacy_payload(
    monkeypatch, context, previous,
):
    messages = repair_messages(context, previous)
    required = wire_bound(messages)
    legacy_payload = json.loads(messages[1]["content"])
    legacy_payload["rejectedOutput"] = previous.model_dump()
    legacy_messages = [messages[0], {
        "role": "user", "content": json.dumps(legacy_payload, ensure_ascii=False),
    }]
    legacy_required = wire_bound(legacy_messages)
    limit = (required + legacy_required) // 2
    assert required <= limit < legacy_required
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", limit)
    monkeypatch.setattr(settings, "ai_per_report_output_token_limit", 4000)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["messages"] == sanitize_outgoing_messages(messages)
        assert "_local_input_token_limit" not in body
        return response(context)

    instance = provider(transport=httpx.MockTransport(handler))
    result = await instance.analyze_evidence(
        contexts=[context], previous_analysis=previous,
        validation_feedback="Synthetic criterion conflict", input_token_limit=limit,
    )
    validate_grounded_analysis([context], result)
    assert len(calls) == 1
    assert result.usage.input_tokens == 80 and result.usage.output_tokens == 40


@pytest.mark.asyncio
async def test_compact_repair_still_blocks_before_transport_below_budget(
    monkeypatch, context, previous,
):
    messages = repair_messages(context, previous)
    required = wire_bound(messages)
    monkeypatch.setattr(settings, "ai_per_report_input_token_limit", required)
    monkeypatch.setattr(settings, "ai_per_report_output_token_limit", 4000)
    calls = []

    def handler(request):
        calls.append(request)
        return response(context)

    instance = provider(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderInputBudgetError):
        await instance.analyze_evidence(
            contexts=[context], previous_analysis=previous,
            validation_feedback="Synthetic criterion conflict", input_token_limit=required - 1,
        )
    assert calls == []
