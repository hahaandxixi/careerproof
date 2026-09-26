"""Explicit paid text-report check using saved synthetic vision and synthetic code."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.agents.provider import EVIDENCE_PROMPT_VERSION
from evals.demo_credentials import get_demo_credentials
from evals.verify_deepseek_tool_report import BASE, data, wait
from evals.verify_persisted_history import OLD_CODE, upload_code


def checks(report, visual, code_version):
    sources = [e for item in report["items"] for e in item["evidenceList"]]
    exact = bool(sources) and all(
        e["filePath"].startswith(code_version + "/")
        and e["filePath"].endswith("/app.py")
        and e["snippet"] == "\n".join(
            OLD_CODE.splitlines()[e["lineStart"] - 1:e["lineEnd"]])
        for e in sources
    )
    current = all(
        set(item["aiCitationIds"]).issubset({e["citationId"] for e in item["evidenceList"]})
        for item in report["items"]
    )
    return {
        "realDeepSeekText": report["analysisMode"] == "ai_evidence"
        and report["aiProvider"] == "deepseek" and not report["aiFallbackUsed"],
        "allItemsValidated": bool(report["items"])
        and all(i["aiStatus"] == "validated" for i in report["items"]),
        "codeSourcesExact": exact,
        "currentCitationWhitelist": current,
        "visualSnapshotExact": len(report["visualClaims"]) == 1
        and report["visualClaims"][0] == visual,
        "noVisualCodeEvidence": exact,
        "gradesWithinBound": all(
            i["evidenceLevel"] is None or 1 <= i["evidenceLevel"] <= 3
            for i in report["items"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    if not parser.parse_args().live:
        print("No calls. --live uses saved synthetic visual fixture and paid DeepSeek text.")
        return 0
    endpoint = urlparse(BASE)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only the local synthetic evaluation API is allowed")
    directory = Path(__file__).parent
    reference = json.loads((directory / "visual-browser-boundary-20260926.json")
                           .read_text(encoding="utf-8"))
    visual_version = reference["visual"]["projectVersionId"]
    fixture = directory.parents[1] / "demo" / "synthetic-vision-panel.png"
    expected_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    with (httpx.Client(base_url=BASE, timeout=60, trust_env=False) as student,
          httpx.Client(base_url=BASE, timeout=30, trust_env=False) as enterprise):
        data(student.post("/auth/login", json=get_demo_credentials("student")))
        visual = data(student.get(f"/project-versions/{visual_version}/visual-review"))
        if (visual["sourceHash"] != expected_hash or visual["status"] != "completed"
                or visual["model"] != "deepseek-flash"):
            raise ValueError("Saved synthetic DeepSeek visual observation is required")
        base = data(student.get(f"/match-reports/{reference['report']['id']}"))
        resume = next(m["id"] for m in base["materials"] if m["kind"] == "resume")
        project = data(student.post("/projects", json={
            "name": f"视觉与代码组合合成验收 {stamp}",
            "description": "固定合成源码，不执行代码，不用于真实招聘。"}))
        source = upload_code(student, project["id"], OLD_CODE)
        accepted = data(student.post("/matches", json={
            "jobId": base["jobId"], "resumeVersionId": resume,
            "projectVersionIds": [source["versionId"], visual_version],
            "externalAiConsent": True, "usePreviousReport": False}))
        task, states = wait(student, accepted["taskId"])
        report = data(student.get(f"/match-reports/{task['reportId']}"))
        results = checks(report, visual, source["versionId"])
        results["reloadStable"] = report == data(
            student.get(f"/match-reports/{report['id']}"))
        data(enterprise.post("/auth/login", json=get_demo_credentials("enterprise")))
        results["enterpriseDenied"] = enterprise.get(
            f"/match-reports/{report['id']}").status_code == 404
        record = {"generatedAt": datetime.now(UTC).isoformat(),
                  "scope": "Synthetic code plus saved synthetic vision; real text API",
                  "promptVersion": EVIDENCE_PROMPT_VERSION,
                  "sourceVersionId": source["versionId"], "report": report,
                  "states": states, "checks": results,
                  "visionCalledAgain": False, "humanSemanticReview": "pending",
                  "regionAccuracy": "not independently labeled", "billingVerified": False}
        path = directory / f"combined-visual-report-{stamp}.json"
        with path.open("x", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
        print(json.dumps({"output": path.name, "reportId": report["id"],
                          "checks": results, "usage": report["aiUsage"]}, ensure_ascii=False))
        return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
