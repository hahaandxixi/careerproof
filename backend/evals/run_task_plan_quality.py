"""Offline task-plan contract probes and replay of named synthetic model outputs.

Reference drafts are authored fixtures, never model results or independent labels.
No provider is created, no network is used, and uploaded sample code is not executed.
"""

from __future__ import annotations

import argparse
import json
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


def case_context(case: dict):
    files = [ProjectFileSnapshot(**row) for row in case["files"]]
    requirement = RequirementInput(
        uuid5(NAMESPACE_URL, f"{SUITE}:{case['id']}"),
        case["requirement"], case["skill"], 5,
    )
    result = enrich_evidence(
        match_candidate([requirement], parse_resume(case["resume"]), files), files,
    )
    contexts = build_evidence_contexts(result)
    exact = all(
        source.snippet.strip()
        == "\n".join(
            next(file.content for file in files if file.path == source.file_path).splitlines()[
                source.line_start - 1:source.line_end
            ]
        ).strip()
        for context in contexts
        for source in context.evidence
    )
    return contexts, exact


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
    contexts, exact = case_context(case)
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
        "sourceExact": exact, "evidenceCount": len(contexts[0].evidence),
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
    return {
        "suite": SUITE, "promptVersionNow": EVIDENCE_PROMPT_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(), "syntheticDataOnly": True,
        "externalCalls": 0, "mode": "saved-output-replay" if model_outputs else "authored-probes",
        "scope": "Contract probes are authored fixtures, not model quality or independent review.",
        "results": rows,
        "metrics": {
            "caseCount": len(rows), "sourceExactCount": sum(row["sourceExact"] for row in rows),
            "referenceContractAccepted": sum(row["probes"][0]["accepted"] for row in rows),
            "contractExpectationMatches": sum(p["contractExpectationMatched"] for p in probes),
            "contractProbeCount": len(probes), "replayedModelOutputs": len(model_outputs or {}),
            "independentSemanticReviews": 0, "semanticQualityPassRate": None,
        },
    }


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
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    outputs = load_model_outputs(args.responses, {case["id"] for case in cases})
    report = evaluate(cases, outputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["metrics"], ensure_ascii=True))
    return 0 if (
        all(row["sourceExact"] for row in report["results"])
        and (
            report["metrics"]["contractExpectationMatches"]
            == report["metrics"]["contractProbeCount"]
        )
        and all(
            row["modelReplay"]["accepted"]
            for row in report["results"] if row["modelReplay"]
        )
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
