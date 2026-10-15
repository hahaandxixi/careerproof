from uuid import uuid4

from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import SkillClaim


def test_matcher_is_deterministic_and_evidence_based() -> None:
    requirement = RequirementInput(uuid4(), "掌握FastAPI接口开发", "Python", 5)
    claims = [SkillClaim("Python", "熟悉Python开发")]
    files = [
        ProjectFileSnapshot(
            "app/main.py",
            "from fastapi import FastAPI\n\ndef create_app():\n    return FastAPI()\n",
        )
    ]

    first = match_candidate([requirement], claims, files)
    second = match_candidate([requirement], claims, files)

    assert first == second
    assert first.overall_score == 65
    assert first.items[0].verdict == "supported"
    assert first.items[0].evidence is not None
    assert first.items[0].evidence.file_path == "app/main.py"
    assert first.items[0].evidence.content_hash
    assert first.items[0].formula_version == "evidence-v4"
    assert "材料支持度" in first.summary


def test_missing_evidence_is_not_invented() -> None:
    requirement = RequirementInput(uuid4(), "掌握Redis", "Redis", 5)

    result = match_candidate([requirement], [], [])

    assert result.overall_score == 0
    assert result.items[0].verdict == "gap"
    assert result.items[0].evidence is None
    assert "无法确认" in result.items[0].explanation
