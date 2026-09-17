"""Create one complete AI report from public synthetic demo material through the local API."""

import json
import time
from datetime import datetime
from pathlib import Path

import httpx

from evals.seed_demo import PASSWORD

BASE = "http://127.0.0.1:8000/api/v1"


def data(response):
    response.raise_for_status()
    return response.json()["data"]


def wait(client, task_id, timeout=240):
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


def main():
    root = Path(__file__).resolve().parents[2]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = Path(__file__).with_name(f"ai-full-report-{timestamp}.json")
    with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
        data(
            client.post(
                "/auth/login",
                json={"email": "demo.student@example.com", "password": PASSWORD},
            )
        )
        jobs = data(client.get("/jobs", params={"q": "Python 后端", "pageSize": 100}))[
            "items"
        ]
        job = next(
            item
            for item in jobs
            if item["title"] == "Python 后端开发实习生（合成演示）"
            and item["companyName"] == "CareerProof 合成演示企业"
        )
        resume_path = root / "demo" / "student-resume.txt"
        resume = data(
            client.post(
                "/resumes",
                data={"title": f"AI完整报告合成简历{timestamp}"},
                files={"file": (resume_path.name, resume_path.read_bytes(), "text/plain")},
            )
        )
        wait(client, resume["taskId"], timeout=60)
        project = data(
            client.post(
                "/projects",
                json={
                    "name": f"AI完整报告合成项目{timestamp}",
                    "description": "仅使用公开合成材料进行模型与降级链路验收。",
                },
            )
        )
        archive = root / "demo" / "evidence-api.zip"
        version = data(
            client.post(
                f"/projects/{project['id']}/versions",
                files={"file": (archive.name, archive.read_bytes(), "application/zip")},
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
                },
            )
        )
        task, states = wait(client, accepted["taskId"])
        report = data(client.get(f"/match-reports/{task['reportId']}"))
        result = {
            "scope": "Synthetic local API and real configured model; no user resume",
            "taskId": accepted["taskId"],
            "reportId": task["reportId"],
            "states": states,
            "steps": task["steps"],
            "analysisMode": report["analysisMode"],
            "provider": report["aiProvider"],
            "model": report["aiModel"],
            "fallbackUsed": report["aiFallbackUsed"],
            "aiRatedCount": sum(
                item.get("evidenceLevelSource") == "ai_preliminary"
                for item in report["items"]
            ),
            "validatedItems": sum(item["aiStatus"] == "validated" for item in report["items"]),
            "items": report["items"],
            "usage": report["aiUsage"],
        }
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": output.name,
                    "reportId": result["reportId"],
                    "analysisMode": result["analysisMode"],
                    "fallbackUsed": result["fallbackUsed"],
                    "aiRatedCount": result["aiRatedCount"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
