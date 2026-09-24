"""Third-party examples remain inspectable without becoming personal practice evidence."""

import hashlib
from uuid import uuid4

from app.agents.contracts import (
    AIRating,
    AIRequirementAnalysis,
    CriterionDecision,
    EvidenceAnalysis,
    RetrievalToolCall,
    validate_grounded_analysis,
)
from app.agents.evidence_workflow import build_evidence_contexts, execute_retrieval_tool
from app.services.analysis import _retrieval_step_detail
from app.services.matching_materials import MatchMaterials, analyze_materials
from app.tools.evidence_levels import classify_evidence
from app.tools.matcher import RequirementInput


def _material(base, version: str, path: str, text: str) -> dict:
    data = text.encode("utf-8")
    storage = base / version / path
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_bytes(data)
    return {
        "versionId": version,
        "path": f"{version}/{path}",
        "storageKey": f"{version}/{path}",
        "hash": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def test_reference_source_is_citable_but_cannot_raise_personal_score(tmp_path) -> None:
    files = [
        _material(
            tmp_path,
            "public",
            "SOURCE.txt",
            "THIRD-PARTY PUBLIC SOURCE / SYNTHETIC TEST FIXTURE\nOriginal repository: example\n",
        ),
        _material(
            tmp_path,
            "public",
            "tests/test_api.py",
            "import pytest\n\ndef test_api():\n    assert 1 + 1 == 2\n",
        ),
    ]
    requirement = RequirementInput(uuid4(), "自动化测试实现与断言", "pytest", 5)
    materials = MatchMaterials("了解 pytest，但公开测试文件非本人编写。", files, [])

    result = analyze_materials([requirement], materials, tmp_path, enable_semantic=False)
    item = result.items[0]

    assert result.overall_score == 10
    assert item.verdict == "claimed_only"
    assert item.evidence is None
    assert item.evidence_list
    assert all(evidence.provenance == "reference" for evidence in item.evidence_list)
    assert any(step.get("referenceFileCount") == 2 for step in result.retrieval_steps)
    contexts = build_evidence_contexts(result)
    assert contexts[0].evidence[0].provenance == "reference"
    assert contexts[0].rating_ceiling is None
    assert classify_evidence(
        {"skill": "pytest", "evidenceList": [e.model_dump() for e in contexts[0].evidence]},
        item.verdict,
    )["evidence_level"] is None


def test_reference_citation_can_explain_example_but_not_support_rating(tmp_path) -> None:
    files = [
        _material(
            tmp_path,
            "public",
            "SOURCE.txt",
            "THIRD-PARTY PUBLIC SOURCE / SYNTHETIC TEST FIXTURE\n",
        ),
        _material(
            tmp_path,
            "public",
            "tests/test_api.py",
            "import pytest\n\ndef test_api():\n    assert 1 + 1 == 2\n",
        ),
    ]
    result = analyze_materials(
        [RequirementInput(uuid4(), "pytest 测试和断言", "pytest", 5)],
        MatchMaterials("", files, []),
        tmp_path,
        enable_semantic=False,
    )
    context = build_evidence_contexts(result)[0]
    citation = context.evidence[0].citation_id
    decisions = [
        CriterionDecision(criterion=criterion, supported=False, reason="个人材料未提供证据")
        for criterion in ("relevance", "operation", "task")
    ]
    item = AIRequirementAnalysis(
        requirement_id=context.requirement_id,
        explanation="第三方示例含测试片段，仅作学习参考。",
        citation_ids=[citation],
        information_gap="缺少本人编写的测试和运行记录。",
        suggestion="提交本人编写的测试文件、运行命令及日志。",
        confidence=0.6,
        rating=AIRating(level=None, reason="第三方示例不计个人实践", criteria=decisions),
    )
    validate_grounded_analysis(
        [context], EvidenceAnalysis(summary="仅有第三方示例。", items=[item], model="test")
    )
    item.rating = AIRating(
        level=1,
        reason="错误地用第三方示例评级",
        criteria=[
            CriterionDecision(
                criterion="relevance", supported=True, citation_ids=[citation], reason="存在代码"
            ),
            *decisions[1:],
        ],
    )
    try:
        validate_grounded_analysis(
            [context], EvidenceAnalysis(summary="仅有第三方示例。", items=[item], model="test")
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Third-party citation must not support a practice level")


def test_tool_retrieval_preserves_reference_provenance(tmp_path) -> None:
    files = [
        _material(
            tmp_path,
            "public",
            "SOURCE.txt",
            "THIRD-PARTY PUBLIC SOURCE / SYNTHETIC TEST FIXTURE\n",
        ),
        _material(
            tmp_path,
            "public",
            "tests/test_api.py",
            "import pytest\n\ndef test_one():\n    assert 1\n\n"
            "def test_two():\n    assert 2\n\n"
            "def test_three():\n    assert 3\n",
        ),
    ]
    result = analyze_materials(
        [RequirementInput(uuid4(), "pytest 测试和断言", "pytest", 5)],
        MatchMaterials("", files, []),
        tmp_path,
        enable_semantic=False,
    )
    assert len(result.items[0].evidence_list) > 1
    contexts = build_evidence_contexts(result, max_evidence=1)
    updated, event = execute_retrieval_tool(
        result,
        contexts,
        RetrievalToolCall(requirement_id=contexts[0].requirement_id, query="test_three"),
    )
    assert event["resultCount"] == 1
    assert updated[0].evidence[-1].provenance == "reference"
    assert updated[0].rating_ceiling is None


def test_metric_definition_is_reference_only_and_not_a_full_alerting_chain(tmp_path) -> None:
    files = [
        _material(
            tmp_path,
            "public",
            "SOURCE.txt",
            "THIRD-PARTY PUBLIC SOURCE / SYNTHETIC TEST FIXTURE\n",
        ),
        _material(
            tmp_path,
            "public",
            "prometheus_client/metrics.py",
            "class Counter(MetricWrapperBase):\n    def inc(self):\n        pass\n",
        ),
    ]
    result = analyze_materials(
        [RequirementInput(uuid4(), "监控指标、告警规则和处置流程", "监控告警", 5)],
        MatchMaterials("", files, []),
        tmp_path,
        enable_semantic=False,
    )
    assert result.overall_score == 0
    assert result.items[0].verdict == "gap"
    assert any(
        evidence.evidence_type == "metric_exposition"
        and evidence.provenance == "reference"
        for evidence in result.items[0].evidence_list
    )


def test_declared_reference_role_works_without_source_marker(tmp_path) -> None:
    files = [
        {
            **_material(
                tmp_path,
                "public",
                "tests/test_api.py",
                "import pytest\n\ndef test_api():\n    assert True\n",
            ),
            "materialRole": "reference",
        }
    ]
    result = analyze_materials(
        [RequirementInput(uuid4(), "pytest 测试", "pytest", 5)],
        MatchMaterials("", files, []),
        tmp_path,
        enable_semantic=False,
    )
    assert result.overall_score == 0
    assert result.items[0].evidence is None
    assert all(evidence.provenance == "reference" for evidence in result.items[0].evidence_list)


def test_personal_evidence_still_counts_when_reference_is_also_selected(tmp_path) -> None:
    files = [
        _material(
            tmp_path,
            "personal",
            "tests/test_owned.py",
            "import pytest\n\ndef test_owned():\n    assert 2 + 2 == 4\n",
        ),
        {
            **_material(
                tmp_path,
                "public",
                "tests/test_example.py",
                "import pytest\n\ndef test_example():\n    assert 1 + 1 == 2\n",
            ),
            "materialRole": "reference",
        },
    ]
    result = analyze_materials(
        [RequirementInput(uuid4(), "pytest 测试", "pytest", 5)],
        MatchMaterials("使用 pytest 编写测试。", files, []),
        tmp_path,
        enable_semantic=False,
    )
    item = result.items[0]
    assert item.verdict in {"supported", "partial"}
    assert item.evidence is not None
    assert item.evidence.provenance == "portfolio"
    assert any(evidence.provenance == "reference" for evidence in item.evidence_list)


def test_reference_audit_step_does_not_claim_context_failure() -> None:
    detail = _retrieval_step_detail(
        {"status": "excluded_from_personal_rating", "referenceFileCount": 12}
    )
    assert "12个第三方参考文件" in detail
    assert "不计入个人实践评级" in detail
    assert "失败" not in detail
