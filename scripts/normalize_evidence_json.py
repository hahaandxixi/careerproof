"""Canonicalize ad-hoc evidence JSON files without changing their values.

Some early evidence commands redirected JSON through PowerShell, which added a
UTF-8 BOM. These five files have no standalone producer script, so this explicit
allowlist re-serializes them with encoding='utf-8' and json.dump. Values are
loaded before writing; the files are not edited by removing bytes.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "docs/evidence/20261017-task77-student-experience/lint.json",
    "docs/evidence/20261018-task80-integration-fixes/lint.json",
    "docs/evidence/20261019-enterprise-filter-state/isolated-two-candidate.json",
    "docs/evidence/20261019-role-consistency/local-run-processes.json",
    "docs/evidence/20261019-task82-job-discovery/import-plan-no-db.json",
]


def main() -> None:
    for relative in FILES:
        path = ROOT / relative
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"normalized {relative}")


if __name__ == "__main__":
    main()
