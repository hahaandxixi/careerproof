"""One new rules report in the pre-existing, explicitly labelled synthetic PG only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
if sys.argv[1:] == ["--final"]:
    OUT = OUT / "final-rules"
    OUT.mkdir(exist_ok=False)
BACKEND = ROOT / "backend/.tmp/test-source-accepted-20261022/backend"
OLD = ROOT / "backend/.tmp/agent-display-20261021/source/backend"
CONTAINER = "careerproof-agent-display-20261021"
DB = "cp_agent_display_20261021"
TARGET_REPORT = "5960cf5d-0f6a-4564-b7ca-037e17d743e3"


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def info():
    return json.loads(subprocess.check_output(["docker", "inspect", CONTAINER]))[0]


def query(sql):
    return subprocess.check_output([
        "docker", "exec", CONTAINER, "psql", "-U", "cp_agent", "-d", DB,
        "-At", "-v", "ON_ERROR_STOP=1", "-c", sql,
    ], encoding="utf-8").strip()


def snapshots():
    return {
        table: json.loads(query(
            f"SELECT COALESCE(jsonb_object_agg(id::text,md5(to_jsonb(t)::text)), '{{}}') "
            f"FROM {table} t"
        ))
        for table in ("match_reports", "match_items", "applications", "application_events",
                      "ai_request_attempts", "ai_usage_logs", "notifications")
    }


def main():
    assert not (OUT / "rules-result.json").exists(), "Do not generate another report"
    assert not (OUT / "rules-run-claim.json").exists(), "A run already began; inspect it first"
    values = {}
    for line in (OLD / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    target = urlparse(values["DATABASE_URL"])
    assert (target.hostname, target.port, target.path) == ("127.0.0.1", 55442, "/" + DB)
    initial = info()
    assert initial["Config"]["Labels"]["careerproof.scope"] == "agent-display-20261021"
    assert initial["HostConfig"]["PortBindings"]["5432/tcp"] == [
        {"HostIp": "127.0.0.1", "HostPort": "55442"}
    ]
    assert not initial["State"]["Running"], "This run expects the stopped dedicated container"
    storage = Path(values["STORAGE_BASE_DIR"]).resolve()
    assert storage.is_dir() and storage.is_relative_to(ROOT / "backend/.tmp")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 8110))
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "PYTHONUTF8": "1",
           "DATABASE_URL": values["DATABASE_URL"], "JWT_SECRET": values["JWT_SECRET"],
           "STORAGE_BASE_DIR": str(storage), "APP_ENV": "test",
           "AI_PROVIDER": "mock", "AI_EXTERNAL_ENABLED": "false",
           "SEMANTIC_RETRIEVAL_ENABLED": "false"}
    # Persist no credentials, only the verified isolation target and immutable claim.
    save("rules-run-claim.json", {"database": DB, "dbPort": 55442, "apiPort": 8110,
                                  "source": str(BACKEND), "storage": str(storage),
                                  "externalAi": False, "initialContainerRunning": False})
    process = None
    subprocess.run(["docker", "start", CONTAINER], check=True, capture_output=True)
    try:
        for _ in range(120):
            check = subprocess.run(["docker", "exec", CONTAINER, "pg_isready", "-U", "cp_agent",
                                    "-d", DB], capture_output=True)
            if check.returncode == 0:
                break
            time.sleep(.25)
        else:
            raise RuntimeError("Dedicated PG did not become ready")
        assert query("SELECT current_database()") == DB
        before = snapshots()
        save("historical-row-hashes-before.json", before)
        with (OUT / "rules-api.raw.out").open("wb") as log:
            process = subprocess.Popen([
                sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                "--port", "8110", "--no-proxy-headers",
            ], cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Owned API exited; inspect raw log")
                try:
                    if httpx.get("http://127.0.0.1:8110/api/v1/health", trust_env=False,
                                 timeout=2).status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Owned API health timeout")
            credentials = json.loads((ROOT / (
                "backend/.tmp/complete-project-20261021/credentials.json"
            )).read_text(encoding="utf-8"))
            with httpx.Client(base_url="http://127.0.0.1:8110/api/v1", timeout=60,
                              trust_env=False) as client:
                def api(method, path, **kwargs):
                    response = client.request(method, path, **kwargs)
                    response.raise_for_status()
                    assert response.json()["code"] == 0
                    return response.json()["data"]
                api("POST", "/auth/login", json={
                    "email": credentials["studentEmail"], "password": credentials["password"],
                })
                old = api("GET", "/match-reports/" + TARGET_REPORT)
                save("saved-report-before.json", old)
                task = api("POST", "/matches", json={
                    "jobId": "33d0b1e1-1b45-4ef9-a0fc-c44da1ba1fd0",
                    "resumeVersionId": "5ecb752b-770b-4280-afb4-70ccbd1ae4b0",
                    "projectVersionIds": ["6db170c9-ea2b-4036-84d1-47260c687014"],
                    "externalAiConsent": False,
                })
                save("new-task.json", task)
                task_id = task["taskId"]
                for _ in range(300):
                    task = api("GET", "/analysis-tasks/" + task_id)
                    if task["status"] == "completed":
                        break
                    assert task["status"] not in {"failed", "cancelled"}, task
                    time.sleep(.2)
                else:
                    raise RuntimeError("Rules report timeout")
                report = api("GET", "/match-reports/" + task["reportId"])
                save("saved-report-after.json", report)
                assert report["id"] != old["id"] and report["analysisMode"] == "rules"
                assert api("GET", "/match-reports/" + TARGET_REPORT) == old
                pytest_item = next(i for i in report["items"] if i["skill"] == "pytest")
                assert sum(e["evidenceType"] == "pytest_test"
                           for e in pytest_item["evidenceList"]) > 1
                assert any("11 passed" in e["snippet"] for e in pytest_item["evidenceList"])
                if OUT.name == "final-rules":
                    assert "test_registration_persists" in pytest_item["explanation"]
                    assert "test_full_event" in pytest_item["explanation"]
                    assert "无需重复上传" in pytest_item["evidenceLevelGap"]
                    assert "pytest-output.txt" in pytest_item["evidenceLevelGap"]
                    assert "不代表运行成功" in pytest_item["evidenceLevelGap"]
                    previous_item = next(i for i in old["items"] if i["skill"] == "pytest")
                    assert (pytest_item["evidenceLevel"], pytest_item["finalScore"]) == (
                        previous_item["evidenceLevel"], previous_item["finalScore"],
                    )
        after = snapshots()
        save("historical-row-hashes-after.json", after)
        for table, rows in before.items():
            assert all(after[table].get(key) == digest for key, digest in rows.items()), table
            if table not in {"match_reports", "match_items"}:
                assert rows == after[table], table
        save("rules-result.json", {
            "baseCommit": "7a19e6b872c8df1a9b74c6e912f0488e43fbe203",
            "acceptedSource": str(BACKEND), "reportId": report["id"],
            "taskId": task_id, "database": DB, "dbPort": 55442,
            "sourceSet": "accepted-source.json", "externalRequests": 0,
            "historicalRowsUnchanged": True, "oldReportReadbackUnchanged": True,
            "newReportCount": len(after["match_reports"]) - len(before["match_reports"]),
            "aiTablesUnchanged": True, "normalSiteTouched": False,
            "browserVerified": False,
        })
        print(json.dumps({"reportId": report["id"], "analysisMode": report["analysisMode"]}))
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=15)
        subprocess.run(["docker", "stop", CONTAINER], check=True, capture_output=True)
        save("isolation-final.json", {"ownedApiStopped": process is None or process.poll() is not None,
                                      "containerRunning": info()["State"]["Running"],
                                      "initialStoppedStateRestored": True})


if __name__ == "__main__":
    main()
