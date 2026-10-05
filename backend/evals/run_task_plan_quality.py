"""Offline task-plan contract probes and replay of named synthetic model outputs.

Reference drafts are authored fixtures, never model results or independent labels.
No provider is created, no network is used, and uploaded sample code is not executed.

Cases may declare optional third-party ``referenceFiles``; they go through the
matcher's keyword-only ``reference_files`` interface and the enrichment plus
snippet checks use the merged personal+reference file set, after rejecting
normalized duplicate paths so a reference file can never shadow a personal one.
Empty evidence is never counted as source-exact; it is reported separately so a
correct no-implementation downgrade is not failed for lacking citations.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.agents.contracts import EvidenceAnalysis, validate_grounded_analysis
from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import EVIDENCE_PROMPT_VERSION
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume

SUITE = "task-plan-quality-v2"
DEFAULT_CASES = Path(__file__).with_name("task-plan-quality-cases.json")


def _normalized_path(path: str) -> str:
    return path.replace("\\", "/")


def load_cases(path: Path = DEFAULT_CASES) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def case_files(case: dict) -> tuple[list[ProjectFileSnapshot], list[ProjectFileSnapshot]]:
    files = [ProjectFileSnapshot(**row) for row in case["files"]]
    reference_files = [ProjectFileSnapshot(**row) for row in case.get("referenceFiles", [])]
    personal_paths = {_normalized_path(file.path) for file in files}
    reference_paths = {_normalized_path(file.path) for file in reference_files}
    if len(files) != len(personal_paths) or len(reference_files) != len(reference_paths):
        raise ValueError(f"case {case['id']}: duplicate normalized file paths")
    collision = sorted(personal_paths & reference_paths)
    if collision:
        raise ValueError(
            f"case {case['id']}: personal/reference path collision would confuse "
            f"provenance lookup: {collision}"
        )
    return files, reference_files


def case_context(case: dict):
    files, reference_files = case_files(case)
    requirement = RequirementInput(
        uuid5(NAMESPACE_URL, f"{SUITE}:{case['id']}"),
        case["requirement"], case["skill"], 5,
    )
    result = enrich_evidence(
        match_candidate(
            [requirement], parse_resume(case["resume"]), files,
            reference_files=reference_files or None,
        ),
        [*files, *reference_files],
    )
    contexts = build_evidence_contexts(result)
    content_by_path = {
        _normalized_path(file.path): file.content for file in [*files, *reference_files]
    }
    source_count = 0
    exact = True
    for context in contexts:
        for source in context.evidence:
            source_count += 1
            content = content_by_path.get(_normalized_path(source.file_path))
            if content is None:
                exact = False
                continue
            expected = "\n".join(
                content.splitlines()[source.line_start - 1:source.line_end]
            ).strip()
            if source.snippet.strip() != expected:
                exact = False
    if not source_count:
        exact = False
    return contexts, exact, source_count


def draft_probe(context, draft: dict) -> dict:
    # A neutral envelope isolates draft guards. Its null rating is not a semantic
    # opinion about the sample. Reviewers receive the full context and rubric.
    citations = [source.citation_id for source in context.evidence
                 if source.provenance == "portfolio"] if context.verdict in {
                     "supported", "partial"
                 } else []
    contract_draft = dict(draft)
    if "acceptanceChecks" in contract_draft:
        contract_draft["acceptance_checks"] = contract_draft.pop("acceptanceChecks")
    return {
        "summary": "离线合成草稿契约检查，不是模型生成或独立质量评定。",
        "model": "authored-contract-probe",
        "items": [{
            "requirement_id": context.requirement_id,
            "explanation": "当前规则提供材料线索，执行结果、本人贡献及其他范围仍需人工核验。",
            "citation_ids": citations,
            "information_gap": "执行结果、本人贡献及未展示材料仍需核对。",
            "suggestion": "针对本项要求补充具名材料并人工核对。",
            "task_plan": contract_draft,
            "confidence": 0,
            "rating": {
                "level": None, "reason": "仅为草稿契约检查，不作语义评级。",
                "criteria": [{
                    "criterion": key, "supported": False, "citation_ids": [],
                    "reason": "草稿契约检查未作语义评级。",
                } for key in ("relevance", "operation", "task")],
            },
        }],
    }


def validate_output(contexts, value: dict) -> dict:
    try:
        analysis = EvidenceAnalysis.model_validate(value)
        validate_grounded_analysis(contexts, analysis)
    except ValueError as error:
        return {"accepted": False, "error": str(error)}
    return {"accepted": True, "error": None}


def evaluate_case(case: dict, model_output: dict | None = None) -> dict:
    contexts, exact, source_count = case_context(case)
    source_check = "no-sources" if not source_count else ("verified" if exact else "mismatch")
    probes = [{
        "id": "authored-reference", "defect": None,
        "expectedContractRejection": False, "draft": case["referenceDraft"],
    }, *case["knownBadDrafts"]]
    rows = []
    for probe in probes:
        checked = validate_output(contexts, draft_probe(contexts[0], probe["draft"]))
        rows.append({
            **probe, **checked,
            "contractExpectationMatched": (
                checked["accepted"] is not probe["expectedContractRejection"]
            ),
            "source": "authored-fixture",
            "semanticReview": "pending",
        })
    return {
        "id": case["id"], "direction": case["direction"], "gapKind": case["gapKind"],
        "requirement": case["requirement"], "qualityRubric": case["qualityRubric"],
        "sourceExact": exact, "sourceCheck": source_check, "sourceCount": source_count,
        "evidenceCount": len(contexts[0].evidence),
        "contexts": [context.model_dump() for context in contexts], "probes": rows,
        "modelReplay": validate_output(contexts, model_output) if model_output else None,
        "rawModelOutput": model_output,
        "independentSemanticReview": {
            "status": "pending", "reviewer": None,
            "executable": None, "verifiable": None, "supportedBySources": None,
        },
    }


def load_model_outputs(path: Path | None, known: set[str]) -> dict:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("syntheticDataOnly") is not True:
        raise ValueError("Replay requires a named syntheticDataOnly output collection")
    rows = payload["outputs"]
    ids = [row["caseId"] for row in rows]
    if len(ids) != len(set(ids)) or not set(ids) <= known:
        raise ValueError("Replay contains duplicate or unknown case IDs")
    return {row["caseId"]: row["analysis"] for row in rows}


def evaluate(cases: list[dict], model_outputs: dict | None = None) -> dict:
    ids = [case["id"] for case in cases]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Use a nonempty collection with unique case IDs")
    if not set(model_outputs or {}) <= set(ids):
        raise ValueError("Model output does not belong to a selected case")
    rows = [evaluate_case(case, (model_outputs or {}).get(case["id"])) for case in cases]
    probes = [probe for row in rows for probe in row["probes"]]
    mismatches = [
        {
            "caseId": row["id"], "probeId": probe["id"],
            "expectedContractRejection": probe["expectedContractRejection"],
            "accepted": probe["accepted"],
        }
        for row in rows for probe in row["probes"]
        if not probe["contractExpectationMatched"]
    ]
    return {
        "suite": SUITE, "promptVersionNow": EVIDENCE_PROMPT_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(), "syntheticDataOnly": True,
        "externalCalls": 0, "mode": "saved-output-replay" if model_outputs else "authored-probes",
        "scope": "Contract probes are authored fixtures, not model quality or independent review.",
        "results": rows,
        "metrics": {
            "caseCount": len(rows), "sourceExactCount": sum(row["sourceExact"] for row in rows),
            "sourceMismatchCount": sum(row["sourceCheck"] == "mismatch" for row in rows),
            "noSourceCount": sum(row["sourceCheck"] == "no-sources" for row in rows),
            "gapKindCoverage": dict(sorted(Counter(
                row["gapKind"] for row in rows).items())),
            "referenceContractAccepted": sum(row["probes"][0]["accepted"] for row in rows),
            "contractExpectationMatches": sum(p["contractExpectationMatched"] for p in probes),
            "contractProbeCount": len(probes),
            "contractExpectationMismatches": mismatches,
            "replayedModelOutputs": len(model_outputs or {}),
            "independentSemanticReviews": 0, "semanticQualityPassRate": None,
        },
    }


def suite_exit_ok(report: dict) -> bool:
    # Source verification and contract assertions stay separate: empty-evidence
    # cases count as no-sources, never as exact, and never fail the suite by
    # themselves — a correct no-implementation downgrade has zero citations.
    metrics = report["metrics"]
    return (
        metrics["sourceMismatchCount"] == 0
        and metrics["contractExpectationMatches"] == metrics["contractProbeCount"]
        and all(
            row["modelReplay"]["accepted"]
            for row in report["results"] if row["modelReplay"]
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--responses", type=Path,
        help="Read saved synthetic outputs; never calls a model",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "Output already exists; choose a new filename to preserve failures and baselines"
        )
    cases = load_cases(args.cases)
    outputs = load_model_outputs(args.responses, {case["id"] for case in cases})
    report = evaluate(cases, outputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["metrics"], ensure_ascii=True))
    return 0 if suite_exit_ok(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
