from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.matcher import FORMULA_VERSION, RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume


def evaluate(cases: list[dict]) -> dict:
    results = []
    for case in cases:
        requirement = RequirementInput(
            id=uuid5(NAMESPACE_URL, case["id"]),
            title=case["requirement"],
            skill=case["skill"],
            weight=5,
        )
        files = [ProjectFileSnapshot(**item) for item in case["files"]]
        item = match_candidate([requirement], parse_resume(case["resume"]), files).items[0]
        evidence_type = item.evidence.evidence_type if item.evidence else None
        verdict_ok = item.verdict == case["expectedVerdict"]
        evidence_ok = evidence_type == case["expectedEvidenceType"]
        citation_ok = True
        if item.evidence:
            source = next(file for file in files if file.path == item.evidence.file_path)
            lines = source.content.splitlines()
            citation_ok = item.evidence.snippet == lines[item.evidence.line_start - 1].strip()[:240]
        results.append(
            {
                "id": case["id"],
                "passed": verdict_ok and evidence_ok and citation_ok,
                "actualVerdict": item.verdict,
                "actualEvidenceType": evidence_type,
                "citationValid": citation_ok,
            }
        )
    passed = sum(result["passed"] for result in results)
    return {
        "formulaVersion": FORMULA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(),
        "caseCount": len(results),
        "passed": passed,
        "passRate": round(passed / len(results), 4) if results else 0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic evidence baseline")
    parser.add_argument("--cases", type=Path, default=Path("evals/rule-eval-cases.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(json.loads(args.cases.read_text(encoding="utf-8")))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] == report["caseCount"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
