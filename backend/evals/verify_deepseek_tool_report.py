"""Verify one persisted report with a real bounded DeepSeek tool call.

Only repository-owned synthetic material is uploaded. Keys, cookies and request
headers are never written to the result artifact.
"""

from __future__ import annotations

import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx

from evals.seed_demo import PASSWORD

BASE = "http://127.0.0.1:8000/api/v1"
JOB_TITLE = "Python 受控补检索（合成验收）"


def data(response: httpx.Response):
    response.raise_for_status()
    return response.json()["data"]


def wait(client: httpx.Client, task_id: str, timeout: int = 240):
    started = time.monotonic()
    states = []
    last = None
    while time.monotonic() - started < timeout:
        task = data(client.get(f"/analysis-tasks/{task_id}"))
        state = (task["status"], task["progress"], task["currentStep"])
        if state != last:
            states.append(
                {"status": state[0], "progress": state[1], "currentStep": state[2]}
            )
            last = state
        if task["status"] == "completed":
            return task, states
        if task["status"] in {"failed", "cancelled"}:
            raise RuntimeError(f"Task failed: {task.get('errorMessage')}; states={states}")
        time.sleep(0.25)
    raise TimeoutError(f"Task did not finish; states={states}")


def ensure_job(client: httpx.Client) -> dict:
    data(
        client.post(
            "/auth/login",
            json={"email": "demo.enterprise@example.com", "password": PASSWORD},
        )
    )
    organization = next(
        item
        for item in data(client.get("/enterprises/me"))
        if item["name"] == "CareerProof 合成演示企业"
    )
    jobs = data(client.get("/jobs/mine", params={"q": "受控补检索", "pageSize": 100}))[
        "items"
    ]
    job = next((item for item in jobs if item["title"] == JOB_TITLE), None)
    if job is None:
        job = data(
            client.post(
                "/jobs",
                json={
                    "enterpriseId": organization["id"],
                    "title": JOB_TITLE,
                    "companyName": organization["name"],
                    "description": "公开合成材料的受控 Function Calling 验收岗位。",
                    "status": "published",
                    "category": "software",
                    "city": "深圳",
                    "employmentType": "internship",
                    "requirements": [
                        {
                            "skillName": "Python",
                            "weight": 5,
                            "isRequired": True,
                            "rawText": "Python 业务函数需包含输入校验、服务调用和响应处理",
                        }
                    ],
                },
            )
        )
    elif job["status"] != "published":
        job = data(client.patch(f"/jobs/{job['id']}", json={"status": "published"}))
    data(client.post("/auth/logout"))
    return job


def build_archive(source: Path, destination: Path) -> None:
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(source).as_posix())


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = Path(__file__).with_name(f"deepseek-tool-report-{timestamp}.json")
    with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
        job = ensure_job(client)
        data(
            client.post(
                "/auth/login",
                json={"email": "demo.student@example.com", "password": PASSWORD},
            )
        )
        resume_path = root / "demo" / "student-resume.txt"
        resume = data(
            client.post(
                "/resumes",
                data={"title": f"Function Calling 合成简历 {timestamp}"},
                files={"file": (resume_path.name, resume_path.read_bytes(), "text/plain")},
            )
        )
        wait(client, resume["taskId"], timeout=60)
        project = data(
            client.post(
                "/projects",
                json={
                    "name": f"Function Calling 合成项目 {timestamp}",
                    "description": "只使用仓库内公开合成代码验证受控补检索。",
                },
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "evidence-function-call.zip"
            build_archive(root / "demo" / "evidence-function-call", archive_path)
            version = data(
                client.post(
                    f"/projects/{project['id']}/versions",
                    files={
                        "file": (
                            archive_path.name,
                            archive_path.read_bytes(),
                            "application/zip",
                        )
                    },
                )
            )
        wait(client, version["taskId"], timeout=60)
        accepted = data(
            client.post(
                "/matches",
                json={
                    "jobId": job["id"],
                    "resumeVersionId": resume["versionId"],
                    "projectVersionIds": [version["versionId"]],
                    "externalAiConsent": True,
                },
            )
        )
        task, states = wait(client, accepted["taskId"])
        report = data(client.get(f"/match-reports/{task['reportId']}"))
        calls = report["aiToolCalls"]
        successful_calls = [call for call in calls if call.get("resultCount") == 1]
        result = {
            "scope": "Repository-owned synthetic source through local API and real DeepSeek",
            "generatedAt": datetime.now(UTC).isoformat(),
            "taskId": accepted["taskId"],
            "reportId": task["reportId"],
            "states": states,
            "steps": task["steps"],
            "analysisMode": report["analysisMode"],
            "provider": report["aiProvider"],
            "model": report["aiModel"],
            "fallbackUsed": report["aiFallbackUsed"],
            "usage": report["aiUsage"],
            "toolCalls": calls,
            "items": report["items"],
        }
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if report["analysisMode"] != "ai_evidence" or report["aiFallbackUsed"]:
            raise SystemExit(f"AI report fell back to rules; see {output.name}")
        if not successful_calls:
            raise SystemExit(
                f"Model did not execute a successful retrieval tool; see {output.name}"
            )
        if not all(item["aiStatus"] == "validated" for item in report["items"]):
            raise SystemExit(f"Report contains an unvalidated AI item; see {output.name}")
        if not any(
            item.get("evidenceLevel") == 3
            and successful_calls[0].get("citationId") in item.get("aiCitationIds", [])
            for item in report["items"]
        ):
            raise SystemExit(
                f"Retrieved evidence did not support the expected level-3 item; see {output.name}"
            )
        print(
            json.dumps(
                {
                    "output": output.name,
                    "reportId": task["reportId"],
                    "toolCall": successful_calls[0],
                    "usage": report["aiUsage"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
