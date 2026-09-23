from uuid import uuid4

from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.hybrid_retrieval import lexical_terms, retrieve_requirement_candidates
from app.tools.matcher import RequirementInput, match_candidate


def test_code_aware_terms_split_identifiers_and_keep_chinese_bigrams():
    terms = lexical_terms("订单重试 retryOrder PostgreSQL")

    assert {"订单", "重试", "retry", "order", "postgresql"} <= terms


def test_hybrid_retrieval_finds_source_exact_context_for_uncovered_requirement():
    files = [
        ProjectFileSnapshot(
            "app/worker.py",
            "def retry_order(order_id):\n    return order_queue.retry(order_id)\n",
        ),
        ProjectFileSnapshot("app/users.py", "def list_users():\n    return []\n"),
    ]

    candidates = retrieve_requirement_candidates("实现订单重试处理", "retry_order", files)

    assert candidates
    assert candidates[0].file_path == "app/worker.py"
    assert candidates[0].line_start in {1, 2}
    assert candidates[0].evidence_type == "retrieved_context"
    assert candidates[0].strength == "low"


def test_comment_only_skill_name_is_not_retrieved():
    files = [ProjectFileSnapshot("app/cache.py", "# Redis cache\ndef health():\n    return True\n")]

    assert retrieve_requirement_candidates("掌握Redis缓存", "Redis", files) == []


def test_retrieved_context_enriches_ai_input_without_raising_rule_score():
    requirement = RequirementInput(uuid4(), "实现订单重试处理", "retry_order", 5)
    files = [
        ProjectFileSnapshot(
            "app/worker.py",
            "def retry_order(order_id):\n    return order_queue.retry(order_id)\n",
        )
    ]

    result = match_candidate([requirement], [], files)

    assert result.overall_score is None
    assert result.items[0].verdict == "unsupported"
    assert result.items[0].rule_base_score == 0
    assert result.items[0].evidence_list[0].evidence_type == "retrieved_context"
    assert result.retrieval_steps[0] == {
        "name": "混合检索补充候选上下文",
        "engine": "hybrid-lexical-v1",
        "candidateCount": 2,
        "changesRuleScore": False,
        "semanticEmbedding": False,
    }


def test_detector_evidence_remains_strongest_and_scoring_source():
    requirement = RequirementInput(uuid4(), "使用FastAPI开发接口", "FastAPI", 5)
    files = [
        ProjectFileSnapshot(
            "app/main.py",
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    return {'ok': True}\n",
        )
    ]

    result = match_candidate([requirement], [], files)

    assert result.items[0].verdict == "supported"
    assert result.items[0].rule_base_score == 0.65
    assert result.items[0].evidence is not None
    assert result.items[0].evidence.evidence_type == "fastapi_route"
