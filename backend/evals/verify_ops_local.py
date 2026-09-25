"""Local synthetic API acceptance. Does not claim browser or semantic QA."""

import json
import time
from pathlib import Path

import httpx

from app.core.config import settings
from evals.demo_credentials import get_demo_credentials


def main():
    if settings.ai_external_enabled:
        raise RuntimeError("This acceptance requires external AI disabled")
    output = Path("evals/ops-api-20260917.json")
    if output.exists():
        raise RuntimeError("Preserve previous acceptance output")
    results = []

    def data(response):
        response.raise_for_status()
        return response.json()["data"]

    with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=30, trust_env=False) as c:

        def wait(task_id):
            for _ in range(60):
                task = data(c.get(f"/analysis-tasks/{task_id}"))
                if task["status"] == "completed":
                    return task
                if task["status"] in {"failed", "cancelled"}:
                    raise RuntimeError(f"Task failed: {task.get('errorMessage')}")
                time.sleep(1)
            raise TimeoutError("Task not finished within 60 checks")

        data(
            c.post("/auth/login", json=get_demo_credentials("student"))
        )
        jobs = data(c.get("/jobs", params={"q": "合成演示", "pageSize": 100}))["items"]
        for slug, title in [("devops", "自动化运维工程师"), ("dba", "数据库工程师 DBA")]:
            job = next(
                j
                for j in jobs
                if j["title"] == title + "（合成演示）"
                and j["companyName"] == "CareerProof 合成演示企业"
            )
            resume = Path("../demo/roles") / slug / "resume.txt"
            accepted = data(
                c.post(
                    "/resumes",
                    data={"title": title + "验收简历0917"},
                    files={"file": (resume.name, resume.read_bytes(), "text/plain")},
                )
            )
            wait(accepted["taskId"])
            project = data(
                c.post(
                    "/projects",
                    json={
                        "name": title + "工程验收0917",
                        "description": "合成 API 验收；脚本未执行，复核操作不代表人工语义通过。",
                    },
                )
            )
            archive = Path("../jianli/public/demo-assets/roles") / (slug + "-project.zip")
            version = data(
                c.post(
                    f"/projects/{project['id']}/versions",
                    files={"file": (archive.name, archive.read_bytes(), "application/zip")},
                )
            )
            wait(version["taskId"])
            files = data(c.get(f"/project-versions/{version['versionId']}/files"))
            assert len(files) == 5
            match = data(
                c.post(
                    "/matches",
                    json={
                        "jobId": job["id"],
                        "resumeVersionId": accepted["versionId"],
                        "projectVersionIds": [version["versionId"]],
                    },
                )
            )
            task = wait(match["taskId"])
            report_id = task["reportId"]
            report = data(c.get(f"/match-reports/{report_id}"))
            assert len(report["items"]) == 5
            assert all(item["verdict"] != "unsupported" for item in report["items"])
            assert report["analysisMode"] != "ai_evidence"
            with c.stream("GET", f"/analysis-tasks/{match['taskId']}/events") as stream:
                stream.raise_for_status()
                assert any("task.completed" in line for line in stream.iter_lines())
            item = next(i for i in report["items"] if i["evidenceList"])
            note = "自动化验收：核对备注持久化，语义复核仍待人工完成。"
            data(
                c.patch(
                    f"/match-reports/{report_id}/items/{item['requirementId']}/review",
                    json={"status": "pending", "note": note},
                )
            )
            refreshed = data(c.get(f"/match-reports/{report_id}"))
            assert (
                next(i for i in refreshed["items"] if i["requirementId"] == item["requirementId"])[
                    "reviewerNote"
                ]
                == note
            )
            results.append(
                dict(
                    role=slug,
                    reportId=report_id,
                    taskId=match["taskId"],
                    score=report["overallScore"],
                    files=5,
                    reviewNotePersisted=True,
                    terminalSseVerified=True,
                    report=refreshed,
                )
            )
            output.write_text(
                json.dumps(
                    {
                        "scope": "Synthetic API acceptance; not browser or human semantic QA",
                        "results": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "utf-8",
            )
            print(
                json.dumps({"role": slug, "reportId": report_id, "score": report["overallScore"]}),
                flush=True,
            )
        data(c.post("/auth/logout"))


if __name__ == "__main__":
    main()
