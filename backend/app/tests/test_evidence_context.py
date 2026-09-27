import ast
import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest

from app.agents.contracts import RetrievalToolCall
from app.agents.evidence_workflow import (
    build_evidence_contexts,
    citation_for_source,
    execute_retrieval_tool,
)
from app.tools.code_analyzer import CodeEvidence, ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence, retrieve_context
from app.tools.matcher import RequirementInput, match_candidate


@pytest.mark.parametrize(
    "skill,path,content,expected",
    [
        (
            "FastAPI",
            "app.py",
            "from fastapi import FastAPI\napp = FastAPI()\n"
            '@app.get("/health")\ndef health():\n    return {"ok": True}\n',
            'return {"ok": True}',
        ),
        (
            "pytest",
            "test_app.py",
            'def test_health():\n    assert health() == {"ok": True}\n',
            'assert health() == {"ok": True}',
        ),
        (
            "PostgreSQL",
            "db.py",
            "import psycopg\ndef find(conn: psycopg.Connection):\n"
            '    return conn.execute("SELECT id FROM tasks").fetchall()\n',
            "SELECT id FROM tasks",
        ),
    ],
)
def test_context_contains_actual_body_and_exact_source(skill, path, content, expected):
    files = [ProjectFileSnapshot(path, content)]
    result = match_candidate([RequirementInput(uuid4(), skill, skill, 5)], [], files)
    enriched = enrich_evidence(result, files)
    evidence = enriched.items[0].evidence
    assert expected in evidence.snippet
    assert evidence.context_complete
    assert evidence.snippet == "\n".join(
        content.splitlines()[evidence.line_start - 1 : evidence.line_end]
    )
    assert result.overall_score == enriched.overall_score
    assert build_evidence_contexts(enriched)[0].evidence[0].snippet == evidence.snippet


def test_empty_evidence_does_not_shift_citation_mapping():
    result = match_candidate(
        [RequirementInput(uuid4(), "FastAPI", "FastAPI", 5)],
        [],
        [ProjectFileSnapshot("app.py", 'app = FastAPI()\n@app.get("/")\ndef root(): pass')],
    )
    item = result.items[0]
    sources = [replace(item.evidence_list[0], snippet=""), item.evidence_list[1]]
    result = replace(result, items=[replace(item, evidence_list=sources)])
    context = build_evidence_contexts(result)[0]
    assert context.evidence[0].citation_id == "R1-E2"
    assert citation_for_source(context, sources[0]) is None
    assert citation_for_source(context, sources[1]) == "R1-E2"
    assert citation_for_source(None, sources[1]) is None


def test_large_function_is_bounded_and_explicitly_incomplete():
    file = ProjectFileSnapshot("app.py", "def large():\n" + "    x = 1\n" * 100)
    result = match_candidate([RequirementInput(uuid4(), "Python", "Python", 5)], [], [file])
    enriched = enrich_evidence(result, [file])
    evidence = enriched.items[0].evidence
    assert not evidence.context_complete
    assert evidence.line_end - evidence.line_start + 1 <= 40
    assert enriched.retrieval_steps[0]["rounds"] == 1
    assert evidence.snippet == "\n".join(file.content.splitlines()[:40])


def test_changed_source_cannot_become_a_verified_context():
    file = ProjectFileSnapshot("app.py", "def health():\n    return True\n")
    result = match_candidate([RequirementInput(uuid4(), "Python", "Python", 5)], [], [file])
    with pytest.raises(ValueError, match="hash mismatch"):
        enrich_evidence(result, [replace(file, content=file.content + "# changed")])


def anchor(file, start, end=None):
    end = start if end is None else end
    return CodeEvidence(
        skill="Python",
        evidence_type="python_function",
        file_path=file.path,
        line_start=start,
        line_end=end,
        snippet="\n".join(file.content.splitlines()[start - 1 : end]).strip()[:240],
        strength="medium",
        explanation="合成代码定位",
        content_hash=hashlib.sha256(file.content.encode("utf-8")).hexdigest(),
    )


@pytest.mark.parametrize("anchor_line", [41, 80, 101])
def test_late_function_anchor_keeps_bounded_surrounding_source(anchor_line):
    file = ProjectFileSnapshot("app.py", "def large():\n" + "    x = 1\n" * 99 + "    return x\n")
    evidence = retrieve_context(anchor(file, anchor_line), file, ast.parse(file.content))
    assert evidence.line_start <= anchor_line <= evidence.line_end
    assert evidence.line_end - evidence.line_start + 1 == 40
    assert evidence.snippet == "\n".join(
        file.content.splitlines()[evidence.line_start - 1 : evidence.line_end]
    )
    assert not evidence.context_complete
    assert "连续局部原文" in evidence.context_note


def test_character_clipping_preserves_multiline_anchor_and_nearby_return():
    file = ProjectFileSnapshot(
        "app.py",
        "def large():\n"
        + ("    value = '" + "x" * 600 + "'\n") * 12
        + "    if value:\n        return value\n    return None\n",
    )
    evidence = retrieve_context(anchor(file, 14, 15), file, ast.parse(file.content))
    assert evidence.line_start <= 14 and evidence.line_end >= 15
    assert "    return None" in evidence.snippet
    assert len(evidence.snippet) <= 4000
    assert evidence.snippet == "\n".join(
        file.content.splitlines()[evidence.line_start - 1 : evidence.line_end]
    )
    assert not evidence.context_complete


@pytest.mark.parametrize(
    "content,start,end",
    [
        ("def large():\n" + "    x = 1\n" * 42, 2, 42),
        ("def large():\n    value = '" + "x" * 4000 + "'\n", 2, 2),
    ],
)
def test_oversized_anchor_is_rejected_without_silently_dropping_lines(content, start, end):
    file = ProjectFileSnapshot("app.py", content)
    with pytest.raises(ValueError, match="anchor exceeds the context budget"):
        retrieve_context(anchor(file, start, end), file, ast.parse(content))


def test_indexed_tail_can_be_supplemented_without_claiming_complete_function():
    from evals.retrieval_context_cases import build_span_cases

    case = next(case for case in build_span_cases()["cases"] if case["id"] == "long_python")
    source = case["documents"][0]
    file = ProjectFileSnapshot(source["path"], source["content"])
    result = match_candidate([RequirementInput(uuid4(), "Python", "Python", 5)], [], [file])
    item = replace(result.items[0], evidence_list=[anchor(file, 1), anchor(file, 43)])
    enriched = enrich_evidence(replace(result, items=[item]), [file])
    contexts = build_evidence_contexts(enriched, max_evidence=1)
    updated, event = execute_retrieval_tool(
        enriched,
        contexts,
        RetrievalToolCall(requirement_id=contexts[0].requirement_id, query="rollback return"),
    )
    assert event["resultCount"] == 1
    assert event["scope"] == "current-upload-index"
    assert event["citationId"] == "R1-E2"
    assert len(updated[0].evidence) == 2
    assert "store.rollback()" in updated[0].evidence[-1].snippet
    assert "return {'order_id'" in updated[0].evidence[-1].snippet
    covered = set()
    for evidence in updated[0].evidence:
        assert not evidence.context_complete
        assert len(evidence.snippet) <= 4000
        assert evidence.line_end - evidence.line_start + 1 <= 40
        assert evidence.snippet == "\n".join(
            file.content.splitlines()[evidence.line_start - 1 : evidence.line_end]
        )
        covered.update(range(evidence.line_start, evidence.line_end + 1))
    assert covered == set(range(1, 46))
    assert updated[0].rating_ceiling <= 2
