from uuid import uuid4

import pytest

from app.agents.contracts import validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.tests.test_evidence_scope import make_analysis, make_result
from app.tools.code_analyzer import ProjectFileSnapshot, find_evidence
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.requirement_versions import compare_requirements


@pytest.mark.parametrize("field", ["explanation", "information_gap", "suggestion"])
@pytest.mark.parametrize("citation", ["R2-E1", "R1-E99"])
def test_narrative_unknown_or_cross_requirement_citation_rejected(field, citation):
    result = make_result()
    context = build_evidence_contexts(result, max_evidence=1)
    analysis = make_analysis(result)
    validate_grounded_analysis(context, analysis)
    setattr(analysis.items[0], field, f"请核对 {citation} 中的材料")
    with pytest.raises(ValueError, match="prose contains"):
        validate_grounded_analysis(context, analysis)


def test_legal_narrative_and_structured_citations_agree():
    result = make_result()
    context = build_evidence_contexts(result, max_evidence=1)
    analysis = make_analysis(result)
    analysis.items[0].explanation = "R1-E1展示测试断言，运行尚未核验"
    validate_grounded_analysis(context, analysis)


def test_both_routes_reach_bounded_context_and_keep_old_path():
    files = [
        ProjectFileSnapshot(
            "version-old/app.py",
            'from fastapi import FastAPI\napp=FastAPI()\n@app.get("/events")\n'
            'def events():\n    return read()\n@app.post("/signup")\n'
            'def signup():\n    return save()\n',
        )
    ]
    routes = [e for e in find_evidence(files, "FastAPI") if e.evidence_type == "fastapi_route"]
    assert [e.line_start for e in routes] == [3, 6]
    result = match_candidate([RequirementInput(uuid4(), "活动和报名路由", "FastAPI", 5)], [], files)
    result = enrich_evidence(result, files)
    context = build_evidence_contexts(result, max_evidence=3)[0]
    assert sum(e.evidence_type == "fastapi_route" for e in context.evidence) == 2
    assert len(context.evidence) <= 3
    assert all(e.file_path.startswith("version-old/") for e in context.evidence)


def test_route_candidates_stay_bounded_in_large_file():
    source = "\n".join(
        f'@app.get("/{i}")\ndef route_{i}():\n    return read({i})\n' for i in range(30)
    )
    routes = [
        e
        for e in find_evidence([ProjectFileSnapshot("app.py", source)], "FastAPI")
        if e.evidence_type == "fastapi_route"
    ]
    assert len(routes) == 6
    assert "/29" in routes[-1].snippet


def req(**patch):
    return dict(id="a", title="实现接口", skill="FastAPI", weight=4, isRequired=True, **patch)


def test_requirement_versions_use_ids_and_all_decision_fields():
    a = req()
    b = {**req(), "id": "b"}
    assert compare_requirements([a, b], [b, a])["status"] == "same"
    for key, value in [
        ("title", "其他要求"),
        ("skill", "SQL"),
        ("weight", 3),
        ("isRequired", False),
    ]:
        assert compare_requirements([a], [{**a, key: value}])["status"] == "changed"
    assert compare_requirements([a], [a, b])["status"] == "changed"
    assert compare_requirements([a, b], [a])["status"] == "changed"
    old = {k: v for k, v in a.items() if k != "isRequired"}
    assert compare_requirements([old], [a]) == {
        "status": "unknown",
        "changes": [],
        "missingFields": ["是否必需"],
    }
    assert compare_requirements(None, [a])["status"] == "unknown"
