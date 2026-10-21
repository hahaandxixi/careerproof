"""Exercise the original demo over loopback HTTP, never through CareerProof."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "demo/complete-projects/campus-signup-v1"
RUN = ROOT / "backend/.tmp/complete-project-20261021"
EVIDENCE = Path(__file__).parent
DATABASE = RUN / "business-run2.sqlite3"
PORT = 0
assert not DATABASE.exists(), "Never silently reuse a business run"
RUN.mkdir(parents=True, exist_ok=True)
events = []
process = None
log = (EVIDENCE / "business-server.raw.out").open("wb")


def start():
    global PORT
    with socket.socket() as check:
        check.bind(("127.0.0.1", 0))
        PORT = check.getsockname()[1]
    env = dict(os.environ, PYTHONPATH=str(PROJECT), PYTHONIOENCODING="utf-8")
    child = subprocess.Popen(
        [sys.executable, "-m", "campus_signup", "--database", str(DATABASE), "--port", str(PORT)],
        cwd=PROJECT, env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(100):
        assert child.poll() is None, "Demo server exited"
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/events", trust_env=False).status_code == 200:
                return child
        except httpx.ConnectError:
            pass
        time.sleep(.1)
    child.terminate()
    child.wait(timeout=10)
    raise RuntimeError("Demo server did not start")


def stop(child):
    child.terminate()
    child.wait(timeout=10)


def request(client, method, path, expected, body=None):
    response = client.request(method, path, json=body) if body is not None else client.request(method, path)
    result = response.json()
    events.append({"method": method, "path": path, "input": body,
                   "status": response.status_code, "body": result})
    assert response.status_code == expected, events[-1]
    return result


try:
    process = start()
    with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", trust_env=False) as client:
        event = request(client, "POST", "/events", 201, {"title": "Robotics workshop", "capacity": 1})
        payload = {"event_id": event["id"], "student_code": "DEMO001"}
        registration = request(client, "POST", "/registrations", 201, payload)
        request(client, "POST", "/registrations", 409, payload)
        request(client, "POST", "/registrations", 409, {**payload, "student_code": "DEMO002"})
        request(client, "POST", "/registrations", 404, {**payload, "event_id": 999})
        request(client, "POST", "/registrations", 422, {**payload, "student_code": "X"})
        request(client, "POST", f"/registrations/{registration['id']}/cancel", 200)
        request(client, "POST", f"/registrations/{registration['id']}/cancel", 409)
        request(client, "POST", "/registrations", 201, {**payload, "student_code": "DEMO002"})
        failure_event = request(client, "POST", "/events", 201, {"title": "Failure workshop", "capacity": 1})
        with sqlite3.connect(DATABASE) as database:
            database.execute("""CREATE TRIGGER fail_audit BEFORE INSERT ON audit_log
                BEGIN SELECT RAISE(ABORT, 'audit write rejected'); END""")
        request(client, "POST", "/registrations", 503,
                {"event_id": failure_event["id"], "student_code": "DEMO003"})
        with sqlite3.connect(DATABASE) as database:
            assert database.execute("SELECT remaining FROM events WHERE id = ?", (failure_event["id"],)).fetchone()[0] == 1
            assert database.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?", (failure_event["id"],)).fetchone()[0] == 0
            database.execute("DROP TRIGGER fail_audit")
        before = {name: request(client, "GET", "/" + name, 200) for name in ["events", "registrations"]}
    stop(process)
    process = None
    file_hash_before = hashlib.sha256(DATABASE.read_bytes()).hexdigest()
    process = start()
    with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", trust_env=False) as client:
        after = {name: request(client, "GET", "/" + name, 200) for name in ["events", "registrations"]}
    assert before == after
    file_hash_after = hashlib.sha256(DATABASE.read_bytes()).hexdigest()
    assert file_hash_before == file_hash_after
    result = {"business": "Create event, bounded registration, cancellation and durable audit",
              "syntheticOnly": True, "requests": events, "restartRecordsEqual": True,
              "databaseSha256BeforeRestart": file_hash_before,
              "databaseSha256AfterRestart": file_hash_after,
              "realExternalModelRequests": 0, "mockBusinessLogic": False,
              "dependenciesReusedNotCleanInstalled": True,
              "versions": {name: importlib.metadata.version(name)
                           for name in ["fastapi", "pydantic", "uvicorn", "httpx", "pytest"]}}
    (EVIDENCE / "business-results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PASS: live HTTP success, 404/409/422/503, atomic rollback, cancellation and restart persistence")
finally:
    if process is not None:
        stop(process)
    log.close()
