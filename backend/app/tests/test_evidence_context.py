from dataclasses import replace
from uuid import uuid4

import pytest

from app.agents.evidence_workflow import build_evidence_contexts, citation_for_source
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
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
