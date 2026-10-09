"""Read public maintainer GitHub advisories through gh; preserve fresh evidence."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPOSITORIES = (
    "Kludex/starlette", "jpadilla/pyjwt", "Kludex/python-multipart",
    "python-pillow/Pillow", "vercel/next.js", "facebook/react",
    "modelcontextprotocol/python-sdk", "fastapi/fastapi",
)


def collect(repository):
    endpoint = f"repos/{repository}/security-advisories?per_page=100"
    try:
        result = subprocess.run(
            ["gh", "api", endpoint, "--paginate", "--slurp"],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        if result.returncode:
            return {"repository": repository, "endpoint": endpoint,
                    "exitCode": result.returncode, "status": "fetch_failed"}
        pages = json.loads(result.stdout)
        return {"repository": repository, "endpoint": endpoint, "exitCode": 0,
                "advisories": [item for page in pages for item in page]}
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return {"repository": repository, "endpoint": endpoint,
                "status": type(error).__name__}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.output).name != args.output or not args.output.endswith(".json"):
        parser.error("Use a new JSON filename in this evidence directory")
    destination = Path(__file__).with_name(args.output)
    if destination.exists():
        parser.error("Preserve previous evidence: output already exists")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(collect, REPOSITORIES))
    payload = {"collectedAtUtc": datetime.now(UTC).isoformat(),
               "scope": "Eight selected maintainer repositories; not exhaustive dependency audit",
               "results": results}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    for item in results:
        print(item["repository"], item.get("status", "ok"), len(item.get("advisories", [])))
    return int(any(item.get("exitCode") != 0 for item in results))


if __name__ == "__main__":
    raise SystemExit(main())
