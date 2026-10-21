"""Use only existing HTTP upload/scan/match APIs in the owned isolated server."""
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import urlparse
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).parent
RUN = ROOT / "backend/.tmp/complete-project-20261021"
ISOLATED = ROOT / "backend/.tmp/agent-display-20261021/source"
CONTAINER = "careerproof-agent-display-20261021"
DATABASE = "cp_agent_display_20261021"
manifest = json.loads((EVIDENCE / "material-manifest.json").read_text(encoding="utf-8"))
plan = json.loads((EVIDENCE / "evaluation-plan.json").read_text(encoding="utf-8"))
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(Path(manifest["zip"]).read_bytes()) == manifest["zipSha256"]
assert sha(Path(manifest["resume"]).read_bytes()) == manifest["resumeSha256"]
assert not (RUN / "careerproof-state.json").exists()
configuration = {}
for line in (ISOLATED / "backend/.env").read_text(encoding="utf-8").splitlines():
    if "=" in line:
        key, value = line.split("=", 1)
        configuration[key] = value.strip().strip('"')
target = urlparse(configuration["DATABASE_URL"])
assert (target.hostname, target.port, target.path) == ("127.0.0.1", 55442, "/" + DATABASE)
assert configuration["AI_EXTERNAL_ENABLED"].lower() == "false"
info = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER]))[0]
assert info["Config"]["Labels"]["careerproof.scope"] == "agent-display-20261021"
assert info["NetworkSettings"]["Ports"]["5432/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "55442"}]
assert info["State"]["Running"]


def sql(query):
    return subprocess.check_output(["docker", "exec", CONTAINER, "psql", "-U", "cp_agent", "-d", DATABASE,
                                    "-At", "-v", "ON_ERROR_STOP=1", "-c", query], encoding="utf-8").strip()


assert sql("SELECT current_database()") == DATABASE


def snapshot():
    return {name: sql(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text, '[]') FROM {name} t")
            for name in ["match_reports", "applications", "ai_request_attempts", "ai_usage_logs"]}


before = snapshot()
password = secrets.token_urlsafe(24)
credentials = {"studentEmail": "complete-project-student@example.com",
               "enterpriseEmail": "complete-project-enterprise@example.com", "password": password}
assert not (RUN / "credentials.json").exists()
(RUN / "credentials.json").write_text(json.dumps(credentials), encoding="utf-8")
calls = []
with httpx.Client(base_url="http://127.0.0.1:3108/backend/api/v1", timeout=60, trust_env=False) as client:
    def data(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        calls.append({"method": method, "path": path, "status": response.status_code})
        response.raise_for_status()
        result = response.json()
        assert result["code"] == 0, result
        return result["data"]

    def settle(task_id):
        for _ in range(200):
            task = data("GET", "/analysis-tasks/" + task_id)
            if task["status"] == "completed":
                return task
            assert task["status"] not in {"failed", "cancelled"}, task
            time.sleep(.15)
        raise RuntimeError("Task timeout")

    data("POST", "/auth/register", json={"email": credentials["enterpriseEmail"], "password": password,
         "displayName": "完整项目验证企业（虚构）", "role": "enterprise"})
    organization = data("POST", "/enterprises", json={"name": "校园活动项目实验室（虚构）"})
    job = data("POST", "/jobs", json={"enterpriseId": organization["id"], "title": "校园活动后端：完整项目材料验证",
               "companyName": organization["name"], "description": "合成项目材料评估，不是真实招聘；核对API、业务、持久化与测试。",
               "status": "published", "category": "software", "city": "本地合成环境", "employmentType": "internship",
               "requirements": [{"rawText": row["requirement"], "skillName": row["skill"], "weight": 5,
                                 "isRequired": True} for row in plan["requirements"]]})
    data("POST", "/auth/register", json={"email": credentials["studentEmail"], "password": password,
         "displayName": "林舟（虚构项目验证）", "role": "student"})
    resume = data("POST", "/resumes", data={"title": "校园活动项目合成简历"},
                  files={"file": ("resume.txt", Path(manifest["resume"]).read_bytes(), "text/plain")})
    resume_task = settle(resume["taskId"])
    project = data("POST", "/projects", json={"name": "Campus Signup：完整业务实现", "requestId": str(uuid4())})
    version = data("POST", "/projects/" + project["id"] + "/versions", data={"requestId": str(uuid4())},
                   files={"file": ("campus-signup-v1.zip", Path(manifest["zip"]).read_bytes(), "application/zip")})
    scan_task = settle(version["taskId"])
    files = data("GET", "/project-versions/" + version["versionId"] + "/files")
    previews = [data("GET", "/project-files/" + item["id"]) for item in files]
    match = data("POST", "/matches", json={"jobId": job["id"], "resumeVersionId": resume["versionId"],
                     "projectVersionIds": [version["versionId"]], "externalAiConsent": False})
    match_task = settle(match["taskId"])
    report = data("GET", "/match-reports/" + match_task["reportId"])
    assert report["analysisMode"] == "rules", report["analysisMode"]
    assert report["aiProvider"] in {None, "rules"}, report["aiProvider"]
    assert not report["aiToolCalls"]
    assert all(not item.get("aiCitationIds") for item in report["items"])
    search_results = {row["key"]: data("GET", "/knowledge/search", params={"q": row["skill"], "limit": 20})
                      for row in plan["requirements"]}
    # Preserve order/results without storing the same large source five times.
    unique_hits = {row["id"]: row for rows in search_results.values() for row in rows}
    compact_search = {"hitsById": unique_hits,
                      "queryResults": {key: [row["id"] for row in rows] for key, rows in search_results.items()}}
    state = {"reportId": report["id"], "taskId": match["taskId"], "jobId": job["id"], "projectId": project["id"],
             "resumeVersionId": resume["versionId"], "projectVersionId": version["versionId"],
             "reportUrl": "http://127.0.0.1:3108/reports/" + report["id"], "rulesOnly": True, "mockReport": False}
    for filename, payload in {"report.json": report, "project-files.json": files, "project-previews.json": previews,
                              "knowledge-search.json": compact_search, "task-results.json": {"resume": resume_task,
                              "scan": scan_task, "match": match_task}, "http-calls.json": calls, "page-entry.json": state}.items():
        (EVIDENCE / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "careerproof-state.json").write_text(json.dumps(state), encoding="utf-8")

after = snapshot()
before_reports = json.loads(before["match_reports"])
after_reports = {row["id"]: row for row in json.loads(after["match_reports"])}
assert all(after_reports[row["id"]] == row for row in before_reports)
for name in ["applications", "ai_request_attempts", "ai_usage_logs"]:
    assert before[name] == after[name], name
assert sha(Path(manifest["zip"]).read_bytes()) == manifest["zipSha256"]
proof = {"database": DATABASE, "port": 55442, "containerScope": "agent-display-20261021",
         "externalAiEnabled": False, "externalAiConsent": False, "normalDatabaseTouched": False,
         "oldSyntheticReportsUnchanged": True, "applicationsUnchanged": True,
         "aiRequestAttemptsUnchanged": True, "aiUsageLogsUnchanged": True,
         "materialZipUnchanged": True, "reviewRubricInUploadedArchive": False,
         "oldReportsCount": len(before_reports), "newReportsCount": len(after_reports),
         "runtimeSource": str(ISOLATED), "backendBaseCommit": "75d6c59",
         "backendReadOnlyDisplayProjectionPresent": True}
(EVIDENCE / "isolation-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
print("Real upload/scan/rules report:", state["reportUrl"])
print("Preserved old reports and applications. No model attempts/usage created.")
