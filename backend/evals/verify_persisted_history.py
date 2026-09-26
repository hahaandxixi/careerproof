"""Opt-in real, persisted history workflow using only synthetic local materials.

Creates a rule baseline with an implemented route, then evaluates a new version
with an empty route. Does not modify historical ratings to manufacture success.
--live explicitly permits model spending; each outcome is saved, including decline.
"""

import argparse
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile

import httpx

from app.agents.provider import EVIDENCE_PROMPT_VERSION
from evals.demo_credentials import get_demo_credentials
from evals.verify_deepseek_tool_report import BASE, data, wait

OLD_CODE = ('from fastapi import FastAPI, HTTPException\napp = FastAPI()\n'
            '@app.get("/health")\ndef health(name: str):\n'
            '    if not name.strip():\n'
            '        raise HTTPException(status_code=400, detail="name required")\n'
            '    return {"status": "ok", "name": name.strip()}\n')
CURRENT_CODE = ('from fastapi import FastAPI\napp = FastAPI()\n'
                '@app.get("/health")\ndef health(name: str):\n    pass\n')


def upload_code(client, project_id, code):
    archive = io.BytesIO()
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("app.py", code)
    version = data(client.post(f"/projects/{project_id}/versions",
                              files={"file": ("synthetic-history.zip", archive.getvalue(),
                                               "application/zip")}))
    wait(client, version["taskId"], timeout=60)
    return version


def exact_current_sources(report):
    for item in report["items"]:
        current = {e["citationId"]: e for e in item["evidenceList"]}
        if not set(item["aiCitationIds"]).issubset(current):
            return False
        for evidence in current.values():
            if not evidence["filePath"].endswith("/app.py"):
                return False
            excerpt = "\n".join(CURRENT_CODE.splitlines()[
                evidence["lineStart"] - 1:evidence["lineEnd"]])
            if excerpt != evidence["snippet"]:
                return False
    return bool(report["items"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    if not parser.parse_args().live:
        print("No calls made. --live creates local synthetic data and uses the configured API.")
        return 0
    endpoint = urlparse(BASE)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("This evaluation only accepts a local HTTP API")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    with (httpx.Client(base_url=BASE, timeout=30, trust_env=False) as enterprise,
          httpx.Client(base_url=BASE, timeout=30, trust_env=False) as student):
        data(enterprise.post("/auth/login", json=get_demo_credentials("enterprise")))
        organization = next(o for o in data(enterprise.get("/enterprises/me"))
                            if o["name"] == "CareerProof 合成演示企业")
        job = data(enterprise.post("/jobs", json={
            "enterpriseId": organization["id"], "title": f"历史补证合成验收 {timestamp}",
            "companyName": organization["name"], "description": "本机合成验收，不用于真实招聘。",
            "status": "published", "category": "software", "requirements": [{
                "skillName": "FastAPI", "weight": 5, "isRequired": True,
                "rawText": "FastAPI 路由需包含输入校验和响应处理；仅声明或空函数不足。"}]}))
        data(student.post("/auth/login", json=get_demo_credentials("student")))
        resume = data(student.post("/resumes", data={"title": f"历史验收简历 {timestamp}"},
                                   files={"file": ("synthetic-resume.txt",
                                           "合成学生：接触过 Python 和 FastAPI。".encode(),
                                           "text/plain")}))
        wait(student, resume["taskId"], timeout=60)
        project = data(student.post("/projects", json={"name": f"历史验收项目 {timestamp}",
                                                       "description": "合成版本撤回实质处理。"}))
        old = upload_code(student, project["id"], OLD_CODE)
        request = {"jobId": job["id"], "resumeVersionId": resume["versionId"],
                   "projectVersionIds": [old["versionId"]], "externalAiConsent": False}
        baseline_task = data(student.post("/matches", json=request))
        previous, _ = wait(student, baseline_task["taskId"])
        current = upload_code(student, project["id"], CURRENT_CODE)
        request.update(projectVersionIds=[current["versionId"]], externalAiConsent=True,
                       usePreviousReport=True)
        accepted = data(student.post("/matches", json=request))
        task, states = wait(student, accepted["taskId"])
        report = data(student.get(f"/match-reports/{task['reportId']}"))
        reloaded = data(student.get(f"/match-reports/{task['reportId']}"))
        comparison = data(student.get(
            f"/match-reports/{previous['reportId']}/comparison/{report['id']}"))
        denied = enterprise.get(f"/match-reports/{report['id']}").status_code
        calls = [c for c in report["aiToolCalls"]
                 if c.get("tool") == "get_previous_report_context"
                 and c.get("status") == "completed"]
        linked = len(calls) == 1 and calls[0].get("previousReportId") == previous["reportId"]
        source_exact = exact_current_sources(report)
        record = {"generatedAt": datetime.now(UTC).isoformat(),
                  "scope": "Local PostgreSQL and real model; synthetic sources only",
                  "promptVersion": EVIDENCE_PROMPT_VERSION, "jobId": job["id"],
                  "previousReportId": previous["reportId"], "reportId": report["id"],
                  "taskId": task["id"], "states": states, "report": report,
                  "comparison": comparison, "linkedHistoryRead": linked,
                  "currentSourcesExact": source_exact, "reloadStable": report == reloaded,
                  "enterpriseReadStatus": denied, "humanSemanticReview": "pending",
                  "billingVerified": False}
        path = Path(__file__).with_name(f"persisted-history-{timestamp}.json")
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": path.name, "reportId": report["id"],
                          "linkedHistoryRead": linked, "currentSourcesExact": source_exact,
                          "fallbackUsed": report["aiFallbackUsed"], "usage": report["aiUsage"]},
                         ensure_ascii=False))
        return 0 if (linked and source_exact and report == reloaded and denied == 404
                     and not report["aiFallbackUsed"]
                     and all(i["aiStatus"] == "validated" for i in report["items"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
