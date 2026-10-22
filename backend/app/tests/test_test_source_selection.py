"""Exercise detection -> expansion -> actual prompt, without a model or database."""

import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest

from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import evidence_analysis_messages
from app.tools.code_analyzer import ProjectFileSnapshot, find_evidence
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate


def _test_candidates(content, path="tests/test_orders.py"):
    return [e for e in find_evidence([ProjectFileSnapshot(path, content)], "pytest")
            if e.evidence_type == "pytest_test"]


def test_separate_functions_survive_and_a_stub_cannot_borrow_next_assertion():
    content = (
        "def test_stub():\n    pass\n\n"
        "def test_create():\n    assert create() == 201\n\n"
        "def test_duplicate():\n    assert create() == 409\n"
    )
    candidates = _test_candidates(content)
    assert [e.line_start for e in candidates] == [4, 7]
    assert all(e.content_hash == hashlib.sha256(content.encode()).hexdigest() for e in candidates)


def test_assertion_must_belong_to_test_and_raises_is_an_assertion():
    content = (
        "import pytest\n"
        "def test_nested_helper_only():\n"
        "    def helper():\n        assert False\n"
        "    helper()\n\n"
        "async def test_error():\n"
        "    with pytest.raises(ValueError):\n        await create()\n\n"
        "class TestOrders:\n"
        "    def test_read(self):\n        assert read()\n"
    )
    assert [e.line_start for e in _test_candidates(content)] == [7, 12]


def test_large_test_file_is_bounded_without_always_dropping_the_tail():
    content = "\n".join(f"def test_case_{i}():\n    assert check({i})\n" for i in range(30))
    candidates = _test_candidates(content)
    assert 2 <= len(candidates) <= 6
    assert candidates[0].line_start == 1
    assert candidates[-1].snippet == "def test_case_29():"


def files_with_output():
    return [
        ProjectFileSnapshot("tests/test_orders.py", (
            "import pytest\n\n@pytest.fixture\ndef database():\n    return connect()\n\n"
            "def test_create(database):\n    assert create(database) == 201\n\n"
            "def test_duplicate(database):\n    assert create(database) == 409\n"
        )),
        ProjectFileSnapshot("pyproject.toml", '[project]\ndependencies = ["pytest"]\n'),
        ProjectFileSnapshot("runtime/pytest-output.txt", (
            "pytest tests/test_orders.py\n"
            "tests/test_orders.py .. [100%]\n\n"
            "2 passed in 0.10s\n"
        )),
    ]


@pytest.mark.parametrize("cap", [1, 2, 3])
def test_real_prompt_retains_tests_and_uploaded_output_with_existing_cap(cap):
    files = files_with_output()
    result = match_candidate([RequirementInput(uuid4(), "pytest行为测试", "pytest", 1)], [], files)
    enriched = enrich_evidence(result, files)
    context = build_evidence_contexts(enriched, max_evidence=cap)[0]
    assert len(context.evidence) == cap
    assert context.evidence[0].evidence_type == "pytest_test"
    if cap > 1:
        output = context.evidence[-1]
        assert output.file_path == "runtime/pytest-output.txt"
        assert "2 passed" in output.snippet
        assert output.evidence_type == "retrieved_context" and output.strength == "low"
    if cap == 3:
        assert [e.evidence_type for e in context.evidence] == [
            "pytest_test", "pytest_test", "retrieved_context",
        ]
        assert "assert create(database) == 409" in context.evidence[1].snippet
    for evidence in context.evidence:
        source = next(f.content for f in files if f.path == evidence.file_path)
        assert evidence.snippet == "\n".join(
            source.splitlines()[evidence.line_start - 1:evidence.line_end]
        )
    prompt = evidence_analysis_messages([context])[1]["content"]
    assert "assert create(database) == 201" in prompt
    if cap > 1:
        assert "2 passed" in prompt
    assert result.items[0].rule_base_score == enriched.items[0].rule_base_score == 0.65


def test_output_survives_twelve_source_cap_and_does_not_raise_score():
    files = files_with_output()
    files.extend(ProjectFileSnapshot(f"tests/test_more_{i}.py", (
        "def test_more():\n    assert check()\n"
    )) for i in range(20))
    requirement = RequirementInput(uuid4(), "pytest行为测试", "pytest", 1)
    result = match_candidate([requirement], [], files)
    enriched = enrich_evidence(result, files)
    assert len(enriched.items[0].evidence_list) <= 12
    context = build_evidence_contexts(enriched)[0]
    assert any(e.file_path == "runtime/pytest-output.txt" for e in context.evidence)
    output_only = match_candidate([requirement], [], [files[2]])
    assert output_only.items[0].rule_base_score == 0
    assert output_only.items[0].verdict == "gap"


def test_reference_tests_cannot_displace_personal_tests_or_output():
    files = files_with_output()
    reference = [
        ProjectFileSnapshot("vendor/test_reference.py", "def test_ref():\n    assert True\n")
    ]
    result = match_candidate(
        [RequirementInput(uuid4(), "pytest行为测试", "pytest", 1)], [], files,
        reference_files=reference,
    )
    enriched = enrich_evidence(result, [*files, *reference])
    context = build_evidence_contexts(enriched)[0]
    assert all(e.provenance == "portfolio" for e in context.evidence)


def test_other_skills_preserve_source_order_and_citation_identity():
    files = [ProjectFileSnapshot(
        "service.py", "def find(db):\n    return db.execute('SELECT id FROM jobs')\n",
    )]
    result = match_candidate([RequirementInput(uuid4(), "SQL查询", "SQL", 1)], [], files)
    enriched = enrich_evidence(result, files)
    # Keep a deliberately unusual order to detect unintended global reordering.
    sources = list(reversed(enriched.items[0].evidence_list))
    enriched = replace(enriched, items=[replace(enriched.items[0], evidence_list=sources)])
    context = build_evidence_contexts(enriched)[0]
    assert [(e.file_path, e.line_start, e.snippet) for e in context.evidence] == [
        (e.file_path, e.line_start, e.snippet) for e in sources[:3]
    ]


@pytest.mark.parametrize("statement", [
    "pytest.raises(ValueError)",
    "unused = pytest.raises(ValueError)",
    "pytest.raises(ValueError, match='invalid')",
    "pytest.raises(ValueError, None)",
])
def test_unused_raises_factory_is_not_test_implementation(statement):
    content = f"import pytest\ndef test_empty():\n    {statement}\n"
    assert _test_candidates(content) == []


@pytest.mark.parametrize("statement", [
    "with pytest.raises(ValueError):\n        reject()",
    "pytest.raises(ValueError, reject)",
    "caught = pytest.raises(ValueError, service.reject, 1, strict=True)",
    "pytest.raises(ValueError, lambda: reject())",
    "assert reject() == 400",
])
def test_raises_context_and_function_forms_remain_candidates(statement):
    content = f"import pytest\ndef test_reject():\n    {statement}\n"
    assert [e.line_start for e in _test_candidates(content)] == [2]
