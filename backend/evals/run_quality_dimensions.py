"""Offline three-dimension AI quality evaluation: citations, suggestions, changes.

Every golden label lives in quality-dimensions-cases.json and was authored
before this runner; the runner only replays synthetic inputs through
production paths (matcher/enrich/build_evidence_contexts,
validate_grounded_analysis, report_comparison.compare_views) and compares
results with the frozen labels. It never creates a provider, never uses the
network, never executes uploaded code, and never touches a database.

Repeat runs are byte-identical except the generatedAt timestamp. No-source
cases are counted in their own metric and never as citation successes, and
the absent independent semantic review keeps semanticQualityPassRate null.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import NAMESPACE_URL, uuid5

from app.agents import contracts as contracts_module
from app.agents import evidence_workflow
from app.agents.contracts import EvidenceAnalysis, validate_grounded_analysis
from app.schemas.analysis import CareerTaskPlan, CodeEvidenceView, ReportMaterial
from app.services import report_comparison
from app.services.report_comparison import compare_views
from app.tools import evidence_context, function_coverage, matcher, resume_parser, task_boundaries
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume

SUITE = "quality-dimensions-v2"
DEFAULT_CASES = Path(__file__).with_name("quality-dimensions-cases.json")
PROBE_MODEL = "authored-quality-dimensions-probe"
NEUTRAL_EXPLANATION = "当前规则提供材料线索，执行结果、本人贡献及其他范围仍需人工核验。"
NEUTRAL_GAP = "执行结果、本人贡献及未展示材料仍需核对。"
NEUTRAL_SUGGESTION = "针对本项要求补充具名材料并人工核对。"


def _normalized_path(path: str) -> str:
    return path.replace("\\", "/")


def _requirement_uuid(case_id: str, title: str):
    return uuid5(NAMESPACE_URL, f"{SUITE}:{case_id}:requirement:{title}")


def _key_uuid(case_id: str, kind: str, key: str):
    return uuid5(NAMESPACE_URL, f"{SUITE}:{case_id}:{kind}:{key}")


def _snapshots(files: list[dict]) -> list[ProjectFileSnapshot]:
    rows = [ProjectFileSnapshot(**row) for row in files]
    if len(rows) != len({_normalized_path(row.path) for row in rows}):
        raise ValueError("duplicate normalized file paths in synthetic case")
    return rows


def build_contexts(
    case_id: str, resume: str, requirements: list[dict], files: list[dict],
    reference_files: list[dict] | None = None,
):
    """Run the production retrieval pipeline over synthetic frozen inputs."""
    personal = _snapshots(files)
    references = _snapshots(reference_files or [])
    inputs = [
        RequirementInput(
            _requirement_uuid(case_id, requirement["title"]),
            requirement["title"], requirement["skill"], requirement["weight"],
        )
        for requirement in requirements
    ]
    result = enrich_evidence(
        match_candidate(
            inputs, parse_resume(resume), personal,
            reference_files=references or None,
        ),
        [*personal, *references],
    )
    contexts = evidence_workflow.build_evidence_contexts(result)
    explanations = [item.explanation for item in result.items]
    content_by_path = {
        (_normalized_path(file.path), provenance): file.content
        for provenance, snapshots in (("portfolio", personal), ("reference", references))
        for file in snapshots
    }
    retrieved_hashes = {
        (_normalized_path(evidence.file_path), evidence.provenance,
         evidence.line_start, evidence.line_end, evidence.snippet): evidence.content_hash
        for item in result.items for evidence in item.evidence_list
    }
    source_count = 0
    exact = bool(contexts)
    for context in contexts:
        for source in context.evidence:
            source_count += 1
            content = content_by_path.get((_normalized_path(source.file_path), source.provenance))
            if content is None:
                exact = False
                continue
            lines = content.splitlines()
            expected = "\n".join(lines[source.line_start - 1:source.line_end]).strip()
            if (not 1 <= source.line_start <= source.line_end <= len(lines)
                    or retrieved_hashes.get((
                        _normalized_path(source.file_path), source.provenance,
                        source.line_start, source.line_end, source.snippet,
                    )) != hashlib.sha256(content.encode("utf-8")).hexdigest()
                    or source.snippet.strip() != expected):
                exact = False
    if not source_count:
        exact = False
    return contexts, exact, source_count, explanations


def resolve_selector(selector: dict, contexts, previous_contexts=None) -> str:
    """Map an authored citation selector to a report-local citation id."""
    if selector["kind"] == "fabricated":
        return selector["citationId"]
    pool = contexts if selector["kind"] == "source" else previous_contexts
    if pool is None:
        raise ValueError("previous-generation contexts missing for selector")
    context = pool[selector["reqIndex"]]
    for evidence in context.evidence:
        if _normalized_path(evidence.file_path) != _normalized_path(selector["path"]):
            continue
        if selector.get("snippetContains") and selector["snippetContains"] not in evidence.snippet:
            continue
        provenance = selector.get("provenance")
        if provenance and evidence.provenance != provenance:
            continue
        return evidence.citation_id
    raise ValueError(
        f"selector resolved to nothing: {selector} (context evidence: "
        + ", ".join(
            f"{evidence.citation_id}:{evidence.file_path}:{evidence.provenance}"
            for evidence in context.evidence
        )
        + ")"
    )


def citation_analysis(contexts, citation_rows: list[list[str]]) -> EvidenceAnalysis:
    """Neutral envelope: only the citation ids differ per requirement."""
    return EvidenceAnalysis(
        summary="离线合成引用边界探针，不是模型输出或独立质量评定。",
        model=PROBE_MODEL,
        items=[
            {
                "requirement_id": context.requirement_id,
                "explanation": NEUTRAL_EXPLANATION,
                "citation_ids": ids,
                "information_gap": NEUTRAL_GAP,
                "suggestion": NEUTRAL_SUGGESTION,
                "confidence": 0,
                "rating": {
                    "level": None,
                    "reason": "引用边界探针不作语义评级。",
                    "criteria": [
                        {
                            "criterion": key, "supported": False, "citation_ids": [],
                            "reason": "引用边界探针不作语义评级。",
                        }
                        for key in ("relevance", "operation", "task")
                    ],
                },
            }
            for context, ids in zip(contexts, citation_rows, strict=True)
        ],
    )


def plan_analysis(context, draft: dict) -> EvidenceAnalysis:
    """Neutral envelope around one authored task-plan draft, like the old suite."""
    citations = [
        evidence.citation_id for evidence in context.evidence
        if evidence.provenance == "portfolio"
    ] if context.verdict in {"supported", "partial"} else []
    return EvidenceAnalysis(
        summary="离线合成建议可操作性探针，不是模型输出或独立质量评定。",
        model=PROBE_MODEL,
        items=[{
            "requirement_id": context.requirement_id,
            "explanation": NEUTRAL_EXPLANATION,
            "citation_ids": citations,
            "information_gap": NEUTRAL_GAP,
            "suggestion": NEUTRAL_SUGGESTION,
            "task_plan": {
                "deliverable": draft["deliverable"],
                "steps": draft["steps"],
                "acceptance_checks": draft.get(
                    "acceptanceChecks", draft.get("acceptance_checks", [])
                ),
            },
            "confidence": 0,
            "rating": {
                "level": None,
                "reason": "建议探针不作语义评级。",
                "criteria": [
                    {
                        "criterion": key, "supported": False, "citation_ids": [],
                        "reason": "建议探针不作语义评级。",
                    }
                    for key in ("relevance", "operation", "task")
                ],
            },
        }],
    )


def validate(contexts, analysis: EvidenceAnalysis) -> dict:
    try:
        validate_grounded_analysis(contexts, analysis)
    except ValueError as error:
        return {"accepted": False, "error": str(error)}
    return {"accepted": True, "error": None}


def evaluate_citation_case(case: dict) -> dict:
    contexts, exact, source_count, explanations = build_contexts(
        case["id"], case["resume"], case["requirements"], case["files"],
        case.get("referenceFiles"),
    )
    verdicts = [context.verdict for context in contexts]
    verdict_ok = verdicts == case["expectedVerdicts"]
    marker = case.get("expectedExplanationContains")
    explanation_ok = marker is None or any(marker in text for text in explanations)
    previous_contexts = None
    if "previous" in case:
        previous_contexts, _, _, _ = build_contexts(
            case["id"], case["previous"]["resume"],
            case["previous"]["requirements"], case["previous"]["files"],
        )
    rows = []
    for draft in case["drafts"]:
        try:
            row_ids = [
                [
                    resolve_selector(selector, contexts, previous_contexts)
                    for selector in group
                ]
                for group in draft["cites"]
            ]
        except ValueError as error:  # fixture wiring bug, never a gold outcome
            rows.append({
                "draftId": draft["id"],
                "expectedContractRejection": draft["expectedContractRejection"],
                "accepted": None, "error": f"selector-unresolved: {error}",
                "expectationMatched": False, "goldReason": draft["goldReason"],
            })
            continue
        result = validate(contexts, citation_analysis(contexts, row_ids))
        invariants = {}
        for name, expected in (draft.get("goldInvariants") or {}).items():
            if name == "verdictStaysGap":
                invariants[name] = {
                    "expected": expected, "observed": all(
                        context.verdict == "gap" for context in contexts
                    ),
                }
            elif name == "ratingLevelStaysNull":
                invariants[name] = {
                    "expected": expected,
                    "observed": all(context.rating_ceiling is None for context in contexts),
                }
            elif name == "citedReferenceIsNotPersonal":
                cited = [
                    evidence for context in contexts for evidence in context.evidence
                    if evidence.citation_id in {
                        citation_id for group in row_ids for citation_id in group
                    }
                ]
                invariants[name] = {
                    "expected": expected,
                    "observed": bool(cited)
                    and all(entry.provenance == "reference" for entry in cited),
                }
            elif name == "sourceCountZero":
                invariants[name] = {
                    "expected": expected, "observed": source_count == 0,
                }
            else:
                raise ValueError(f"unknown gold invariant: {name}")
        invariants_ok = all(
            row["observed"] is row["expected"] for row in invariants.values()
        )
        expected_rejection = draft["expectedContractRejection"]
        matched = (
            result["accepted"] is not expected_rejection
            and invariants_ok
        )
        rows.append({
            "draftId": draft["id"], "expectedContractRejection": expected_rejection,
            "accepted": result["accepted"], "error": result["error"],
            "resolvedCitationIds": row_ids,
            "expectationMatched": matched, "goldReason": draft["goldReason"],
            "goldInvariants": invariants,
        })
    return {
        "id": case["id"], "narrative": case["narrative"],
        "verdictsObserved": verdicts, "verdictsExpected": case["expectedVerdicts"],
        "verdictExpectationMatched": verdict_ok,
        "explanationMarkerMatched": explanation_ok,
        "sourceExact": exact, "sourceCheck": (
            "no-sources" if not source_count else "verified" if exact else "mismatch"
        ),
        "sourceCount": source_count,
        "drafts": rows,
    }


def evaluate_suggestion_case(case: dict) -> dict:
    contexts, exact, source_count, _ = build_contexts(
        case["id"], case["resume"], [case["requirement"]], case["files"],
        case.get("referenceFiles"),
    )
    context = contexts[0]
    probes = [(
        "reference", None, case["referenceDraft"], False,
    ), *[
        (bad["id"], bad["defectClass"], bad["draft"], bad["expectedContractRejection"])
        for bad in case["knownBadDrafts"]
    ]]
    rows = []
    for probe_id, defect_class, draft, expected_rejection in probes:
        result = validate(contexts, plan_analysis(context, draft))
        rows.append({
            "probeId": probe_id, "defectClass": defect_class,
            "expectedContractRejection": expected_rejection,
            "accepted": result["accepted"], "error": result["error"],
            "expectationMatched": result["accepted"] is not expected_rejection,
        })
    operability = case["referenceDraft"]["operabilityGold"]
    return {
        "id": case["id"], "gapCategory": case["gapCategory"],
        "narrative": case["narrative"],
        "verdictObserved": context.verdict,
        "sourceCheck": (
            "no-sources" if not source_count else "verified" if exact else "mismatch"
        ),
        "operabilityGold": operability,
        "probes": rows,
    }


def _evidence_view(case_id: str, item_key: str, row: dict) -> CodeEvidenceView:
    return CodeEvidenceView.model_validate({
        "citation_id": row["citationId"], "provenance": row["provenance"],
        "context_complete": row["contextComplete"],
        "function_line_start": row["functionLineStart"],
        "function_line_end": row["functionLineEnd"],
        "skill": "FastAPI", "evidence_type": "fastapi_route",
        "file_path": row["filePath"], "line_start": row["lineStart"],
        "line_end": row["lineEnd"], "snippet": row["snippet"],
        "strength": "high", "explanation": "合成比较证据",
        "content_hash": row["contentHash"],
    })


def _item_ns(case_id: str, row: dict) -> NS:
    plan = CareerTaskPlan(
        deliverable=row["plan"]["deliverable"], steps=row["plan"]["steps"],
        acceptance_checks=row["plan"]["acceptanceChecks"],
    ) if row.get("plan") else None
    return NS(
        requirement_id=_key_uuid(case_id, "req", row["key"]),
        requirement_title=row["title"],
        evidence_list=[
            _evidence_view(case_id, row["key"], evidence)
            for evidence in row["evidence"]
        ],
        formula_version="evidence-v3",
        evidence_level_version="practice-evidence-v2",
        confirmation_status=None, reviewer_note=None,
        ai_status=row.get("aiStatus", "validated"),
        evidence_level=row.get("evidenceLevel"),
        ai_explanation=row.get("explanation"),
        ai_information_gap=row.get("gap"),
        ai_suggestion=row.get("suggestion"),
        ai_task_plan=plan,
        ai_task_plan_warning=row.get("taskPlanWarning"),
        ai_suggestion_redundant=row.get("suggestionRedundant", False),
    )


def _view_ns(case_id: str, view_id: str, spec: dict) -> NS:
    return NS(
        id=_key_uuid(case_id, "report", view_id),
        job_id=_key_uuid(case_id, "job", spec["jobId"]),
        candidate_id="student-synthetic",
        materials=[
            ReportMaterial(
                kind=material["kind"],
                id=_key_uuid(case_id, "mat", material["key"]),
                title=material["title"],
                version_number=material["versionNumber"],
                content_hash=material["contentHash"],
            )
            for material in spec["materials"]
        ],
        evidence_context_version="c1", ai_model="synthetic",
        analysis_mode="ai_evidence", ai_fallback_used=False,
        items=[_item_ns(case_id, row) for row in spec["items"]],
    )


def _snapshot(case_id: str, spec: dict) -> dict:
    return {"requirements": [
        {
            "id": str(_key_uuid(case_id, "req", row["key"])),
            "weight": row["weight"], "title": next(
                item["title"] for item in spec["items"] if item["key"] == row["key"]
            ),
        }
        for row in spec["snapshot"]["requirements"]
    ]}


def _check_signal(signal: dict, diff, replay: dict | None) -> dict:
    kind = signal["kind"]
    item = diff.items[0]
    if kind == "no-requirement-change":
        observed = (
            "requirement" not in item.changes
            and "requirements" not in diff.context_changes
        )
    elif kind == "no-evidence-change":
        observed = "evidence" not in item.changes
    elif kind == "level-unchanged":
        observed = item.base_level == item.target_level
    elif kind == "added-evidence-complete-fields":
        observed = bool(item.added_evidence) and all(
            entry.file_path and entry.content_hash
            and isinstance(entry.line_start, int) and isinstance(entry.line_end, int)
            for entry in item.added_evidence
        )
    elif kind == "target-gap-text":
        observed = item.target_information_gap == signal["expect"]
    elif kind == "limitation-contains":
        observed = any(
            signal["text"] in limitation for limitation in diff.limitations
        )
    elif kind == "provenance-flip-detected":
        observed = (
            bool(item.added_evidence) and bool(item.removed_evidence)
            and item.removed_evidence[0].provenance == "portfolio"
            and item.added_evidence[0].provenance == "reference"
            and item.added_evidence[0].file_path == item.removed_evidence[0].file_path
        )
    elif kind == "same-citation-id-content-diff-detected":
        observed = (
            bool(item.added_evidence) and bool(item.removed_evidence)
            and item.added_evidence[0].citation_id
            == item.removed_evidence[0].citation_id
            and item.added_evidence[0].content_hash
            != item.removed_evidence[0].content_hash
            and "evidence" in item.changes
        )
    elif kind == "old-citation-rejected":
        observed = replay is not None and replay["accepted"] is False
    else:
        raise ValueError(f"unknown attribution signal: {kind}")
    return {"kind": kind, "observed": observed}


def _replay_old_citations(case_id: str, replay_spec: dict) -> dict:
    """Replay an old report's items/citations against the new requirement set.

    The old analysis covers both old requirements; the new context only has
    the surviving one, so the contract must reject the replay outright rather
    than letting stale citation ids silently re-bind.
    """
    old_contexts, _, _, _ = build_contexts(
        f"{case_id}:old", replay_spec["resume"],
        replay_spec["oldRequirements"], replay_spec["oldFiles"],
    )
    new_contexts, _, _, _ = build_contexts(
        f"{case_id}:new", replay_spec["resume"],
        replay_spec["newRequirements"], replay_spec["newFiles"],
    )
    ids_per_requirement = [
        [resolve_selector(selector, old_contexts) for selector in group]
        for group in replay_spec["oldCites"]
    ]
    analysis = EvidenceAnalysis(
        summary="离线合成旧引用重放探针，不是模型输出或独立质量评定。",
        model=PROBE_MODEL,
        items=[
            {
                "requirement_id": context.requirement_id,
                "explanation": NEUTRAL_EXPLANATION,
                "citation_ids": ids,
                "information_gap": NEUTRAL_GAP,
                "suggestion": NEUTRAL_SUGGESTION,
                "confidence": 0,
                "rating": {
                    "level": None,
                    "reason": "旧引用重放探针不作语义评级。",
                    "criteria": [
                        {
                            "criterion": key, "supported": False, "citation_ids": [],
                            "reason": "旧引用重放探针不作语义评级。",
                        }
                        for key in ("relevance", "operation", "task")
                    ],
                },
            }
            for context, ids in zip(old_contexts, ids_per_requirement, strict=True)
        ],
    )
    result = validate(new_contexts, analysis)
    return {
        "oldCitationIds": ids_per_requirement, "accepted": result["accepted"],
        "error": result["error"],
        "newRequirementIds": [context.requirement_id for context in new_contexts],
        "newAllowedIds": [
            evidence.citation_id for context in new_contexts
            for evidence in context.evidence
        ],
    }


def evaluate_change_case(case: dict) -> dict:
    base_spec = case["base"]
    target_spec = copy.deepcopy(base_spec) if "clone" in case["target"] else case["target"]
    base = _view_ns(case["id"], "base", base_spec)
    target = _view_ns(case["id"], "target", target_spec)
    replay = (
        _replay_old_citations(case["id"], case["oldCitationReplay"])
        if "oldCitationReplay" in case else None
    )
    diff = compare_views(
        base, target, _snapshot(case["id"], base_spec),
        _snapshot(case["id"], target_spec),
        allow_job_change=case.get("allowJobChange", False),
    )
    gold = case["gold"]
    items_by_key = {item.requirement_id: item for item in diff.items}
    ordered = [
        items_by_key[_key_uuid(case["id"], "req", row["key"])]
        for row in target_spec["items"]
    ]
    change_type_ok = (
        diff.context_changes == gold["contextChanges"]
        and [item.changes for item in ordered] == gold["itemChanges"]
        and [len(item.added_evidence) for item in ordered] == gold["addedEvidenceCounts"]
        and [len(item.removed_evidence) for item in ordered] == gold["removedEvidenceCounts"]
    )
    signals = [
        _check_signal(signal, diff, replay) for signal in gold["attributionSignals"]
    ]
    remaining_gap_ok = True
    if gold["remainingGapExpect"] is not None:
        remaining_gap_ok = ordered[0].target_information_gap == gold["remainingGapExpect"]
    return {
        "id": case["id"], "changeGroup": case["changeGroup"],
        "narrative": case["narrative"], "attribution": gold["attribution"],
        "contextChanges": diff.context_changes,
        "itemChanges": [item.changes for item in ordered],
        "addedEvidenceCounts": [len(item.added_evidence) for item in ordered],
        "removedEvidenceCounts": [len(item.removed_evidence) for item in ordered],
        "targetInformationGaps": [item.target_information_gap for item in ordered],
        "changeTypeExpectationMatched": change_type_ok,
        "attributionSignals": signals,
        "attributionSignalsMatched": all(signal["observed"] for signal in signals),
        "remainingGapExpect": gold["remainingGapExpect"],
        "remainingGapMatched": remaining_gap_ok,
        "oldCitationReplay": replay,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _citation_metrics(rows: list[dict]) -> dict:
    failures = []
    sourced, no_source = [], []
    gold_accept = gold_reject = valid_accepted = rejected_out_of_bounds = 0
    false_accepted = unknown_predictions = 0
    for row in rows:
        if not row["verdictExpectationMatched"]:
            failures.append({
                "caseId": row["id"], "draftId": None,
                "reason": (
                    f"verdicts {row['verdictsObserved']} "
                    f"!= expected {row['verdictsExpected']}"
                ),
            })
        if not row["explanationMarkerMatched"]:
            failures.append({
                "caseId": row["id"], "draftId": None,
                "reason": "matcher explanation marker missing",
            })
        if row["sourceCheck"] == "mismatch":
            failures.append({
                "caseId": row["id"], "draftId": None, "reason": "source mismatch",
            })
        eligible = row["sourceCheck"] != "no-sources"
        for draft in row["drafts"]:
            if eligible:
                if draft["expectedContractRejection"] is False:
                    gold_accept += 1
                    valid_accepted += draft["accepted"] is True
                else:
                    gold_reject += 1
                    rejected_out_of_bounds += draft["accepted"] is False
                    false_accepted += draft["accepted"] is True
                unknown_predictions += draft["accepted"] is None
            if draft["accepted"] is None or not draft["expectationMatched"]:
                failures.append({
                    "caseId": row["id"], "draftId": draft["draftId"],
                    "reason": draft.get("error") or "contract verdict disagrees with gold",
                })
                continue
            if not eligible:
                continue
        (sourced if eligible else no_source).append(row["id"])
    return {
        "caseCount": len(rows),
        "sourceExactCount": sum(row["sourceExact"] for row in rows),
        "sourceMismatchCount": sum(row["sourceCheck"] == "mismatch" for row in rows),
        "noSourceCount": sum(row["sourceCheck"] == "no-sources" for row in rows),
        "noSourceCaseIds": no_source,
        "sourcedCaseIds": sourced,
        "draftsTotal": sum(len(row["drafts"]) for row in rows),
        "validCitationGoldAccept": gold_accept,
        "validCitationAccepted": valid_accepted,
        "validCitationAcceptanceRate": _ratio(valid_accepted, gold_accept),
        "outOfBoundsGoldReject": gold_reject,
        "outOfBoundsRejected": rejected_out_of_bounds,
        "outOfBoundsRejectionRate": _ratio(rejected_out_of_bounds, gold_reject),
        "contractCitationPrecision": _ratio(
            valid_accepted, valid_accepted + false_accepted,
        ),
        "contractCitationRecall": _ratio(valid_accepted, gold_accept),
        "unknownContractPredictions": unknown_predictions,
        "failures": failures,
    }


def _suggestion_metrics(rows: list[dict]) -> dict:
    failures = []
    matches = total = 0
    bad_rejected = bad_total = 0
    reference_accepted = reference_total = 0
    defect_classes: dict[str, dict] = {}
    for row in rows:
        if row["sourceCheck"] == "mismatch":
            failures.append({"caseId": row["id"], "reason": "source mismatch"})
        for probe in row["probes"]:
            total += 1
            matches += probe["expectationMatched"]
            if not probe["expectationMatched"]:
                failures.append({
                    "caseId": row["id"], "probeId": probe["probeId"],
                    "reason": probe.get("error") or "contract verdict disagrees with gold",
                })
            if probe["defectClass"] is None:
                reference_total += 1
                reference_accepted += probe["accepted"]
            else:
                bad_total += 1
                bad_rejected += not probe["accepted"]
                bucket = defect_classes.setdefault(
                    probe["defectClass"], {"rejected": 0, "total": 0},
                )
                bucket["total"] += 1
                bucket["rejected"] += not probe["accepted"]
    return {
        "caseCount": len(rows),
        "gapCategoryCoverage": {
            category: sum(row["gapCategory"] == category for row in rows)
            for category in sorted({row["gapCategory"] for row in rows})
        },
        "probesTotal": total,
        "expectationMatches": matches,
        "expectationMatchRate": _ratio(matches, total),
        "referenceDraftAccepted": reference_accepted,
        "referenceDraftTotal": reference_total,
        "badDraftRejected": bad_rejected,
        "badDraftTotal": bad_total,
        "badDraftRejectionRate": _ratio(bad_rejected, bad_total),
        "defectClassBreakdown": {
            name: {**bucket, "rejectionRate": _ratio(bucket["rejected"], bucket["total"])}
            for name, bucket in sorted(defect_classes.items())
        },
        "operabilityGoldBreakdown": {
            row["gapCategory"]: {
                key: row["operabilityGold"][key]
                for key in ("deliverableNamed", "stepsExecutable", "checksObservable")
            } for row in rows
        },
        # Counts of AUTHOR LABELS are coverage, never an observed quality score.
        "authoredOperabilityCounts": {
            key: {
                "numerator": sum(
                    row["operabilityGold"][key] for row in rows
                ),
                "denominator": len(rows),
            }
            for key in ("deliverableNamed", "stepsExecutable", "checksObservable")
        },
        "operabilityCounts": None,
        "generatedPlanOperabilityRate": None,
        "operabilityMeasurementStatus": "not-measured: authored draft labels only",
        "failures": failures,
    }


def _change_metrics(rows: list[dict]) -> dict:
    failures = []
    type_correct = signal_correct = 0
    gap_cases = gap_correct = 0
    for row in rows:
        if row["changeTypeExpectationMatched"]:
            type_correct += 1
        else:
            failures.append({
                "caseId": row["id"],
                "reason": (
                    f"change type mismatch: context={row['contextChanges']} "
                    f"items={row['itemChanges']} added={row['addedEvidenceCounts']} "
                    f"removed={row['removedEvidenceCounts']}"
                ),
            })
        if row["attributionSignalsMatched"]:
            signal_correct += 1
        else:
            failures.append({
                "caseId": row["id"],
                "reason": "attribution signals missing: "
                + ", ".join(
                    signal["kind"] for signal in row["attributionSignals"]
                    if not signal["observed"]
                ),
            })
        if row["remainingGapExpect"] is not None:
            gap_cases += 1
            gap_correct += row["remainingGapMatched"]
            if not row["remainingGapMatched"]:
                failures.append({
                    "caseId": row["id"],
                    "reason": "remaining gap text not carried by comparison",
                })
    return {
        "caseCount": len(rows),
        "changeGroupCoverage": {
            group: sum(row["changeGroup"] == group for row in rows)
            for group in sorted({row["changeGroup"] for row in rows})
        },
        "changeTypeCorrect": type_correct,
        "changeTypeAccuracy": _ratio(type_correct, len(rows)),
        "attributionSignalCorrect": signal_correct,
        "attributionSignalRate": _ratio(signal_correct, len(rows)),
        "remainingGapCases": gap_cases,
        "remainingGapIdentified": gap_correct,
        "remainingGapIdentificationRate": _ratio(gap_correct, gap_cases),
        "failures": failures,
    }


def load_cases(path: Path = DEFAULT_CASES) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ids = [
        row["id"]
        for row in [*payload["citationCases"], *payload["suggestionCases"],
                    *payload["changeCases"]]
    ]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("case IDs must be nonempty and unique across dimensions")
    return payload


def select(cases: dict, wanted: set[str] | None) -> dict:
    if wanted is None:
        return cases
    unknown = wanted - {
        row["id"] for row in [*cases["citationCases"], *cases["suggestionCases"],
                              *cases["changeCases"]]
    }
    if unknown:
        raise ValueError(f"unknown case ids: {sorted(unknown)}")
    keep = lambda rows: [row for row in rows if row["id"] in wanted]  # noqa: E731
    return {
        "citationCases": keep(cases["citationCases"]),
        "suggestionCases": keep(cases["suggestionCases"]),
        "changeCases": keep(cases["changeCases"]),
    }


def source_hashes(fixture_path: Path | None = None) -> dict:
    paths = {
        "runner": Path(__file__),
        "fixture": fixture_path or DEFAULT_CASES,
        "app.agents.contracts": Path(contracts_module.__file__),
        "app.agents.evidence_workflow": Path(evidence_workflow.__file__),
        "app.tools.matcher": Path(matcher.__file__),
        "app.tools.evidence_context": Path(evidence_context.__file__),
        "app.tools.function_coverage": Path(function_coverage.__file__),
        "app.tools.task_boundaries": Path(task_boundaries.__file__),
        "app.tools.resume_parser": Path(resume_parser.__file__),
        "app.services.report_comparison": Path(report_comparison.__file__),
    }
    return {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in sorted(paths.items())
    }


def evaluate(cases: dict, fixture_path: Path | None = None) -> dict:
    citation_rows = [evaluate_citation_case(case) for case in cases["citationCases"]]
    suggestion_rows = [evaluate_suggestion_case(case) for case in cases["suggestionCases"]]
    change_rows = [evaluate_change_case(case) for case in cases["changeCases"]]
    citation_metrics = _citation_metrics(citation_rows)
    suggestion_metrics = _suggestion_metrics(suggestion_rows)
    change_metrics = _change_metrics(change_rows)
    return {
        "suite": SUITE,
        "generatedAt": datetime.now(UTC).isoformat(),
        "syntheticDataOnly": True,
        "externalCalls": 0,
        "generatedWebsiteModelOutputs": 0,
        "labelAuthorship": (
            "Author-written synthetic labels (ZCode, GLM-5.3, 2026-10-10): not real "
            "model outputs, not independent human semantic review."
        ),
        "scope": (
            "Structural/rule probes over production paths only. semanticQualityPassRate "
            "stays null because no real-model or independent semantic review exists."
        ),
        "sourceHashes": source_hashes(fixture_path),
        "results": {
            "citation": citation_rows,
            "suggestion": suggestion_rows,
            "change": change_rows,
        },
        "metrics": {
            "citation": citation_metrics,
            "suggestion": suggestion_metrics,
            "change": change_metrics,
            "independentSemanticReviews": 0,
            "semanticQualityPassRate": None,
        },
    }


def suite_exit_ok(report: dict) -> bool:
    metrics = report["metrics"]
    return (
        metrics["citation"]["sourceMismatchCount"] == 0
        and not metrics["citation"]["failures"]
        and not metrics["suggestion"]["failures"]
        and not metrics["change"]["failures"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--case", default=None,
        help="Comma-separated case ids to run (across all three dimensions)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "Output already exists; choose a new filename to preserve baselines"
        )
    cases = select(
        load_cases(args.cases),
        set(args.case.split(",")) if args.case else None,
    )
    report = evaluate(cases, fixture_path=args.cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["metrics"], ensure_ascii=True))
    return 0 if suite_exit_ok(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
