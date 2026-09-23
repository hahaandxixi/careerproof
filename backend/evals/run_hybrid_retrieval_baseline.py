"""Generate a deterministic detector-versus-hybrid retrieval baseline."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.tools.code_analyzer import ProjectFileSnapshot, find_evidence
from app.tools.matcher import RequirementInput, match_candidate


@dataclass(frozen=True)
class Case:
    case_id: str
    title: str
    skill: str
    files: list[ProjectFileSnapshot]
    expected_path: str | None
    expected_rule_score: float | None


CASES = [
    Case(
        "uncovered_retry_identifier",
        "实现订单重试处理",
        "retry_order",
        [
            ProjectFileSnapshot(
                "app/worker.py",
                "def retry_order(order_id):\n    return order_queue.retry(order_id)\n",
            ),
            ProjectFileSnapshot("app/users.py", "def list_users():\n    return []\n"),
        ],
        "app/worker.py",
        None,
    ),
    Case(
        "detector_fastapi_preserved",
        "使用FastAPI开发接口",
        "FastAPI",
        [
            ProjectFileSnapshot(
                "app/main.py",
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "@app.get('/health')\n"
                "def health():\n"
                "    return {'ok': True}\n",
            )
        ],
        "app/main.py",
        0.65,
    ),
    Case(
        "comment_only_redis_rejected",
        "掌握Redis缓存",
        "Redis",
        [ProjectFileSnapshot("app/cache.py", "# Redis cache\ndef health():\n    return True\n")],
        None,
        0.0,
    ),
]


def run() -> dict:
    rows = []
    for case in CASES:
        detector = find_evidence(case.files, case.skill)
        result = match_candidate(
            [RequirementInput(uuid4(), case.title, case.skill, 5)], [], case.files
        )
        item = result.items[0]
        retrieved = [
            entry
            for entry in item.evidence_list
            if entry.evidence_type == "retrieved_context"
        ]
        paths = [entry.file_path for entry in item.evidence_list]
        path_ok = (
            case.expected_path in paths if case.expected_path is not None else not paths
        )
        score_ok = (
            case.expected_rule_score is None
            if item.rule_base_score == 0 and item.final_score is None
            else item.rule_base_score == case.expected_rule_score
        )
        rows.append(
            {
                "caseId": case.case_id,
                "detectorCount": len(detector),
                "retrievedCandidateCount": len(retrieved),
                "allCandidatePaths": paths,
                "verdict": item.verdict,
                "ruleBaseScore": item.rule_base_score,
                "pathExpectationPassed": path_ok,
                "scoreExpectationPassed": score_ok,
            }
        )
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "engine": "hybrid-lexical-v1",
        "semanticEmbedding": False,
        "summary": {
            "caseCount": len(rows),
            "pathExpectationsPassed": sum(row["pathExpectationPassed"] for row in rows),
            "scoreExpectationsPassed": sum(row["scoreExpectationPassed"] for row in rows),
        },
        "cases": rows,
        "caseDefinitions": [
            asdict(case) | {"files": [asdict(file) for file in case.files]}
            for case in CASES
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(run(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
