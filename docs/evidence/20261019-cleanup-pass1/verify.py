"""Verify removed sizes, protected Git files/stash and normal site availability."""
import json
from pathlib import Path

import httpx

from inventory import OUT, ROOT, TEMP, git, inspect, protected_files


def main():
    plan = json.loads((OUT / "cleanup.json").read_text(encoding="utf-8"))
    results = json.loads((OUT / "deletion-results.json").read_text(encoding="utf-8-sig"))
    removed_bytes = removed_files = 0
    for row in results:
        path = Path(row["path"])
        remaining = inspect(path) if path.exists() else {"bytes": 0, "files": 0, "errors": []}
        row["remainingBytes"] = remaining["bytes"]
        row["remainingFiles"] = remaining["files"]
        row["measurementErrors"] = len(remaining["errors"])
        if not remaining["errors"]:
            removed_bytes += row["beforeBytes"] - remaining["bytes"]
            removed_files += row["beforeFiles"] - remaining["files"]
    after = protected_files()
    protected = plan["protectedFileHashes"]
    changed = [name for name, value in protected.items() if after.get(name) != value]
    stash_after = git("stash", "list", "--format=%H").decode().splitlines()
    manifest = json.loads((TEMP / "local-run/processes.json").read_text(encoding="utf-8-sig"))
    assert manifest["frontendRoot"] == plan["activeFrontend"]
    build = Path(plan["activeFrontend"]) / ".next/BUILD_ID"
    http = {}
    with httpx.Client(trust_env=False, timeout=20) as client:
        for name, url in [("site", "http://127.0.0.1:3000/jobs"),
                          ("api", "http://127.0.0.1:8000/api/v1/health")]:
            http[name] = client.get(url).status_code
        response = client.get("http://127.0.0.1:8000/api/v1/jobs")
        response.raise_for_status()
        jobs = response.json()["data"]
        http["discoveryTotal"] = jobs["total"]
        http["sampleCount"] = sum(bool(j["isDemo"]) for j in jobs["items"])
    report = {"removedBytes": removed_bytes, "removedGiB": round(removed_bytes/1024**3, 3),
              "removedFiles": removed_files,
              "fullyRemovedDirectories": sum(r["status"] == "deleted" for r in results),
              "retainedOrPartial": [r for r in results if r["status"] != "deleted"],
              "scanSkippedUnreadable": len(plan["scanSkipped"]),
              "protectedFilesChecked": len(protected), "protectedChanged": changed,
              "stashUnchanged": stash_after == plan["stashBefore"],
              "activeBuildId": build.read_text().strip(), "http": http,
              "perPathAfter": results}
    (OUT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"perPathAfter", "retainedOrPartial"}}, ensure_ascii=False))
    print("retainedOrPartial", len(report["retainedOrPartial"]))
    assert not changed and report["stashUnchanged"]
    assert http["site"] == http["api"] == 200
    assert http["discoveryTotal"] == 4 and http["sampleCount"] == 3


if __name__ == "__main__":
    main()
