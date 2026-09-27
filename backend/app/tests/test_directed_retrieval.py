import hashlib
import io
import zipfile
from dataclasses import replace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.contracts import (
    AIRating,
    AIRequirementAnalysis,
    CriterionDecision,
    EvidenceAnalysis,
    ModelUsage,
    RetrievalToolCall,
)
from app.agents.evidence_workflow import build_evidence_contexts, run_evidence_workflow
from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.services.matching_materials import MatchMaterials, analyze_materials
from app.tests import test_real_matching as matching_fixture_module
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import create_job, match_report, upload_materials
from app.tests.test_reference_materials import _material
from app.tools.code_analyzer import FrozenRetrievalSource, ProjectFileSnapshot
from app.tools.directed_retrieval import (
    MAX_SCANNED_LINES,
    can_search_frozen_sources,
    search_frozen_sources,
)
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from evals.retrieval_context_cases import build_span_cases

directed_db = matching_fixture_module.matching_db


def long_file():
    case = next(case for case in build_span_cases()["cases"] if case["id"] == "long_python")
    source = case["documents"][0]
    return ProjectFileSnapshot(source["path"], source["content"])


def frozen(file):
    return FrozenRetrievalSource(file, hashlib.sha256(file.content.encode()).hexdigest())


def initial_result(file):
    result = match_candidate([RequirementInput(uuid4(), "Python业务处理", "Python", 5)], [], [file])
    result = enrich_evidence(result, [file])
    return replace(result, retrieval_sources=(frozen(file),))


def test_query_finds_previously_unindexed_tail_and_preserves_bounds():
    file = long_file()
    result = initial_result(file)
    shown = build_evidence_contexts(result)[0].evidence
    assert all(entry.line_end <= 40 for entry in shown)
    assert can_search_frozen_sources(result.retrieval_sources, shown)
    candidates, audit = search_frozen_sources(result.retrieval_sources, "rollback", "Python", shown)
    assert candidates and "store.rollback()" in candidates[0].snippet
    assert candidates[0].line_start == 6 and candidates[0].line_end == 45
    assert not candidates[0].context_complete
    assert candidates[0].content_hash == frozen(file).content_hash
    assert candidates[0].snippet == "\n".join(file.content.splitlines()[5:45])
    assert audit["scannedLines"] == 45 and audit["sourceExact"]


def test_changed_hash_refused_and_scan_budget_counts_nonmatching_lines():
    file = long_file()
    with pytest.raises(ValueError, match="hash mismatch"):
        search_frozen_sources(
            [replace(frozen(file), content_hash="0" * 64)], "rollback", "Python", []
        )
    file = ProjectFileSnapshot("many.txt", "irrelevant\n" * MAX_SCANNED_LINES + "rollback\n")
    candidates, audit = search_frozen_sources([frozen(file)], "rollback", "Python", [])
    assert candidates == []
    assert audit["scannedLines"] == MAX_SCANNED_LINES and audit["scanLimitReached"]


@pytest.mark.parametrize("query", ["api_key 密钥", "password", "身份证号码"])
def test_sensitive_query_is_rejected(query):
    with pytest.raises(ValueError, match="credentials or identifiers"):
        search_frozen_sources([frozen(long_file())], query, "Python", [])


def test_no_match_full_context_and_ignored_file_do_not_produce_evidence():
    result = initial_result(long_file())
    candidates, _ = search_frozen_sources(result.retrieval_sources, "unrelatedword", "Python", [])
    assert candidates == []
    source = frozen(ProjectFileSnapshot(".env", "rollback=secret"))
    assert not can_search_frozen_sources([source], [])
    assert search_frozen_sources([source], "rollback", "Python", [])[0] == []
    context = build_evidence_contexts(result)[0]
    context.evidence[0] = context.evidence[0].model_copy(update={"line_end": 45})
    assert not can_search_frozen_sources(result.retrieval_sources, context.evidence)


def test_only_selected_personal_text_enters_frozen_lookup(tmp_path):
    files = [
        _material(tmp_path, "owned", "app.py", long_file().content),
        {
            **_material(tmp_path, "reference", "example.py", long_file().content),
            "materialRole": "reference",
        },
        {
            **_material(tmp_path, "image", "ocr.txt", "rollback in screenshot"),
            "sourceModality": "image",
        },
    ]
    # A file on disk that wasn't selected must never be read by the lookup.
    _material(tmp_path, "unselected", "other.py", "rollback private_marker")
    result = analyze_materials(
        [RequirementInput(uuid4(), "Python业务处理", "Python", 5)],
        MatchMaterials("", files, []),
        tmp_path,
        enable_semantic=False,
    )
    assert [source.file.path for source in result.retrieval_sources] == ["owned/app.py"]
    # Later storage edits cannot alter an already verified in-memory task snapshot.
    (tmp_path / "owned" / "app.py").write_text("replacement secret_marker", encoding="utf-8")
    candidates, _ = search_frozen_sources(result.retrieval_sources, "rollback", "Python", [])
    assert all(candidate.file_path == "owned/app.py" for candidate in candidates)
    assert all(candidate.provenance == "portfolio" for candidate in candidates)
    assert "private_marker" not in repr(candidates)


class OfflinePlanner(DeepSeekProvider):
    def __init__(self, query="rollback"):
        super().__init__(
            api_key="offline-placeholder",
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout_seconds=1,
        )
        self.query = query
        self.rounds = 0

    async def plan_evidence_retrieval(self, *, contexts, **kwargs):
        self.rounds += 1
        if self.rounds > 1:
            return None
        return RetrievalToolCall(requirement_id=contexts[0].requirement_id, query=self.query)

    async def analyze_evidence(self, *, contexts, **kwargs):
        context = contexts[0]
        evidence = next(entry for entry in context.evidence if "store.rollback()" in entry.snippet)
        return EvidenceAnalysis(
            summary="材料中包含异常回滚调用，运行结果和本人贡献待核验。",
            model=self.model,
            usage=ModelUsage(),
            items=[
                AIRequirementAnalysis(
                    requirement_id=context.requirement_id,
                    explanation="原文包含回滚调用。",
                    citation_ids=[evidence.citation_id],
                    information_gap="未执行代码，需核验运行结果。",
                    suggestion="补充可核验的异常分支运行记录。",
                    confidence=0.5,
                    rating=AIRating(
                        level=1,
                        reason="补取候选仅用于定位与核对。",
                        criteria=[
                            CriterionDecision(
                                criterion="relevance",
                                supported=True,
                                citation_ids=[evidence.citation_id],
                                reason="原文包含所查询的回滚调用。",
                            ),
                            CriterionDecision(
                                criterion="operation",
                                supported=False,
                                reason="低强度候选未作为直接操作评级证据。",
                            ),
                            CriterionDecision(
                                criterion="task",
                                supported=False,
                                reason="上下文不完整，运行结果待核验。",
                            ),
                        ],
                    ),
                )
            ],
        )


def enable_offline_planner(monkeypatch, provider):
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "ai_local_fallback_enabled", True)
    monkeypatch.setattr("app.agents.evidence_workflow.get_ai_provider", lambda: provider)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "hash", "sensitive"])
async def test_planner_directed_lookup_and_failures_preserve_rule_result(monkeypatch, fault):
    result = initial_result(long_file())
    if fault == "hash":
        result = replace(
            result, retrieval_sources=(replace(result.retrieval_sources[0], content_hash="0" * 64),)
        )
    provider = OfflinePlanner(query="password" if fault == "sensitive" else "rollback")
    enable_offline_planner(monkeypatch, provider)
    outcome = await run_evidence_workflow(result)
    assert outcome.retrieval_result.overall_score == result.overall_score
    if fault:
        assert outcome.fallback_used and outcome.analysis is None
        assert outcome.tool_calls[-1]["status"] == "unavailable"
        return
    assert not outcome.fallback_used
    assert outcome.analysis.items[0].citation_ids
    assert outcome.tool_calls[0]["scope"] == "current-frozen-materials"
    assert outcome.tool_calls[0]["scannedLines"] == 45
    item = outcome.retrieval_result.items[0]
    cited = outcome.analysis.items[0].citation_ids[0]
    context = outcome.contexts[0]
    source = next(entry for entry in context.evidence if entry.citation_id == cited)
    assert any(entry.snippet == source.snippet for entry in item.evidence_list)
    assert context.rating_ceiling <= 2 and len(context.evidence) <= 3
    assert result.items[0].rule_base_score == item.rule_base_score


@pytest.mark.asyncio
async def test_directed_source_persists_and_other_owner_cannot_read(directed_db, monkeypatch):
    app, _ = directed_db
    file = long_file()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("src/order.py", file.content)
    monkeypatch.setattr("app.tests.test_real_matching.source_archive", lambda: buffer.getvalue())
    enable_offline_planner(monkeypatch, OfflinePlanner())
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as enterprise,
        AsyncClient(transport=transport, base_url="http://test") as student,
        AsyncClient(transport=transport, base_url="http://test") as other,
    ):
        await register(enterprise, "directed-hr@example.com")
        job = await create_job(enterprise)
        await register(student, "directed-owner@example.com", "student")
        await register(other, "directed-other@example.com", "student")
        resume, _, version = await upload_materials(student)
        report = await match_report(student, job, resume, version, externalAiConsent=True)
        assert report["analysisMode"] == "ai_evidence"
        assert report["aiToolCalls"][0]["scope"] == "current-frozen-materials"
        item = report["items"][0]
        cited = item["aiCitationIds"][0]
        evidence = next(entry for entry in item["evidenceList"] if entry["citationId"] == cited)
        assert "store.rollback()" in evidence["snippet"]
        assert evidence["projectVersionId"] == version["versionId"]
        assert evidence["sourceId"] and evidence["projectFileId"]
        assert evidence["snippet"] == "\n".join(
            file.content.splitlines()[evidence["lineStart"] - 1 : evidence["lineEnd"]]
        )
        url = f"/api/v1/match-reports/{report['id']}"
        assert (await student.get(url)).json()["data"] == report
        assert (await other.get(url)).status_code == 404
        assert (await enterprise.get(url)).status_code == 404
