"""Synthetic credential privacy at all text-generation boundaries; no real API."""

import copy
import json

import httpx
import pytest

from app.agents.contracts import AIRequirementAnalysis, EvidenceAnalysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import _redact_external_value, evidence_analysis_messages
from app.tests.test_ai_evidence_workflow import evidenced_result
from app.tests.test_deepseek_provider import provider
from app.tools.credential_redaction import MARKER

PRIVATE = "synthetic private password with tail"


def synthetic_analysis(context, summary):
    return EvidenceAnalysis(
        summary=summary,
        model="synthetic",
        items=[
            AIRequirementAnalysis(
                requirement_id=context.requirement_id,
                explanation="材料包含路由声明，运行情况待核验。",
                citation_ids=[context.evidence[0].citation_id],
                confidence=0.2,
            )
        ],
    )


@pytest.mark.parametrize("case", ["assignment", "structured", "known_token", "uri", "quoted_tail"])
def test_external_value_filters_credentials_without_mutating_sources(case):
    secret = PRIVATE
    if case == "structured":
        raw = {"credentials": {"api_key": secret}, "citation_id": "R1-E1"}
    elif case == "known_token":
        secret = "s" + "k" + "-" + "Synthetic1234567890example"
        raw = {"snippet": "unlabeled " + secret}
    elif case == "uri":
        secret = "synthetic-db-password"
        raw = {"dsn": "postgresql://user:" + secret + "@localhost/db"}
    elif case == "quoted_tail":
        raw = {"snippet": 'PASSWORD="' + secret + " "}
    else:
        raw = {
            "file_path": "app.py",
            "snippet": 'PASSWORD="' + secret + '"',
            "citation_id": "R1-E1",
        }
    original = copy.deepcopy(raw)
    safe = _redact_external_value(raw)
    assert secret not in json.dumps(safe) and MARKER in json.dumps(safe)
    assert raw == original
    if "citation_id" in raw:
        assert safe["citation_id"] == raw["citation_id"]


@pytest.mark.parametrize(
    "source",
    [
        'password: str = "' + PRIVATE + '"',
        'api_key: str | None = "' + PRIVATE + '"',
        'def login(password: str = "' + PRIVATE + '"):\n    return password',
        "def login(password: str):\n    return password",
        'token: list[str] = ["' + PRIVATE + '"]',
    ],
)
def test_python_credential_annotations_and_defaults_are_handled(source):
    safe = _redact_external_value({"file_path": "auth.py", "snippet": source})["snippet"]
    assert PRIVATE not in safe
    assert source.split("=")[0].strip() in safe


@pytest.mark.parametrize(
    "entry",
    ["current", "history", "repair", "auxiliary", "summary", "planning", "transport", "multimodal"],
)
async def test_transport_never_sends_synthetic_text_credentials(entry):
    contexts = build_evidence_contexts(evidenced_result())
    context = contexts[0]
    assignment = 'PASSWORD="' + PRIVATE + '"'
    original_contexts = contexts
    raw_contexts = [c.model_dump() for c in original_contexts]
    bitmap = "data:image/png;base64,13800138000AABBCC"
    captured = []

    async def handler(request):
        payload = json.loads(request.content)
        captured.append(payload)
        assert PRIVATE not in json.dumps(payload)
        assert request.headers["Authorization"] == "Bearer synthetic-deepseek-key"
        if entry == "multimodal":
            assert payload["messages"][0]["content"][1]["image_url"]["url"] == bitmap
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                synthetic_analysis(context, "合成摘要").model_dump(
                                    exclude={"model", "usage"}
                                )
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
        )

    model = provider(transport=httpx.MockTransport(handler), max_attempts=1)
    if entry in {"current", "history", "repair"}:
        kwargs = {}
        if entry == "current":
            contexts = [context.model_copy(update={"requirement_title": assignment})]
        elif entry == "history":
            model.history_context = {"items": [{"snippet": assignment}]}
        else:
            kwargs = {
                "validation_feedback": assignment,
                "previous_analysis": synthetic_analysis(context, assignment),
            }
        await model.analyze_evidence(contexts=contexts, **kwargs)
    elif entry == "auxiliary":
        await model.generate_bounded_json(system="Synthetic", data={"password": PRIVATE})
    elif entry == "summary":
        await model.summarize_match(
            deterministic_summary=assignment, job_title="合成岗位", candidate_name="不外发姓名"
        )
    elif entry == "planning":
        await model.plan_evidence_retrieval(
            contexts=contexts,
            history_available=True,
            history_hint={"memo": assignment},
            previous_retrieval={"snippet": assignment},
        )
    else:
        content = (
            assignment
            if entry == "transport"
            else [
                {"type": "text", "text": assignment},
                {"type": "image_url", "image_url": {"url": bitmap}},
            ]
        )
        request = {"model": "deepseek-flash", "messages": [{"role": "user", "content": content}]}
        original = copy.deepcopy(request)
        await model._completion(request)
        assert request == original
    assert captured and [c.model_dump() for c in original_contexts] == raw_contexts


def test_prompt_builder_filters_repair_text_even_without_network():
    contexts = build_evidence_contexts(evidenced_result())
    prompt = evidence_analysis_messages(
        contexts,
        validation_feedback='TOKEN="' + PRIVATE + '"',
        previous_analysis=synthetic_analysis(contexts[0], 'PASSWORD="' + PRIVATE + '"'),
    )
    assert PRIVATE not in json.dumps(prompt)


@pytest.mark.parametrize(
    "source",
    [
        'password = ["' + PRIVATE + '", "synthetic second secret"]',
        'api_key = dict(token="' + PRIVATE + '", password="synthetic second secret")',
        'def login(token="' + PRIVATE + '"):\n    return token',
        'password: str = "' + PRIVATE + " \\\n",
        'password: list[str] = [\n    "' + PRIVATE + '",\n    "synthetic second secret",\n]\n',
    ],
)
def test_python_default_collections_and_partial_literals_are_filtered(source):
    safe = _redact_external_value({"filePath": "auth.py", "snippet": source})["snippet"]
    assert PRIVATE not in safe and "synthetic second secret" not in safe
    assert safe.count("\n") == source.count("\n")


def test_tool_arguments_and_encoded_text_are_filtered_without_mutation():
    from app.agents.provider import sanitize_outgoing_messages

    raw = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "search_evidence",
                        "arguments": json.dumps(
                            {"query": 'PASSWORD="' + PRIVATE + '"', "password": {"nested": PRIVATE}}
                        ),
                    },
                }
            ],
        },
        {"role": "tool", "content": json.dumps({"api_key": [PRIVATE]})},
    ]
    original = copy.deepcopy(raw)
    safe = sanitize_outgoing_messages(raw)
    assert PRIVATE not in json.dumps(safe) and raw == original
    assert safe[0]["tool_calls"][0]["id"] == "call-1"
    assert safe[0]["tool_calls"][0]["function"]["name"] == "search_evidence"


def test_mcp_metadata_restore_never_unmasks_structural_credentials():
    from app.services.mcp_tools import sanitize_export

    report_id = "f1234567-1234-4321-9876-abcdef123456"
    raw = {
        "reportId": report_id,
        "password": {"reportId": report_id, "secret": PRIVATE},
        "authorization": [PRIVATE],
    }
    original = copy.deepcopy(raw)
    safe = sanitize_export(raw)
    assert safe["reportId"] == report_id
    assert safe["password"] == safe["authorization"] == MARKER
    assert PRIVATE not in json.dumps(safe) and raw == original
