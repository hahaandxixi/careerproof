import hashlib
from uuid import uuid4

import pytest

from app.services.matching_materials import MatchMaterials, analyze_materials
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.semantic_retrieval import load_local_model, retrieve_semantic_candidates


class MeaningOnlyEmbedder:
    def embed(self, documents):
        for text in documents:
            if "事务一致性" in text or "撤销库存扣减" in text:
                yield [1.0, 0.0]
            else:
                yield [0.0, 1.0]


def test_semantic_paraphrase_adds_source_exact_candidate_without_scoring(tmp_path):
    requirement = RequirementInput(uuid4(), "保证事务一致性", "事务一致性", 5)
    files = [
        ProjectFileSnapshot(
            "project/README.md",
            "订单写入失败时撤销库存扣减，两个变更要么一起成功，要么都不生效。\n",
        ),
        ProjectFileSnapshot("project/worker.py", "def save_order():\n    pass\n"),
    ]
    semantic, scanned = retrieve_semantic_candidates(
        [requirement], files, MeaningOnlyEmbedder()
    )
    result = enrich_evidence(
        match_candidate([requirement], [], files, semantic_candidates=semantic), files
    )

    assert scanned == 1
    assert result.items[0].verdict == "unsupported"
    assert result.items[0].rule_base_score == 0
    assert result.items[0].evidence_list[0].evidence_type == "semantic_document_candidate"
    assert "撤销库存扣减" in result.items[0].evidence_list[0].snippet
    assert result.items[0].evidence_list[0].file_path == "project/README.md"
    assert result.items[0].evidence_list[0].line_start == 1


def test_unrelated_document_and_code_stub_do_not_become_semantic_hits():
    requirement = RequirementInput(uuid4(), "保证事务一致性", "事务一致性", 5)
    files = [
        ProjectFileSnapshot(
            "project/README.md", "本项目负责市场活动策划、社群内容维护和线下品牌宣传。\n"
        ),
        ProjectFileSnapshot("project/worker.py", "def save_order():\n    pass\n"),
    ]

    semantic, scanned = retrieve_semantic_candidates(
        [requirement], files, MeaningOnlyEmbedder()
    )

    assert scanned == 1
    assert semantic == {}


def test_absent_local_model_does_not_attempt_runtime_download(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_local_model(tmp_path)


def test_worker_uses_semantic_documents_and_preserves_rule_score(tmp_path, monkeypatch):
    content = "订单写入失败时撤销库存扣减，两个变更要么一起成功，要么都不生效。\n".encode()
    (tmp_path / "source.md").write_bytes(content)
    materials = MatchMaterials(
        resume_text="姓名：演示学生",
        files=[
            {
                "storageKey": "source.md",
                "hash": hashlib.sha256(content).hexdigest(),
                "path": "project/README.md",
            }
        ],
        snapshots=[],
    )
    monkeypatch.setattr(
        "app.services.matching_materials.load_local_model", lambda _: MeaningOnlyEmbedder()
    )
    requirement = RequirementInput(uuid4(), "保证事务一致性", "事务一致性", 5)

    result = analyze_materials([requirement], materials, tmp_path)

    assert result.items[0].verdict == "unsupported"
    assert result.items[0].rule_base_score == 0
    assert result.items[0].evidence_list[0].evidence_type == "semantic_document_candidate"
    assert result.retrieval_steps[-1]["status"] == "active"
    assert result.retrieval_steps[-1]["semanticEmbedding"] is True


def test_worker_falls_back_to_lexical_when_model_unavailable(tmp_path, monkeypatch):
    content = "订单写入失败时撤销库存扣减，两个变更要么一起成功，要么都不生效。\n".encode()
    (tmp_path / "source.md").write_bytes(content)
    materials = MatchMaterials(
        resume_text="姓名：演示学生",
        files=[
            {
                "storageKey": "source.md",
                "hash": hashlib.sha256(content).hexdigest(),
                "path": "project/README.md",
            }
        ],
        snapshots=[],
    )

    def unavailable(_):
        raise FileNotFoundError("missing")

    monkeypatch.setattr("app.services.matching_materials.load_local_model", unavailable)
    requirement = RequirementInput(uuid4(), "保证事务一致性", "事务一致性", 5)

    result = analyze_materials([requirement], materials, tmp_path)

    assert result.items[0].verdict == "unsupported"
    assert result.retrieval_steps[-1]["status"] == "unavailable"
    assert result.retrieval_steps[-1]["semanticEmbedding"] is False
