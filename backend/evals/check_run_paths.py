"""Check the explicit run-path source manifest, not the whole worktree."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/evidence/20261021-source-equivalence/run-paths.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for relative, expected in manifest["paths"].items():
        path = ROOT / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        dirty = subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--quiet", "--", relative],
            capture_output=True,
        ).returncode != 0
        untracked = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard", "--", relative],
            text=True,
        ).strip()
        rows.append({
            "path": relative,
            "expectedSha256": expected,
            "actualSha256": actual,
            "dirty": dirty,
            "untracked": bool(untracked),
            "passed": actual == expected and not dirty and not untracked,
        })
    result = {"status": "pass" if all(row["passed"] for row in rows) else "fail", "paths": rows}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
