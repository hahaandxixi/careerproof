"""Independent diagnostic of the current offline fixture contract, no model calls."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from evals.run_task_plan_quality import evaluate, suite_exit_ok  # noqa: E402

sources = [
    BACKEND / "evals/run_task_plan_quality.py",
    BACKEND / "evals/task-plan-quality-cases.json",
    BACKEND / "app/agents/contracts.py",
]
boundary_module = BACKEND / "app/tools/task_boundaries.py"
if boundary_module.exists():
    sources.append(boundary_module)


def digests():
    return {
        str(file.relative_to(ROOT)).replace("\\", "/"):
        hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sources
    }


before = digests()
cases = json.loads(sources[1].read_text(encoding="utf-8"))
report = evaluate(cases)
after = digests()
result = {
    "sourceHashesBefore": before,
    "sourceHashesAfter": after,
    "sourcesUnchangedDuringCheck": before == after,
    "externalCalls": report["externalCalls"],
    "metrics": report["metrics"],
    "suitePassed": suite_exit_ok(report),
    "unmatched": [
        {
            "caseId": row["id"], "probeId": probe["id"],
            "accepted": probe["accepted"],
            "expectedRejection": probe["expectedContractRejection"],
            "error": probe["error"],
        }
        for row in report["results"]
        for probe in row["probes"]
        if not probe["contractExpectationMatched"]
    ],
}
serialized = json.dumps(result, ensure_ascii=True, indent=2)
if len(sys.argv) > 1:
    with Path(sys.argv[1]).open("x", encoding="utf-8") as stream:
        stream.write(serialized + "\n")
print(serialized)
raise SystemExit(0 if result["suitePassed"] and before == after else 1)
