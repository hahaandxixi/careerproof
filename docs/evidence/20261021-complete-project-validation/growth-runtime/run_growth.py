"""Append actual execution observations, then use the existing growth HTTP APIs."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).parent
BASE = EVIDENCE.parent
RUN = ROOT / "backend/.tmp/complete-project-20261021"
state = json.loads((RUN / "careerproof-state.json").read_text(encoding="utf-8"))
credentials = json.loads((RUN / "credentials.json").read_text(encoding="utf-8"))
manifest = json.loads((BASE / "material-manifest.json").read_text(encoding="utf-8"))
fixed = json.loads((BASE / "sql-fix/result.json").read_text(encoding="utf-8"))
sha = lambda value: hashlib.sha256(value).hexdigest()
assert not (RUN / "growth-runtime-state.json").exists(), "Do not blindly repeat writes"
assert sha(Path(manifest["zip"]).read_bytes()) == manifest["zipSha256"]
container = "careerproof-agent-display-20261021"
info = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
assert info["State"]["Running"]
assert info["Config"]["Labels"]["careerproof.scope"] == "agent-display-20261021"
assert info["NetworkSettings"]["Ports"]["5432/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "55442"}]
env_file = ROOT / "backend/.tmp/agent-display-20261021/source/backend/.env"
configuration = dict(line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines() if "=" in line)
assert "127.0.0.1:55442/cp_agent_display_20261021" in configuration["DATABASE_URL"]
assert configuration["AI_EXTERNAL_ENABLED"].lower() == "false"


def sql(query):
    return subprocess.check_output(["docker", "exec", container, "psql", "-U", "cp_agent", "-d", "cp_agent_display_20261021",
                                    "-At", "-v", "ON_ERROR_STOP=1", "-c", query], encoding="utf-8").strip()


def snapshot():
    return {name: sql(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]') FROM {name} t")
            for name in ["match_reports", "applications", "ai_request_attempts", "ai_usage_logs"]}


with zipfile.ZipFile(manifest["zip"]) as archive:
    original = {name: archive.read(name) for name in archive.namelist()}
assert {name: sha(content) for name, content in original.items()} == manifest["files"]
added = {
    "runtime/http-observations.json": (BASE / "business-results.json").read_bytes(),
    "runtime/pytest-output.txt": (BASE / "project-tests.raw.out").read_bytes(),
    "runtime/source-hashes.json": (json.dumps(manifest["files"], indent=2) + "\n").encode(),
    "runtime/README.txt": b"Local synthetic execution observations collected outside CareerProof.\n"
                          b"Original business source is unchanged. No independent review or authorship certification.\n"
                          b"HTTP responses and pytest output describe the recorded local environment only.\n",
}
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name, body in sorted({**original, **added}.items()):
        item = zipfile.ZipInfo(name, (2026, 10, 21, 0, 0, 0))
        item.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(item, body)
package = ROOT / "output/demo/CareerProof-campus-signup-v2-runtime.zip"
assert not package.exists()
package.write_bytes(buffer.getvalue())
freeze = {"zip": str(package), "sha256": sha(package.read_bytes()), "version1Sha256": manifest["zipSha256"],
          "originalNineFilesUnchanged": True, "addedActualOutputs": {name: sha(body) for name, body in added.items()},
          "evaluationPlanNotUploaded": True, "targetGrade": None, "frozenBeforeGrowthAnalyze": True}
(EVIDENCE / "v2-manifest.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
before = snapshot()
calls = []
with httpx.Client(base_url="http://127.0.0.1:8108/api/v1", timeout=60, trust_env=False) as client:
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
            time.sleep(.1)
        raise RuntimeError("Task timeout")

    data("POST", "/auth/login", json={"email": credentials["studentEmail"], "password": credentials["password"]})
    baseline = data("GET", "/match-reports/" + fixed["newReportId"])
    sql_item = next(item for item in baseline["items"] if item["skill"] == "SQL")
    assert data("GET", f"/match-reports/{baseline['id']}/growth-tasks/{sql_item['requirementId']}") is None
    growth = data("POST", "/match-reports/" + baseline["id"] + "/growth-tasks", json={
        "requirementId": sql_item["requirementId"], "gapKind": "execution",
        "deliverable": "补交同一源码版本的本地报名、故障回滚和重启读取记录，标明环境及源码摘要。",
        "steps": ["保留原源码并整理已产生的真实HTTP回执和测试输出", "上传包含运行记录的新材料版本并与固定基准比较"],
        "acceptanceChecks": ["运行记录能对应原源码摘要", "成功及拒绝状态、故障回滚与重启读取均有实际观测", "不将本地记录当作独立认证或保证评级提升"],
    })
    partial = {"growthTaskId": growth["id"], "baseReportId": baseline["id"], "projectId": state["projectId"]}
    (RUN / "growth-runtime-state.json").write_text(json.dumps(partial), encoding="utf-8")
    uploaded = data("POST", "/projects/" + state["projectId"] + "/versions",
                    data={"requestId": str(uuid4())}, files={"file": (package.name, package.read_bytes(), "application/zip")})
    scan = settle(uploaded["taskId"])
    attached = data("PUT", "/growth-tasks/" + growth["id"] + "/materials", json={
        "resumeVersionId": state["resumeVersionId"], "projectVersionIds": [uploaded["versionId"]]})
    started = data("POST", "/growth-tasks/" + growth["id"] + "/analyze", json={"externalAiConsent": False})
    match_task = settle(started["analysisTaskId"])
    report = data("GET", "/match-reports/" + match_task["reportId"])
    saved = data("GET", "/growth-tasks/" + growth["id"])
    comparison = data("GET", f"/match-reports/{baseline['id']}/comparison/{report['id']}")
    assert report["analysisMode"] == "rules" and report["aiProvider"] is None
    assert report["id"] != baseline["id"]
    assert data("GET", "/match-reports/" + baseline["id"]) == baseline
    assert saved["targetReportId"] == report["id"]
    version = next(material for material in report["materials"] if material["kind"] == "project")
    assert version["id"] == uploaded["versionId"] and version["versionNumber"] == 2
    for item in report["items"]:
        for evidence in item["evidenceList"]:
            assert evidence["projectVersionId"] == uploaded["versionId"]
    files = data("GET", "/project-versions/" + uploaded["versionId"] + "/files")
    assert len(files) == len(original) + len(added)
    for name, payload in {"report-after.json": report, "growth-task.json": saved, "comparison.json": comparison,
                          "http-calls.json": calls, "scan-task.json": scan}.items():
        (EVIDENCE / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    final = {**partial, "newReportId": report["id"], "newProjectVersionId": uploaded["versionId"],
             "projectVersionNumber": 2, "rulesOnly": True, "mockReport": False,
             "growthUrl": "http://127.0.0.1:3108/growth/" + growth["id"],
             "reportUrl": "http://127.0.0.1:3108/reports/" + report["id"]}
    (RUN / "growth-runtime-state.json").write_text(json.dumps(final), encoding="utf-8")
    (EVIDENCE / "page-entry.json").write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")

after = snapshot()
new_reports = {row["id"]: row for row in json.loads(after["match_reports"])}
assert all(new_reports[row["id"]] == row for row in json.loads(before["match_reports"]))
assert all(before[name] == after[name] for name in ["applications", "ai_request_attempts", "ai_usage_logs"])
proof = {"originalNineSourceFilesUnchanged": True, "allHistoricalReportsUnchanged": True,
         "applicationsUnchanged": True, "aiRequestAttemptsAndUsageUnchanged": True,
         "newMaterialVersionActuallyUsed": True, "newFiles": len(files), "realModelRequests": 0,
         "normalDatabaseTouched": False, "uiVerification": "Not performed: 3108 startup rejected by automatic approval review"}
(EVIDENCE / "result.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
print("PASS: real growth task -> uploaded v2 execution observations -> rules report -> fixed-base comparison.")
print("GROWTH", growth["id"], "REPORT", report["id"])
