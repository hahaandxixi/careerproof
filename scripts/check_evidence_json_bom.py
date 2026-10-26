"""Fail if any delivery evidence JSON starts with a UTF-8 BOM."""
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
    "docs/evidence/20261021-source-equivalence/source-equivalence.json",
    "docs/evidence/20261021-source-equivalence/path-check.json",
]


def main() -> int:
    failed = False
    for relative in FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            json.loads(raw.decode("utf-8-sig"))
            parsed = True
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = False
        print(f"{'FAIL' if bom or not parsed else 'OK'} BOM={bom} parse={parsed} {relative}")
        failed = failed or bom or not parsed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
