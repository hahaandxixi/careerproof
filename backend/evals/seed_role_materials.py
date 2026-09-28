"""Opt-in named demo uploads: one paired resume/project per career, no model calls."""

import argparse
import json
from datetime import datetime
from pathlib import Path

import httpx

from evals.demo_credentials import get_demo_credentials
from evals.verify_deepseek_tool_report import data, wait

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000/api/v1"
DESCRIPTION = "合成静态测试作品，未执行，不代表本人贡献。"


def seed(client, cases, assets, records):
    """Reuse exact named fixtures; never rename, delete or merge existing materials."""
    resumes = data(client.get("/resumes"))
    projects = data(client.get("/projects"))
    for case in cases:
        record = {"caseId": case["caseId"], "title": case["title"], "stage": "resume"}
        records.append(record)
        matching = [r for r in resumes if r["title"] == case["resumeName"]]
        if len(matching) > 1:
            raise ValueError("Ambiguous demo resume; leave existing materials unchanged")
        if matching:
            versions = [
                v
                for v in matching[0]["versions"]
                if v["originalFilename"] == case["resumeFilename"]
            ]
            if len(versions) != 1 or versions[0]["status"] != "completed":
                raise ValueError("Demo resume version needs manual inspection")
            resume_version_id = versions[0]["id"]
            record["resumeReused"] = True
        else:
            upload = data(
                client.post(
                    "/resumes",
                    data={"title": case["resumeName"]},
                    files={
                        "file": (
                            case["resumeFilename"],
                            (assets / case["resumeFilename"]).read_bytes(),
                            "text/plain",
                        ),
                    },
                )
            )
            record["resumeVersionId"] = upload["versionId"]
            wait(client, upload["taskId"], timeout=90)
            resume_version_id = upload["versionId"]
            record["resumeReused"] = False
        record.update(resumeVersionId=resume_version_id, stage="project")
        matching = [p for p in projects if p["name"] == case["projectName"]]
        if len(matching) > 1:
            raise ValueError("Ambiguous demo project; leave existing materials unchanged")
        if matching:
            project = matching[0]
            if project["description"] != DESCRIPTION:
                raise ValueError("Named project outside expected demo scope")
        else:
            project = data(
                client.post(
                    "/projects",
                    json={
                        "name": case["projectName"],
                        "description": DESCRIPTION,
                    },
                )
            )
        record["projectId"] = project["id"]
        versions = data(client.get(f"/projects/{project['id']}/versions"))
        matching_versions = [
            v for v in versions if v["originalFilename"] == case["projectFilename"]
        ]
        if matching_versions:
            if len(matching_versions) != 1 or matching_versions[0]["status"] != "completed":
                raise ValueError("Demo project version needs manual inspection")
            record.update(projectVersionId=matching_versions[0]["id"], projectReused=True)
        else:
            upload = data(
                client.post(
                    f"/projects/{project['id']}/versions",
                    data={
                        "materialRole": "portfolio",
                    },
                    files={
                        "file": (
                            case["projectFilename"],
                            (assets / case["projectFilename"]).read_bytes(),
                            "application/zip",
                        )
                    },
                )
            )
            record.update(projectVersionId=upload["versionId"], projectReused=False)
            wait(client, upload["taskId"], timeout=90)
        record["stage"] = "completed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cases = json.loads((ROOT / "demo/role-cases.json").read_text("utf-8"))
    assets = ROOT / "jianli/public/demo-assets/cases"
    # Validate every pair before uploading anything.
    for case in cases:
        for key in ("resumeFilename", "projectFilename", "scriptFilename"):
            if not (assets / case[key]).is_file():
                parser.error("Build all named role assets before importing")
    if not args.apply:
        print("Plan only: nine named pairs. --apply uploads and parses local synthetic material.")
        return 0
    record = {"modelCalls": 0, "cases": [], "passed": False}
    try:
        with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
            user = data(client.post("/auth/login", json=get_demo_credentials("student")))["user"]
            if user["role"] != "student":
                raise ValueError("Only the configured demo student may receive test materials")
            seed(client, cases, assets, record["cases"])
            record["passed"] = True
    except Exception as error:
        record["errorType"] = type(error).__name__
    path = ROOT / "backend/.tmp" / f"role-materials-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "passed": record["passed"],
                "completedPairs": sum(c["stage"] == "completed" for c in record["cases"]),
                "modelCalls": 0,
                "output": path.name,
                "errorType": record.get("errorType"),
            }
        )
    )
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
