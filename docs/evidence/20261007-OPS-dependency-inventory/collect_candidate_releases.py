"""Confirm proposed fixes against public maintainer releases without installing."""

import base64
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

CANDIDATES = (
    ("fastapi/fastapi", "0.143.0"), ("Kludex/starlette", "1.3.1"),
    ("Kludex/python-multipart", "0.0.31"), ("python-pillow/Pillow", "12.3.0"),
    ("jpadilla/pyjwt", "2.15.0"), ("vercel/next.js", "15.5.27"),
    ("lovell/sharp", "0.35.5"), ("postcss/postcss", "8.5.23"),
    ("postcss/postcss-selector-parser", "7.1.6"), ("7rulnik/source-map-js", "1.2.2"),
    ("sqlalchemy/mako", "1.4.2"), ("pypa/pip", "26.2.0"), ("pytest-dev/pytest", "9.0.3"),
)


def fetch(endpoint):
    process = subprocess.run(["gh", "api", endpoint], capture_output=True,
                             text=True, encoding="utf-8", timeout=45)
    if process.returncode:
        return None
    return json.loads(process.stdout)


def candidate(item):
    repository, version = item
    attempts = []
    for tag in (version, f"v{version}"):
        endpoint = f"repos/{repository}/releases/tags/{tag}"
        attempts.append(endpoint)
        release = fetch(endpoint)
        if release:
            return {"repository": repository, "version": version, "attemptedEndpoints": attempts,
                    "status": "maintainer_release_confirmed", "release": release}
    return {"repository": repository, "version": version, "attemptedEndpoints": attempts,
            "status": "release_not_confirmed"}


def main():
    output = Path(__file__).with_name("candidate-releases-20261009.json")
    if output.exists():
        raise FileExistsError("Preserve previous evidence")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(candidate, CANDIDATES))
    constraints = fetch("repos/fastapi/fastapi/contents/pyproject.toml?ref=0.143.0")
    if constraints:
        constraints = {"html_url": constraints["html_url"], "sha": constraints["sha"],
                       "source": base64.b64decode(constraints["content"]).decode("utf-8")}
    payload = {"collectedAtUtc": datetime.now(UTC).isoformat(), "results": results,
               "fastapiCandidateConstraints": constraints,
               "scope": "Maintainer releases and tagged source; package registry availability and upgrade tests not verified"}
    with output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    for result in results:
        print(result["repository"], result["version"], result["status"])
    if constraints:
        for line in constraints["source"].splitlines():
            if "starlette" in line or "requires-python" in line:
                print("FastAPI candidate constraint:", line.strip())


if __name__ == "__main__":
    main()
