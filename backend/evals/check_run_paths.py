"""Check the explicit run-path source manifest, not the whole worktree."""
from __future__ import annotations

import argparse
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
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(text, end="")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
