"""Repeat only rules matching on the original selected versions, in owned PG."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).parent
BASE_EVIDENCE = EVIDENCE.parent
RUN = ROOT / "backend/.tmp/complete-project-20261021"
SERVER = ROOT / "backend/.tmp/agent-display-20261021/source/backend"
CONTAINER = "careerproof-agent-display-20261021"
state = json.loads((RUN / "careerproof-state.json").read_text(encoding="utf-8"))
credentials = json.loads((RUN / "credentials.json").read_text(encoding="utf-8"))
manifest = json.loads((BASE_EVIDENCE / "material-manifest.json").read_text(encoding="utf-8"))
old_probe = json.loads((BASE_EVIDENCE / "detector-probe.json").read_text(encoding="utf-8"))
sha = lambda content: hashlib.sha256(content).hexdigest()
assert sha(Path(manifest["zip"]).read_bytes()) == manifest["zipSha256"]
target = SERVER / "app/tools/code_analyzer.py"
assert sha(target.read_bytes()) == old_probe["moduleSha256"], "Stage file changed; do not overwrite"
configuration = dict(line.split("=", 1) for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines() if "=" in line)
url = urlparse(configuration["DATABASE_URL"].strip('"'))
assert (url.hostname, url.port, url.path) == ("127.0.0.1", 55442, "/cp_agent_display_20261021")
assert configuration["AI_EXTERNAL_ENABLED"].lower() == "false"
info = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER]))[0]
assert info["State"]["Running"]
assert info["Config"]["Labels"]["careerproof.scope"] == "agent-display-20261021"
assert info["NetworkSettings"]["Ports"]["5432/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "55442"}]


def sql(query):
    return subprocess.check_output(["docker", "exec", CONTAINER, "psql", "-U", "cp_agent", "-d", "cp_agent_display_20261021",
                                    "-At", "-v", "ON_ERROR_STOP=1", "-c", query], encoding="utf-8").strip()


def stable_rows():
    return {name: sql(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]') FROM {name} t")
            for name in ["match_reports", "applications", "ai_request_attempts", "ai_usage_logs"]}


before = stable_rows()
target.write_bytes((ROOT / "backend/app/tools/code_analyzer.py").read_bytes())
with socket.socket() as free:
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
env = dict(os.environ, PYTHONPATH=str(SERVER), PYTHONIOENCODING="utf-8")
with (EVIDENCE / "api.raw.out").open("wb") as log:
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                               "--port", str(port), "--no-proxy-headers"], cwd=SERVER, env=env,
                               stdout=log, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        for _ in range(100):
            assert process.poll() is None, "Owned API process exited"
            try:
                if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", trust_env=False).status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError("API not ready")
        with httpx.Client(base_url=f"http://127.0.0.1:{port}/api/v1", timeout=45, trust_env=False) as client:
            def data(method, path, **kwargs):
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                value = response.json()
                assert value["code"] == 0, value
                return value["data"]

            data("POST", "/auth/login", json={"email": credentials["studentEmail"], "password": credentials["password"]})
            old_report = data("GET", "/match-reports/" + state["reportId"])
            started = data("POST", "/matches", json={"jobId": state["jobId"], "resumeVersionId": state["resumeVersionId"],
                           "projectVersionIds": [state["projectVersionId"]], "externalAiConsent": False})
            for _ in range(150):
                task = data("GET", "/analysis-tasks/" + started["taskId"])
                if task["status"] == "completed":
                    break
                assert task["status"] != "failed", task
                time.sleep(.1)
            else:
                raise RuntimeError("Rule report timeout")
            report = data("GET", "/match-reports/" + task["reportId"])
            assert report["id"] != old_report["id"]
            assert report["analysisMode"] == "rules" and not report["aiToolCalls"]
            assert report["materials"] == old_report["materials"]
            assert data("GET", "/match-reports/" + state["reportId"]) == old_report
            sql_item = next(item for item in report["items"] if item["skill"] == "SQL")
            assert any(e["filePath"].endswith("campus_signup/schema.sql")
                       and e["evidenceType"] == "sql_schema" for e in sql_item["evidenceList"])
            (EVIDENCE / "report-after.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (EVIDENCE / "comparison.json").write_text(json.dumps(data("GET", f"/match-reports/{old_report['id']}/comparison/{report['id']}"),
                                                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        process.terminate()
        process.wait(timeout=10)

after = stable_rows()
old_rows = json.loads(before["match_reports"])
new_rows = {row["id"]: row for row in json.loads(after["match_reports"])}
assert all(new_rows[row["id"]] == row for row in old_rows)
assert all(before[name] == after[name] for name in ["applications", "ai_request_attempts", "ai_usage_logs"])
assert sha(Path(manifest["zip"]).read_bytes()) == manifest["zipSha256"]
result = {"oldReportId": state["reportId"], "newReportId": report["id"], "sameMaterialVersions": True,
          "allHistoricalReportRowsUnchanged": True, "applicationsUnchanged": True,
          "aiRequestAttemptsAndUsageUnchanged": True, "realModelRequests": 0,
          "schemaNowInRuleEvidence": True, "sourceFile": str(target), "sourceSha256": sha(target.read_bytes()),
          "scope": "Only SQL CREATE TABLE IF NOT EXISTS compatibility; Python business selection still unresolved",
          "newApiProcessStopped": True, "port": port, "normalServicesTouched": False}
(EVIDENCE / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print("PASS: same frozen versions; schema retrieved in new rules report; old reports/applications unchanged; no model attempts.")
print("NEW REPORT", report["id"])
