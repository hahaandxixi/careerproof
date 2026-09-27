import json
from pathlib import Path

import pytest

from evals.retrieval_cases import build_cases
from evals.run_offline_retrieval_comparison import (
    aggregate,
    apply_annotations,
    load_corpus,
    measure,
)


def hit(path, start=1, end=1):
    return {"file_path": path, "line_start": start, "line_end": end, "sourceExact": True}


def test_cross_file_recall_cannot_be_inflated_by_duplicate_hits():
    gold = [
        {"path": "a.md", "lineStart": 1, "lineEnd": 1},
        {"path": "b.md", "lineStart": 2, "lineEnd": 2},
    ]
    repeated = measure([hit("a.md"), hit("a.md")], gold)
    assert repeated["recallAt2"] == 0.5
    assert not repeated["fullCoverageAt2"]
    complete = measure([hit("a.md"), hit("b.md", 1, 3)], gold)
    assert complete["recallAt2"] == 1 and complete["fullCoverageAt2"]
    assert measure([hit("b.md", 3, 3)], gold)["recallAt2"] == 0


def test_no_target_rate_and_missed_positive_are_separate():
    gold = [{"path": "a.md", "lineStart": 1, "lineEnd": 1}]
    rows = [
        {"metrics": measure([], gold), "hits": []},
        {"metrics": measure([hit("irrelevant.md")], []), "hits": [hit("irrelevant.md")]},
        {"metrics": measure([], []), "hits": []},
    ]
    result = aggregate(rows)
    assert result["positiveCases"] == 1 and result["noTargetCases"] == 2
    assert result["recallAt2"] == 0 and result["noTargetCandidateRate"] == 0.5
    assert aggregate([])["recallAt2"] is None


def test_frozen_corpus_has_valid_labels_and_is_not_independent():
    corpus, digest = load_corpus(Path(__file__).parents[2] / "evals" / "retrieval-corpus-v1.json")
    assert len(corpus["cases"]) == 64 and len(digest) == 64
    assert "pending" in corpus["annotationStatus"]
    assert sum(not c["gold"] for c in corpus["cases"]) == 20
    assert corpus == build_cases()


def test_invalid_gold_is_rejected_instead_of_silently_inflating_metrics(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text(
        '{"cases":[{"id":"a","documents":[],"gold":['
        '{"path":"missing.md","lineStart":1,"lineEnd":1}]}]}'
    )
    with pytest.raises(ValueError, match="Gold source"):
        load_corpus(path)
    path.write_text('{"cases":[]}')
    with pytest.raises(ValueError, match="at least one"):
        load_corpus(path)


def test_annotation_import_requires_explicit_complete_review_and_correct_sources(tmp_path):
    corpus = {
        "cases": [{"id": "one", "documents": [{"path": "a.md", "content": "text\n"}], "gold": []}]
    }
    path = tmp_path / "review.json"
    review = {"corpusHash": "frozen", "reviewer": "", "reviewedAt": "", "cases": []}
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="Reviewer"):
        apply_annotations(corpus, "frozen", path)
    review.update(
        reviewer="synthetic-test",
        reviewedAt="2026-09-26",
        cases=[
            {
                "id": "one",
                "noRelevantSource": False,
                "reason": "synthetic unit fixture",
                "relevantSources": [
                    {"path": "a.md", "lineStart": 1, "lineEnd": 2, "support": "describes_behavior"}
                ],
            }
        ],
    )
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="Invalid annotated source"):
        apply_annotations(corpus, "frozen", path)
    review["cases"][0]["relevantSources"][0]["lineEnd"] = 1
    path.write_text(json.dumps(review))
    annotated, metadata = apply_annotations(corpus, "frozen", path)
    assert annotated["cases"][0]["gold"] and corpus["cases"][0]["gold"] == []
    assert not metadata["identityVerified"]
    with pytest.raises(ValueError, match="hash"):
        apply_annotations(corpus, "changed", path)


def test_micro_and_macro_recall_remain_distinct_for_cross_file_queries():
    single = [{"path": "a.md", "lineStart": 1, "lineEnd": 1}]
    pair = [*single, {"path": "b.md", "lineStart": 1, "lineEnd": 1}]
    rows = [
        {"metrics": measure([hit("a.md")], single), "hits": [hit("a.md")]},
        {"metrics": measure([], pair), "hits": []},
    ]
    result = aggregate(rows)
    assert result["recallAt2"] == 0.5
    assert result["targetUnits"] == 3
    assert result["microRecallAt2"] == pytest.approx(1 / 3)


def test_live_retrieval_entry_uses_deepseek_without_network(monkeypatch):
    from pydantic import SecretStr

    from app.core.config import settings
    from evals import run_retrieval_comparison as live

    monkeypatch.setattr(settings, "ai_external_enabled", False)
    monkeypatch.setattr(settings, "ai_provider", "zhipu")
    monkeypatch.setattr(settings, "deepseek_api_key", SecretStr("synthetic-test-key"))
    sentinel = object()

    def factory():
        assert settings.ai_external_enabled
        assert settings.ai_provider == "deepseek"
        return sentinel

    monkeypatch.setattr(live, "get_ai_provider", factory)
    assert live.model_provider() is sentinel


def test_target_overlap_is_distinct_from_complete_context():
    gold = [{"path": "a.md", "lineStart": 2, "lineEnd": 5}]
    partial = measure([hit("a.md", 2, 2)], gold)
    assert partial["recallAt2"] == 1 and partial["fullCoverageAt2"]
    assert partial["spanRecallAt2"] == 0 and not partial["fullSpanCoverageAt2"]
    assert partial["meanTargetLineCoverageAt2"] == 0.25
    complete = measure([hit("a.md", 1, 10)], gold)
    assert complete["spanRecallAt2"] == 1 and complete["meanTargetLineCoverageAt2"] == 1


def test_full_span_uses_interval_union_and_only_top_two_hits():
    gold = [{"path": "a.md", "lineStart": 2, "lineEnd": 5}]
    adjacent = measure([hit("a.md", 2, 3), hit("a.md", 4, 5)], gold)
    assert adjacent["fullSpanCoverageAt2"]
    duplicate = measure([hit("a.md", 2, 3), hit("a.md", 2, 3)], gold)
    assert duplicate["meanTargetLineCoverageAt2"] == 0.5
    gap = measure([hit("a.md", 2, 2), hit("a.md", 4, 5)], gold)
    assert gap["meanTargetLineCoverageAt2"] == 0.75 and not gap["fullSpanCoverageAt2"]
    outside_top_two = measure([hit("a.md", 2, 3), hit("b.md", 4, 5), hit("a.md", 4, 5)], gold)
    assert outside_top_two["meanTargetLineCoverageAt2"] == 0.5
    assert measure([hit("b.md", 2, 5)], gold)["meanTargetLineCoverageAt2"] == 0


def test_macro_and_micro_full_span_coverage_keep_target_denominators():
    one = [{"path": "a.md", "lineStart": 1, "lineEnd": 2}]
    two = [*one, {"path": "b.md", "lineStart": 1, "lineEnd": 2}]
    rows = [
        {"metrics": measure([hit("a.md", 1, 2)], one), "hits": [hit("a.md", 1, 2)]},
        {"metrics": measure([hit("a.md", 1, 1)], two), "hits": [hit("a.md", 1, 1)]},
    ]
    result = aggregate(rows)
    assert result["spanRecallAt2"] == 0.5
    assert result["microSpanRecallAt2"] == pytest.approx(1 / 3)
    assert aggregate([])["spanRecallAt2"] is None


def test_frozen_multiline_context_set_is_valid_and_explicitly_provisional():
    import ast

    from evals.retrieval_context_cases import build_span_cases

    corpus, digest = load_corpus(
        Path(__file__).parents[2] / "evals" / "retrieval-context-span-v1.json"
    )
    assert corpus == build_span_cases() and len(corpus["cases"]) == 4 and len(digest) == 64
    assert "pending" in corpus["annotationStatus"]
    long_case = next(case for case in corpus["cases"] if case["id"] == "long_python")
    ast.parse(long_case["documents"][0]["content"])
    assert long_case["gold"][0]["lineEnd"] > 40
    assert all(gold["lineEnd"] > 1 for case in corpus["cases"] for gold in case["gold"])
