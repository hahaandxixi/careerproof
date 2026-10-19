"""Inventory regenerable caches/pytest trees; never follow directory junctions."""
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
TEMP = BACKEND / ".tmp"
SCAN_SKIPS = []


def inspect(path):
    files = size = 0
    links, errors = [], []
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            for entry in os.scandir(current):
                try:
                    item = entry.stat(follow_symlinks=False)
                    if item.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        links.append(entry.path)
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    else:
                        size += item.st_size
                        files += 1
                except OSError as error:
                    errors.append(type(error).__name__)
        except OSError as error:
            errors.append(type(error).__name__)
    return {"bytes": size, "files": files, "links": links, "errors": errors}


def pytest_tree(path):
    if not path.is_dir() or path.is_junction() or path.is_symlink():
        return False
    try:
        children = list(path.iterdir())
    except OSError as error:
        SCAN_SKIPS.append({"path": str(path), "reason": type(error).__name__})
        return False
    tests = [p for p in children if re.fullmatch(r"test_[A-Za-z0-9_]+\d+", p.name)]
    return bool(tests) and all(
        p in tests or (p.name == ".lock" and p.is_file()) for p in children
    )


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def protected_files():
    names = set(git("diff", "--name-only", "-z").decode().split("\0"))
    names.update(git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0"))
    result = {}
    for name in sorted(names - {""}):
        p = ROOT / name
        if p.is_file() and not p.is_relative_to(OUT):
            result[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def main():
    manifest = json.loads((TEMP / "local-run/processes.json").read_text(encoding="utf-8-sig"))
    active = Path(manifest["frontendRoot"])
    candidates = []
    # Old production/verification output only: preserve their source, locks and dependencies.
    for name in ["dep-frontend-20261010", "dep-frontend-20261017",
                 "dep-frontend-20261018", "dep-frontend-20261019-task82"]:
        stage = TEMP / name
        if stage.exists() and stage != active:
            candidates.extend((p / "cache", "obsolete Next compilation cache; complete builds retained")
                              for p in stage.iterdir()
                              if p.is_dir() and p.name.startswith(".next") and (p / "cache").is_dir())
    for base in [ROOT, BACKEND]:
        for name in [".ruff_cache", ".pytest_cache"]:
            if (base / name).is_dir():
                candidates.append((base / name, "regenerable lint/test cache"))
    # The layout, not just a directory's name or age, must identify a pytest basetemp.
    for parent in [BACKEND, TEMP]:
        for path in parent.iterdir():
            if not path.is_dir() or path.is_junction() or path.is_symlink():
                continue
            if parent == BACKEND and not path.name.startswith(".tmp-"):
                continue
            if path.name in {"ai-smoke", "local-run", "e2e", "release-smoke", "storage"}:
                continue
            if pytest_tree(path):
                candidates.append((path, "pytest generated basetemp; persistent logs kept"))
            elif (path / "pytest").is_dir() and pytest_tree(path / "pytest"):
                candidates.append((path / "pytest", "pytest generated basetemp; parent logs kept"))
    rows = []
    for path, reason in candidates:
        absolute = path.absolute()
        assert absolute.is_relative_to(ROOT) and absolute != ROOT
        assert not active.is_relative_to(absolute) and not absolute.is_relative_to(active)
        tracked = git("ls-files", "--", str(path.relative_to(ROOT))).strip()
        info = inspect(path)
        rows.append({"path": str(absolute), "reason": reason, **info,
                     "trackedFiles": bool(tracked),
                     "status": "skip" if tracked or info["links"] or info["errors"] else "planned"})
    report = {"root": str(ROOT), "activeFrontend": str(active), "candidates": rows,
              "scanSkipped": SCAN_SKIPS,
              "preserved": ["all dependencies and Python environments", "all source/locks",
                            "uncommitted and untracked nonignored files", "all docs/evidence",
                            "credentials, model budgets, storage, database volumes",
                            "video/audio/PDF/source packages", "P2 stash", "other D:/jbcode projects"],
              "protectedFileHashes": protected_files(),
              "stashBefore": git("stash", "list", "--format=%H").decode().splitlines()}
    (OUT / "cleanup.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ready = [r for r in rows if r["status"] == "planned"]
    print(json.dumps({"readyDirectories": len(ready), "MiB": round(sum(r["bytes"] for r in ready)/1048576, 1),
                      "files": sum(r["files"] for r in ready),
                      "skipped": [{"path": r["path"], "links": len(r["links"]),
                                   "errors": len(r["errors"])} for r in rows if r["status"] != "planned"]}))


if __name__ == "__main__":
    main()
