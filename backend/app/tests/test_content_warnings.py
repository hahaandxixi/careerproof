"""Offline phrase-hint contracts; these do not assert legal or policy judgments."""

from __future__ import annotations

import json

import pytest

from app.tools.content_warnings import (
    CATEGORIES,
    MAX_CHARACTERS,
    MAX_FILES,
    MAX_FINDINGS,
    MAX_PATH_CHARACTERS,
    scan_content_warnings,
)


@pytest.mark.parametrize(
    ("text", "category", "rule_id"),
    [
        ("裸聊请加微信联系", "sexual_solicitation", "sexual.contact_solicitation"),
        ("我要杀了你", "abuse_threat", "abuse.targeted_threat"),
        ("你这个废物", "abuse_threat", "abuse.targeted_insult"),
        ("应聘成功后入职前先交押金", "recruitment_fraud", "recruitment.upfront_fee"),
        ("兼职刷单日结返佣", "recruitment_fraud", "recruitment.order_rebate"),
        ("稳赚不赔，私聊联系我", "spam", "spam.guaranteed_income_contact"),
    ],
)
def test_explicit_phrases_produce_only_located_hints(text, category, rule_id):
    report = scan_content_warnings([("resume.txt", text)])

    assert report["warningOnly"] is True
    assert report["truncated"] is False
    assert report["findings"] == [
        {"category": category, "ruleId": rule_id, "path": "resume.txt", "line": 1}
    ]
    assert report["counts"] == {key: int(key == category) for key in CATEGORIES}


@pytest.mark.parametrize(
    "text",
    [
        "张同学，本科计算机专业。使用 Python、SQL 开发校园报名系统，负责异常处理与行为测试。",
        (
            "def kill(pid): pass\nsex = 'not collected'\n"
            "DELETE FROM sessions;\n# 色情内容过滤与反诈测试"
        ),
        "入职后公司提供培训，不收取费用。负责支付接口、押金退款与安全风控。",
        "裸聊内容应被过滤。微信通知模块另行开发。\n招聘\n先交押金",
    ],
)
def test_ordinary_resume_code_and_unconnected_terms_are_not_single_word_hits(text):
    report = scan_content_warnings([("project/service.py", text)])

    assert report["findings"] == []
    assert not report["truncated"]


def test_quoted_filtering_example_is_a_hint_never_a_block_or_verdict():
    text = 'def test_reject_fraud():\n    assert detect("招聘先交押金")'
    report = scan_content_warnings([("tests/test_filter.py", text)])

    assert report["findings"][0]["line"] == 2
    assert report["warningOnly"] is True
    assert "blocked" not in report
    assert "violation" not in report


def test_nfkc_casefold_preserves_original_crlf_line_location_and_paths():
    path = "项目Ａ/tests.py"
    text = "普通说明\r\n\r\nＩ ＷＩＬＬ ＫＩＬＬ ＹＯＵ\r\nGUARANTEED PROFIT, CONTACT ME"
    report = scan_content_warnings([(path, text)])

    assert [(item["path"], item["line"]) for item in report["findings"]] == [
        (path, 3),
        (path, 4),
    ]
    assert report["scannedCharacters"] == len(text)


def test_same_rule_repeated_on_one_line_counts_once_but_other_lines_count_separately():
    report = scan_content_warnings([("a.txt", "我要杀了你，我要杀了你\n我要杀了你")])

    assert report["counts"]["abuse_threat"] == 2
    assert [item["line"] for item in report["findings"]] == [1, 2]


def test_file_limit_marks_partial_scan_and_never_reads_more_source_text():
    report = scan_content_warnings(
        [("first.txt", "正常简历"), ("unscanned.txt", "我要杀了你")], max_files=1
    )

    assert report["findings"] == []
    assert report["truncated"] is True
    assert report["truncationReasons"] == ["file_limit"]
    assert report["scannedFiles"] == 1
    assert report["scannedCharacters"] == 4


def test_character_limit_only_checks_prefix_and_reports_original_character_count():
    report = scan_content_warnings([("a.txt", "普通\n我要杀了你")], max_characters=5)

    assert report["findings"] == []
    assert report["truncated"] is True
    assert report["truncationReasons"] == ["character_limit"]
    assert report["scannedCharacters"] == 5


def test_exact_character_and_file_limits_can_be_complete_when_no_input_remains():
    report = scan_content_warnings([("a.txt", "普通")], max_files=1, max_characters=2)

    assert report["truncated"] is False
    assert report["scannedCharacters"] == 2


def test_finding_limit_is_conservatively_partial_and_counts_only_emitted_hints():
    report = scan_content_warnings([("a.txt", "我要杀了你\n招聘先交押金")], max_findings=1)

    assert len(report["findings"]) == 1
    assert report["truncated"] is True
    assert report["truncationReasons"] == ["finding_limit"]
    assert sum(report["counts"].values()) == 1
    assert report["scannedCharacters"] == len("我要杀了你\n")


def test_long_path_is_not_truncated_into_an_incorrect_locator_or_returned_unbounded():
    report = scan_content_warnings([("p" * (MAX_PATH_CHARACTERS + 1), "我要杀了你")])

    assert report["findings"] == []
    assert report["truncated"] is True
    assert report["truncationReasons"] == ["path_length_limit"]
    assert report["scannedFiles"] == 0
    assert report["scannedCharacters"] == 0


def test_report_is_json_serializable_has_no_source_excerpt_and_does_not_mutate_inputs():
    text = "PRIVATE-SOURCE-ONLY 裸聊加微信 UNIQUE-CONTACT-DETAIL"
    sources = [("resume.txt", text)]
    original = list(sources)
    report = scan_content_warnings(sources)
    serialized = json.dumps(report, ensure_ascii=False)

    assert sources == original
    assert "PRIVATE-SOURCE-ONLY" not in serialized
    assert "UNIQUE-CONTACT-DETAIL" not in serialized
    assert "裸聊" not in serialized
    assert "微信" not in serialized
    assert set(report["findings"][0]) == {"category", "ruleId", "path", "line"}


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("max_files", 0),
        ("max_files", MAX_FILES + 1),
        ("max_characters", MAX_CHARACTERS + 1),
        ("max_findings", MAX_FINDINGS + 1),
        ("max_findings", True),
    ],
)
def test_callers_cannot_remove_or_increase_hard_limits(keyword, value):
    with pytest.raises(ValueError, match=keyword):
        scan_content_warnings([], **{keyword: value})


def test_empty_iterable_is_complete_and_has_all_categories():
    report = scan_content_warnings(iter(()))

    assert report["findings"] == []
    assert report["counts"] == dict.fromkeys(CATEGORIES, 0)
    assert report["truncated"] is False
    assert report["scannedFiles"] == report["scannedCharacters"] == 0
