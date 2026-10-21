"""Compare the historical run copy with the pre-budget-fix source blob."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_COPY = ROOT / "backend/.tmp/agent-live-20261021/backend/app/agents/evidence_workflow.py"
RUN_COMMIT = "bcbe0e3"
CURRENT_COMMIT = "f17be7a"
REL = "backend/app/agents/evidence_workflow.py"
DEBUG_PREFIX = 'print(f"WORKFLOW_EXC'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    pre = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{RUN_COMMIT}:{REL}"])
    run = RUN_COPY.read_bytes()
    normalized = ("\n".join(
        line for line in run.decode("utf-8").splitlines() if not line.lstrip().startswith(DEBUG_PREFIX)
    ) + "\n").encode("utf-8")
    current = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{CURRENT_COMMIT}:{REL}"])
    result = {
        "runCommit": RUN_COMMIT,
        "currentCommit": CURRENT_COMMIT,
        "runCopySha256": digest(run),
        "preBudgetFixSha256": digest(pre),
        "normalizedRunCopySha256": digest(normalized),
        "currentWorkflowSha256": digest(current),
        "historicalBusinessEquivalent": normalized == pre,
        "currentBusinessEquivalent": normalized == current,
        "debugLineRemoved": next(
            (line.strip() for line in run.decode("utf-8").splitlines() if DEBUG_PREFIX in line), None
        ),
        "currentDelta": "budget estimator label and admission implementation changed after the historical run",
        "claim": "historical source-equivalent after removing one diagnostic print; not current-source byte-identical",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    out = ROOT / "docs/evidence/20261021-source-equivalence/source-equivalence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
