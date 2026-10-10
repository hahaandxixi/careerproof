"""Independent narrow guard probe; not a production-model quality score."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "backend"))
from app.tools.task_boundaries import task_boundary_error

inputs = json.loads((root / "backend/evals/quality-blind-plan-review-input.json").read_text(encoding="utf-8"))
case = next(c for c in inputs["cases"] if c["id"] == "09fb4e82f3")
source = [f["content"] for f in case["personalFiles"]]
draft = case["draft"]
bad = task_boundary_error(deliverable=draft["deliverable"], steps=draft["steps"],
    acceptance_checks=draft["acceptanceChecks"], personal_source_texts=source)
good = task_boundary_error(deliverable="本人贡献证明补交计划",
    steps=["先核对共用账号不能区分作者的边界，再补交独立具名的分工证明"],
    acceptance_checks=["贡献在独立材料核验前仍待核验"], personal_source_texts=source)
assert bad is None, "Baseline changed: reassess the proposed regression before implementation"
assert good is None
print(json.dumps({"scope":"task_boundary_error only, not full matcher/contract/model",
    "sourceSha256": hashlib.sha256((root / "backend/app/tools/task_boundaries.py").read_bytes()).hexdigest(),
    "sharedAccountFrozenDraftAcceptedByGuard":bad is None,
    "explicitlyPendingIndependentProofAccepted":good is None,
    "finding":"Current guard does not distinguish extracting personal signed commits from explicitly shared-account history from obtaining new independent proof"}, ensure_ascii=False, indent=2))
