"""Read local manifests and installed metadata; no network or package imports."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed_python(requirement: str) -> dict:
    name = re.match(r"[A-Za-z0-9_.-]+", requirement).group(0)
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return {"requirement": requirement, "name": name, "installed": None}
    return {
        "requirement": requirement,
        "name": name,
        "installed": distribution.version,
        "requires": distribution.requires or [],
    }


def collect() -> dict:
    backend_manifest = ROOT / "backend/pyproject.toml"
    frontend_manifest = ROOT / "jianli/package.json"
    frontend_lock = ROOT / "jianli/package-lock.json"
    project = tomllib.loads(backend_manifest.read_text(encoding="utf-8"))["project"]
    frontend = json.loads(frontend_manifest.read_text(encoding="utf-8"))
    lock = json.loads(frontend_lock.read_text(encoding="utf-8"))
    python_groups = {"runtime": project["dependencies"]}
    python_groups.update(project.get("optional-dependencies", {}))
    javascript = {}
    for group in ("dependencies", "devDependencies"):
        javascript[group] = []
        for name, requested in frontend.get(group, {}).items():
            module_path = ROOT / "jianli/node_modules" / name / "package.json"
            installed = (
                json.loads(module_path.read_text(encoding="utf-8"))["version"]
                if module_path.exists() else None
            )
            javascript[group].append({
                "name": name,
                "requested": requested,
                "locked": lock.get("packages", {}).get(f"node_modules/{name}", {}).get("version"),
                "installed": installed,
            })
    distributions = sorted(
        ({"name": item.metadata["Name"], "version": item.version}
         for item in importlib.metadata.distributions()),
        key=lambda item: item["name"].lower(),
    )
    return {
        "collectedAtUtc": datetime.now(UTC).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "scope": "local metadata only; no advisory audit, upgrade, network or database action",
        "manifestHashes": {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
            for path in (backend_manifest, frontend_manifest, frontend_lock)
        },
        "pythonGroups": {
            group: [installed_python(requirement) for requirement in requirements]
            for group, requirements in python_groups.items()
        },
        "installedPythonDistributions": distributions,
        "javascriptDirect": javascript,
        "javascriptLockVersions": {
            name: value.get("version")
            for name, value in sorted(lock.get("packages", {}).items())
            if name and value.get("version")
        },
        "notVerified": [
            "current official advisories and affected version ranges",
            "deployment or Docker image installed versions",
            "upgrade compatibility and post-upgrade tests",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="local-inventory.json", help="new JSON filename in this evidence directory")
    arguments = parser.parse_args()
    if Path(arguments.output).name != arguments.output or not arguments.output.endswith(".json"):
        parser.error("output must be a JSON filename without directories")
    output = Path(__file__).with_name(arguments.output)
    if output.exists():
        parser.error("snapshot already exists; choose a new --output filename to preserve evidence")
    inventory = collect()
    with output.open("x", encoding="utf-8") as destination:
        destination.write(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {output.relative_to(ROOT)}")
    print(f"HEAD {inventory['head']}; {len(inventory['installedPythonDistributions'])} Python distributions")
    print("LOCAL INVENTORY ONLY; advisories, Docker and upgrade compatibility unverified")
