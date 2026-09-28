"""Close temporary evaluation jobs, preserving their requirements and reports.

Only known evaluation titles/descriptions in the demo organization are accepted.
This is evaluation cleanup, never a production job-name filter.
"""

import re
from urllib.parse import urlparse

import httpx

DEMO_COMPANY = "CareerProof 合成演示企业"
HISTORY_DESCRIPTION = "本机合成验收，不用于真实招聘。"
TOOL_TITLE = "Python 受控补检索（合成验收）"
TOOL_DESCRIPTION = "公开合成材料的受控 Function Calling 验收岗位。"
HISTORY_TITLES = re.compile(
    r"(?:历史完整报告 (?:injected-history|anchor-down|withdrawn-material|job-change)"
    r"（合成）\d{8}-\d{6}-\d{6}|改要求新岗位（合成）\d{8}-\d{6}-\d{6}"
    r"|历史补证合成验收 \d{8}-\d{6})"
)


def is_evaluation_job(job: dict) -> bool:
    return job.get("companyName") == DEMO_COMPANY and (
        (
            job.get("description") == HISTORY_DESCRIPTION
            and HISTORY_TITLES.fullmatch(job.get("title", "")) is not None
        )
        or (job.get("title") == TOOL_TITLE and job.get("description") == TOOL_DESCRIPTION)
    )


def _data(response: httpx.Response):
    response.raise_for_status()
    return response.json()["data"]


class TemporaryEvaluationJobs:
    """Register only jobs used by this run; always attempt to close all of them.

    The enterprise client must keep its own authenticated session through exit.
    Cleanup failures are recorded without raw transport errors or credentials.
    They fail a successful run, but never mask an existing evaluation exception.
    """

    def __init__(self, client: httpx.Client, record: dict):
        endpoint = urlparse(str(client.base_url))
        if (
            endpoint.scheme != "http"
            or endpoint.hostname not in {"127.0.0.1", "localhost"}
            or endpoint.path.rstrip("/") != "/api/v1"
        ):
            raise ValueError("Evaluation job cleanup requires a local /api/v1 endpoint")
        self.client = client
        self.record = record
        self.jobs: dict[str, dict] = {}
        self.record["jobCleanup"] = []

    def __enter__(self):
        return self

    def track(self, job: dict) -> dict:
        if not is_evaluation_job(job) or not job.get("enterpriseId") or not job.get("createdBy"):
            raise ValueError("Job outside known synthetic evaluation scope")
        self.jobs[job["id"]] = {
            key: job[key]
            for key in ("id", "title", "description", "companyName", "enterpriseId", "createdBy")
        }
        return job

    def create(self, payload: dict) -> dict:
        if not is_evaluation_job(payload):
            raise ValueError("Job outside known synthetic evaluation scope")
        return self.track(_data(self.client.post("/jobs", json=payload)))

    def __exit__(self, exc_type, exc_value, traceback):
        failed = False
        for job_id, expected in self.jobs.items():
            outcome = {"jobId": job_id, "status": "failed"}
            try:
                current = _data(self.client.get(f"/jobs/{job_id}"))
                if any(current.get(key) != value for key, value in expected.items()):
                    raise ValueError("Evaluation job identity changed; cleanup refused")
                if current["status"] != "closed":
                    updated = _data(self.client.patch(f"/jobs/{job_id}", json={"status": "closed"}))
                    if updated["status"] != "closed":
                        raise ValueError("Evaluation job was not closed")
                outcome["status"] = "closed"
            except Exception as error:
                failed = True
                outcome["errorType"] = type(error).__name__
            self.record["jobCleanup"].append(outcome)
        self.record["jobCleanupPassed"] = not failed
        if failed:
            self.record["passed"] = False
            if exc_type is None:
                raise RuntimeError("Synthetic job cleanup incomplete; see jobCleanup")
        return False
