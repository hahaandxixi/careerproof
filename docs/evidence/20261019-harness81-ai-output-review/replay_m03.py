"""Offline contract/display probe; never constructs a provider or writes a report."""

import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

os.environ["AI_EXTERNAL_ENABLED"] = "false"
os.environ["AI_PROVIDER"] = "mock"

from app.agents.contracts import EvidenceAnalysis, validate_grounded_analysis  # noqa: E402
from app.agents.evidence_workflow import build_evidence_contexts  # noqa: E402
from app.tools.code_analyzer import ProjectFileSnapshot  # noqa: E402
from app.tools.evidence_context import enrich_evidence  # noqa: E402
from app.tools.evidence_levels import classify_evidence  # noqa: E402
from app.tools.matcher import RequirementInput, match_candidate  # noqa: E402
from app.tools.resume_parser import parse_resume  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
PACK = ROOT / "docs/evidence/20261017-task70-semantic-review-packet"
CASE = "contradictory-return"

packet = json.loads((PACK / "current-smoke-preflight-20261018.json").read_text(encoding="utf-8"))
live = json.loads((PACK / "live-smoke-20261018-a.json").read_text(encoding="utf-8"))
case = next(row["syntheticInput"] for row in packet["cases"] if row["id"] == CASE)
saved = next(row["analysis"] for row in live["results"] if row["id"] == CASE)
files = [ProjectFileSnapshot(**item) for item in case["files"]]
matched = match_candidate(
    [RequirementInput(uuid5(NAMESPACE_URL, CASE), case["requirement"], case["skill"], 5)],
    parse_resume(case["resume"]), files,
)
contexts = build_evidence_contexts(enrich_evidence(matched, files), max_evidence=2)
original = EvidenceAnalysis.model_validate(saved)
validate_grounded_analysis(contexts, original)

snapshot = {
    "skill": contexts[0].skill,
    "evidenceList": [item.model_dump() for item in contexts[0].evidence],
    "ai": {"status": "validated", "rating": saved["items"][0]["rating"]},
}
display = classify_evidence(snapshot, contexts[0].verdict)
assert display["evidence_level"] is None
assert display["evidence_level_label"] == "AI 未确认相关实践证据"

# This is explicitly a counterfactual IN MEMORY, not a new model response.
counterfactual = original.model_copy(deep=True)
counterfactual.items[0].rating.criteria[0].supported = True
counterfactual.items[0].rating.criteria[0].reason = "函数签名仅作为待核对的相关线索。"
counterfactual.items[0].rating.level = 1
counterfactual.items[0].rating.reason = "仅有待核对的相关线索，未确认实质操作。"
validate_grounded_analysis(contexts, counterfactual)

result = {
    "case": CASE,
    "externalRequests": 0,
    "originalAcceptedByStructuralGroundingValidator": True,
    "negativeCriteriaWithCitationsAccepted": True,
    "originalDisplayLevel": display["evidence_level"],
    "originalDisplayLabel": display["evidence_level_label"],
    "counterfactualLevelOneStructurallyAccepted": True,
    "counterfactualIsNotModelOutput": True,
    "rubricRelevance": contexts[0].rating_rubric["criteria"]["relevance"],
    "semanticAccuracyOrHumanAcceptanceProved": False,
}
with Path(__file__).with_name("m03-offline-result.json").open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False))
