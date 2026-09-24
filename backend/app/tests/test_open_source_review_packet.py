"""The external review packet must show sources without preloading the expected answer."""

from evals.build_open_source_review_packet import build_packet


def test_review_packet_shows_cited_source_but_not_expected_boundary() -> None:
    packet = build_packet(
        {
            "mode": "real-ai",
            "suite": "synthetic",
            "promptVersion": "v1",
            "generatedAt": "2026-09-24T00:00:00Z",
            "cases": [
                {
                    "caseId": "case-1",
                    "job": "测试",
                    "sourceRepo": "public/example",
                    "sourceCommit": "abc123",
                    "expectedBoundary": "PRIVATE ANSWER KEY",
                    "ai": {
                        "fallbackUsed": False,
                        "analysis": {
                            "summary": "材料有一个参考测试。",
                            "items": [
                                {
                                    "requirement_id": "r1",
                                    "citation_ids": ["R1-E1"],
                                    "explanation": "R1-E1 含断言。",
                                    "information_gap": "未见运行记录。",
                                    "suggestion": "提供测试报告。",
                                    "rating": {
                                        "level": None,
                                        "reason": "第三方参考",
                                        "criteria": [],
                                    },
                                }
                            ],
                        },
                        "contexts": [
                            {
                                "requirement_id": "r1",
                                "requirement_title": "pytest 断言",
                                "verdict": "claimed_only",
                                "claim_text": "会用 pytest",
                                "evidence": [
                                    {
                                        "citation_id": "R1-E1",
                                        "file_path": "tests/test_a.py",
                                        "line_start": 1,
                                        "line_end": 2,
                                        "provenance": "reference",
                                        "context_complete": True,
                                        "snippet": "def test_a():\n    assert True",
                                    },
                                    {
                                        "citation_id": "R1-E2",
                                        "file_path": "tests/test_b.py",
                                        "line_start": 1,
                                        "line_end": 2,
                                        "provenance": "reference",
                                        "context_complete": True,
                                        "snippet": "UNCITED SOURCE",
                                    },
                                ],
                            }
                        ],
                    },
                }
            ],
        }
    )
    assert "R1-E1" in packet
    assert "assert True" in packet
    assert "归属 `reference`" in packet
    assert "PRIVATE ANSWER KEY" not in packet
    assert "UNCITED SOURCE" not in packet
    assert "评审签名：____________" in packet
