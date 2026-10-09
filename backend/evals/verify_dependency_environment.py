"""Verify the selected E2E interpreter satisfies current production dependency pins."""

from __future__ import annotations

import importlib.metadata
import json
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path


def verify_environment(
    manifest: Path,
    version_reader: Callable[[str], str] = importlib.metadata.version,
) -> dict[str, str]:
    document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    versions = {}
    for declaration in document["project"]["dependencies"]:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^;\s]+)", declaration)
        if not match:
            raise ValueError("E2E verifier requires an explicit exact production dependency pin")
        name, required = match.groups()
        try:
            actual = version_reader(name)
        except importlib.metadata.PackageNotFoundError:
            raise ValueError(f"Selected E2E interpreter is missing {name}") from None
        if actual != required:
            raise ValueError(f"Selected E2E interpreter has {name}=={actual}; requires {required}")
        versions[name] = actual
    return versions


def main() -> None:
    if sys.version_info[:2] != (3, 12):
        raise ValueError("This project's E2E runtime requires Python 3.12")
    manifest = Path(__file__).resolve().parents[1] / "pyproject.toml"
    versions = verify_environment(manifest)
    print(json.dumps({"python": sys.version.split()[0], "dependencies": versions}, sort_keys=True))


if __name__ == "__main__":
    main()
