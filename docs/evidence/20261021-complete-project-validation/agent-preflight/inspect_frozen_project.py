"""Offline request sizing and an operator-chosen real retrieval, never a model run."""
from dataclasses import fields, replace
import hashlib
import json
from pathlib import Path
from uuid import UUID
import zipfile

import httpx

from app.agents.contracts import RetrievalToolCall
from app.agents.evidence_workflow import (
    build_evidence_contexts, eligible_retrieval_contexts, execute_retrieval_tool,
)
from app.agents.provider import DeepSeekProvider
from app.core.config import settings
from app.tools.code_analyzer import CodeEvidence, FrozenRetrievalSource, ProjectFileSnapshot
from app.tools.directed_retrieval import search_frozen_sources
from app.tools.evidence_context import source_key
from app.tools.matcher import MatchItemResult, MatchResult

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).parent
BASE = EVIDENCE.parent
report_path = BASE / "growth-runtime/report-after.json"
report = json.loads(report_path.read_text(encoding="utf-8"))
manifest = json.loads((BASE / "growth-runtime/v2-manifest.json").read_text(encoding="utf-8"))
assert hashlib.sha256(Path(manifest["zip"]).read_bytes()).hexdigest() == manifest["sha256"]
names = {field.name for field in fields(CodeEvidence)}


def evidence(row, skill):
    aliases = {"evidence_type": "evidenceType", "file_path": "filePath", "line_start": "lineStart",
               "line_end": "lineEnd", "content_hash": "contentHash", "context_complete": "contextComplete",
               "context_note": "contextNote", "function_line_start": "functionLineStart",
               "function_line_end": "functionLineEnd", "source_line_count": "sourceLineCount"}
    values = {name: row[aliases.get(name, name)] for name in names if aliases.get(name, name) in row}
    return CodeEvidence(**{**values, "skill": skill})


items = []
for item in report["items"]:
    rows = [evidence(row, item["skill"]) for row in item["evidenceList"]]
    items.append(MatchItemResult(
        requirement_id=UUID(item["requirementId"]), requirement_title=item["requirementTitle"],
        skill=item["skill"], claimed=item["claimed"], claim_text=item["claimText"],
        evidence=rows[0] if item.get("evidence") and rows else None, evidence_list=rows,
        verdict=item["verdict"], ai_confidence=item["aiConfidence"], rule_base_score=item["ruleBaseScore"],
        weight=item["weight"], final_score=item["finalScore"], explanation=item["explanation"],
        formula_version=item["formulaVersion"],
    ))
version = next(material["id"] for material in report["materials"] if material["kind"] == "project")
with zipfile.ZipFile(manifest["zip"]) as archive:
    bodies = {name: archive.read(name) for name in archive.namelist()}
frozen = tuple(FrozenRetrievalSource(ProjectFileSnapshot(version + "/" + name, body.decode("utf-8")),
                                    hashlib.sha256(body).hexdigest()) for name, body in bodies.items())
result = MatchResult(report.get("overallScore"), items, report["gaps"], report["claimedOnly"],
                     report["summary"], retrieval_sources=frozen)
contexts = build_evidence_contexts(result, max_evidence=2)
eligible = eligible_retrieval_contexts(result, contexts)
network_calls = []


def forbidden(request):
    network_calls.append(str(request.url))
    raise AssertionError("No HTTP request permitted during this offline inspection")


# The provider is used only for its real pure input estimator, not completion.
provider = DeepSeekProvider(api_key="offline-estimation-not-a-real-key", base_url="https://api.deepseek.com",
                            model="deepseek-flash", timeout_seconds=1,
                            transport=httpx.MockTransport(forbidden), max_attempts=1)
before_bound = provider.estimate_evidence_input(contexts)
sql_context = next(context for context in contexts if context.skill == "SQL")
query = "storage.py transaction connection.rollback"
directed, search_detail = search_frozen_sources(frozen, query, sql_context.skill, sql_context.evidence)
# Mirror the frozen-source branch immediately before execute_retrieval_tool.
# This is individual production-helper inspection, not a whole Agent execution.
expanded_items = []
for item in result.items:
    if str(item.requirement_id) != sql_context.requirement_id:
        expanded_items.append(item)
        continue
    merged = list(item.evidence_list)
    existing = {source_key(row) for row in merged}
    for candidate in directed:
        if source_key(candidate) not in existing:
            merged.append(candidate)
            existing.add(source_key(candidate))
    assert len(merged) <= 12  # No eviction branch needed for this fixed project.
    expanded_items.append(replace(item, evidence_list=merged))
result = replace(result, items=expanded_items)
updated, event = execute_retrieval_tool(result, contexts, RetrievalToolCall(
    requirement_id=sql_context.requirement_id, query=query,
))
after_context = next(context for context in updated if context.skill == "SQL")
assert event["status"] == "completed" and len(after_context.evidence) == len(sql_context.evidence) + 1
added = after_context.evidence[-1]
selected_name = next(name for name in bodies if added.file_path == version + "/" + name)
raw = bodies[selected_name].decode("utf-8").splitlines()
assert added.snippet == "\n".join(raw[added.line_start - 1:added.line_end])
after_bound = provider.estimate_evidence_input(updated)
assert network_calls == []
output = {
    "reportId": report["id"], "reconstructedFromSavedRuleEvidence": True,
    "materialVersionId": version, "materialZipSha256": manifest["sha256"],
    "requirements": [{"id": context.requirement_id, "skill": context.skill,
                       "initialSources": [{"citationId": source.citation_id, "path": source.file_path,
                                           "start": source.line_start, "end": source.line_end}
                                          for source in context.evidence],
                       "hasRetrievalSpace": context in eligible} for context in contexts],
    "operatorQuery": query, "toolResult": event, "addedSource": added.model_dump(mode="json"),
    "directedSearchDetail": search_detail,
    "selectedContainsTransactionRollback": "connection.rollback()" in added.snippet,
    "individualProductionHelpersNotWholeWorkflowExecution": True,
    "notAModelChoice": True, "noModelResponseFabricated": True, "reportsWritten": 0,
    "httpRequests": 0, "liveAuthorizationProvided": False,
    "realProviderConservativeInputUpperBoundBeforeTool": before_bound,
    "realProviderConservativeInputUpperBoundAfterTool": after_bound,
    "configuredReportInputLimit": settings.ai_per_report_input_token_limit,
    "configuredReportOutputLimit": settings.ai_per_report_output_token_limit,
    "configuredToolRoundLimit": settings.ai_max_retrieval_calls,
    "initialFinalPromptFitsInputLimit": before_bound <= settings.ai_per_report_input_token_limit,
    "afterToolFinalPromptFitsInputLimit": after_bound <= settings.ai_per_report_input_token_limit,
    "fixedThreeCaseGuardCompatibleWithFiveRequirements": False,
    "legacyAuthorizationApplicable": False,
}
(EVIDENCE / "result.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("OFFLINE ONLY: real tool located", added.file_path, added.line_start, added.line_end)
print("Input upper bounds:", before_bound, "->", after_bound,
      "; report limit", settings.ai_per_report_input_token_limit)
print("No HTTP requests, model decisions, generated answers or database writes.")
