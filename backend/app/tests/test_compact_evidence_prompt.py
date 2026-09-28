import json

import httpx
import pytest

from app.agents.contracts import EvidenceAnalysis, validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import (
    ProviderInputBudgetError,
    conservative_input_token_estimate,
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

    assert payload == {"requirements": [context.model_dump()], "historicalContext": history}
    assert payload["requirements"][0]["evidence"][0]["snippet"] == snippet
    assert messages[1]["content"] == json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )
    assert len(messages[1]["content"]) < len(json.dumps(payload, ensure_ascii=False))
    assert sanitize_outgoing_messages(messages) == messages


def test_repair_omits_only_transport_metadata(context, previous):
    messages = repair_messages(context, previous)
    payload = json.loads(messages[1]["content"])
    assert payload["requirements"] == [context.model_dump()]
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
    assert json.loads(outgoing[1]["content"])["requirements"] == [context.model_dump()]


@pytest.mark.asyncio
async def test_compact_repair_fits_budget_that_rejected_legacy_payload(
    monkeypatch, context, previous,
):
    messages = repair_messages(context, previous)
    required = conservative_input_token_estimate(sanitize_outgoing_messages(messages))
    legacy_payload = json.loads(messages[1]["content"])
    legacy_payload["rejectedOutput"] = previous.model_dump()
    legacy_messages = [messages[0], {
        "role": "user", "content": json.dumps(legacy_payload, ensure_ascii=False),
    }]
    legacy_required = conservative_input_token_estimate(
        sanitize_outgoing_messages(legacy_messages)
    )
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
    required = conservative_input_token_estimate(sanitize_outgoing_messages(messages))
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
