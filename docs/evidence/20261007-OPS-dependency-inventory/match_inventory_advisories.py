"""Read GitHub reviewed advisories for exact installed/locked package versions."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode


def query(package):
    ecosystem, name, version = package
    endpoint = "advisories?" + urlencode({
        "type": "reviewed", "ecosystem": ecosystem,
        "affects": f"{name}@{version}", "per_page": 100,
    })
    result = {"ecosystem": ecosystem, "name": name, "version": version,
              "endpoint": endpoint}
    try:
        process = subprocess.run(
            ["gh", "api", endpoint, "--paginate", "--slurp"],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        result["exitCode"] = process.returncode
        if process.returncode:
            result["status"] = "query_failed"
        else:
            pages = json.loads(process.stdout)
            result["status"] = "queried"
            result["advisories"] = [item for page in pages for item in page]
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        result["status"] = type(error).__name__
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    for name in (args.inventory, args.output):
        if Path(name).name != name or not name.endswith(".json"):
            parser.error("Use evidence-directory JSON filenames")
    directory = Path(__file__).parent
    output = directory / args.output
    if output.exists():
        parser.error("Preserve existing evidence; choose a fresh output")
    inventory = json.loads((directory / args.inventory).read_text(encoding="utf-8"))
    packages = {("pip", item["name"], item["version"])
                for item in inventory["installedPythonDistributions"]}
    for path, version in inventory["javascriptLockVersions"].items():
        if "node_modules/" not in path:
            raise ValueError(f"Unexpected lock package path: {path}")
        packages.add(("npm", path.rsplit("node_modules/", 1)[1], version))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(query, sorted(packages)))
    payload = {"collectedAtUtc": datetime.now(UTC).isoformat(),
               "inventory": args.inventory, "inventoryHead": inventory["head"],
               "scope": "Reviewed advisory version matches; not exploitability or safety proof",
               "packageVersionCount": len(packages), "results": results}
    with output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    failed = [item for item in results if item["status"] != "queried"]
    matches = [item for item in results if item.get("advisories")]
    print(f"Queried {len(results)} package versions; failures {len(failed)}; matching packages {len(matches)}")
    for item in matches:
        print(item["ecosystem"], item["name"], item["version"], len(item["advisories"]))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
