"""Owned rules-only HTTP reproduction; no normal DB, external AI or old writes."""
import hashlib
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
from uuid import UUID
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
STAGE = ROOT / "backend/.tmp/rule-narrative-20261021/source-r2"
BACKEND = STAGE / "backend"
OLD = ROOT / "backend/.tmp/agent-display-20261021/source"
DB = "cp_agent_display_20261021"
CONTAINER = "careerproof-agent-display-20261021"
sha = lambda body: hashlib.sha256(body).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sql(query):
    return subprocess.check_output([
        "docker", "exec", CONTAINER, "psql", "-U", "cp_agent", "-d", DB,
        "-At", "-v", "ON_ERROR_STOP=1", "-c", query,
    ], encoding="utf-8").strip()


def main():
    assert not (OUT / "result.json").exists(), "Saved run exists; do not repeat writes"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    read_existing = sys.argv[1:] == ["--read-existing"]
    if not read_existing:
        assert not STAGE.exists(), "Do not overwrite a previous validation source"
        archive = subprocess.check_output(["git", "archive", "--format=zip", head, "backend"], cwd=ROOT)
        STAGE.mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            package.extractall(STAGE)
        (BACKEND / ".tmp").mkdir()
    else:
        assert (BACKEND / ".env").exists(), "Only resume the already prepared source"
    (BACKEND / "app/tests/test_real_matching.py").write_bytes(
        (ROOT / "backend/app/tests/test_real_matching.py").read_bytes()
    )
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "AI_EXTERNAL_ENABLED": "false",
           "AI_PROVIDER": "mock", "CAREERPROOF_TEST_DATABASE_URL": "", "PYTHONIOENCODING": "utf-8"}
    command = [sys.executable, "-m", "pytest",
               "app/tests/test_real_matching.py::test_rules_explain_selected_source_without_requesting_duplicate_upload",
               "-q", "--no-header", "--tb=short", "-p", "no:cacheprovider",
               "-o", "faulthandler_timeout=45", "--basetemp=.tmp/narrative-red"]
    if not read_existing:
        with (OUT / "red-baseline.raw.out").open("wb") as log:
            red = subprocess.run(command, cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        assert red.returncode == 1 and "reserve" in (OUT / "red-baseline.raw.out").read_text(encoding="utf-8")

    # Copy only our source. The paused ai_process projection is preserved in the
    # working tree and deliberately absent from this owned execution source.
    paused = '''            ai_process={
                key: value if isinstance(value, str) else None
                for key in ("planningSkippedReason", "skippedReason", "fallbackReason", "failureStage")
                for value in [(report.analysis_metadata or {}).get(key)]
            },
'''
    changed = ["app/services/analysis.py", "app/tools/evidence_levels.py", "app/tools/rule_narrative.py"]
    for relative in changed:
        text = (ROOT / "backend" / relative).read_text(encoding="utf-8")
        if relative == "app/services/analysis.py":
            assert text.count(paused) == 1
            text = text.replace(paused, "")
        (BACKEND / relative).write_text(text, encoding="utf-8", newline="\n")
    with (OUT / "stage-static.raw.out").open("wb") as log:
        checked = subprocess.run([sys.executable, "-m", "ruff", "check", *changed],
                                 cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
    assert checked.returncode == 0
    values = {}
    for line in (OLD / "backend/.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    target = urlparse(values["DATABASE_URL"])
    assert (target.hostname, target.port, target.path) == ("127.0.0.1", 55442, "/" + DB)
    info = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER]))[0]
    assert info["State"]["Running"] and info["Config"]["Labels"]["careerproof.scope"] == "agent-display-20261021"
    assert info["NetworkSettings"]["Ports"]["5432/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "55442"}]
    assert sql("SELECT current_database()") == DB
    storage = Path(values.get("STORAGE_BASE_DIR", "storage"))
    if not storage.is_absolute():
        storage = (OLD / "backend" / storage).resolve()
    assert storage.is_dir() and storage.is_relative_to(ROOT / "backend/.tmp")
    env.update(DATABASE_URL=values["DATABASE_URL"], JWT_SECRET=values["JWT_SECRET"],
               STORAGE_BASE_DIR=str(storage), APP_ENV="test", SEMANTIC_RETRIEVAL_ENABLED="false")
    # Local-only restart command can reuse this minimal configuration; no API key copied.
    local_keys = ("DATABASE_URL", "JWT_SECRET", "STORAGE_BASE_DIR", "APP_ENV",
                  "AI_EXTERNAL_ENABLED", "AI_PROVIDER", "SEMANTIC_RETRIEVAL_ENABLED")
    (BACKEND / ".env").write_text("\n".join(f'{key}="{env[key]}"' for key in local_keys) + "\n", encoding="utf-8")
    tables = ("match_reports", "match_items", "applications", "ai_request_attempts", "ai_usage_logs", "notifications")
    before = {name: json.loads(sql(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]') FROM {name} t")) for name in tables}
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (OUT / ("api-readback.raw.out" if read_existing else "api-process.raw.out")).open("wb") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                    "--port", str(port), "--no-proxy-headers"], cwd=BACKEND, env=env,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            for _ in range(120):
                assert process.poll() is None
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", trust_env=False, timeout=2).status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Owned API failed health")
            credentials = json.loads((ROOT / "backend/.tmp/complete-project-20261021/credentials.json").read_text())
            with httpx.Client(base_url=f"http://127.0.0.1:{port}/api/v1", trust_env=False, timeout=60) as client:
                def api(method, path, **kwargs):
                    response = client.request(method, path, **kwargs)
                    response.raise_for_status()
                    assert response.json()["code"] == 0
                    return response.json()["data"]
                api("POST", "/auth/login", json={"email": credentials["studentEmail"], "password": credentials["password"]})
                old = api("GET", "/match-reports/516cc695-5044-481f-ab9b-5ffa5e59f1a5")
                task = None if read_existing else api("POST", "/matches", json={
                    "jobId": "33d0b1e1-1b45-4ef9-a0fc-c44da1ba1fd0",
                    "resumeVersionId": "5ecb752b-770b-4280-afb4-70ccbd1ae4b0",
                    "projectVersionIds": ["6db170c9-ea2b-4036-84d1-47260c687014"],
                    "externalAiConsent": False,
                })
                for _ in range(0 if read_existing else 300):
                    task = api("GET", "/analysis-tasks/" + task["taskId"] if "taskId" in task else "/analysis-tasks/" + task["id"])
                    if task["status"] == "completed":
                        break
                    assert task["status"] not in {"failed", "cancelled"}, task
                    time.sleep(.2)
                if task and task.get("status") != "completed":
                    raise RuntimeError("Rules task timed out")
                report = api("GET", "/match-reports/" + (
                    "93bc1b91-177b-4755-a9f6-55ca2dc96b4c" if read_existing else task["reportId"]
                ))
                assert report["id"] != old["id"] and report["analysisMode"] == "rules"
                assert api("GET", "/match-reports/" + old["id"]) == old
                save("report-before-v1-historical.json", old)
                save("report-after.json", report)
                # The earlier historical report is V1, so it cannot be used to
                # assert exact V2 references. Re-run the unchanged selection and
                # context production modules on the same frozen V2 input instead.
                sys.path.insert(0, str(BACKEND))
                from app.tools.code_analyzer import ProjectFileSnapshot
                from app.tools.evidence_context import enrich_evidence
                from app.tools.evidence_levels import classify_evidence
                from app.tools.matcher import RequirementInput, match_candidate
                from app.tools.resume_parser import parse_resume
                v2 = json.loads((OUT.parent / "growth-runtime/v2-manifest.json").read_text(encoding="utf-8"))
                assert sha(Path(v2["zip"]).read_bytes()) == v2["sha256"]
                with zipfile.ZipFile(v2["zip"]) as package:
                    files = [ProjectFileSnapshot("6db170c9-ea2b-4036-84d1-47260c687014/" + name,
                                                 package.read(name).decode("utf-8")) for name in package.namelist()]
                requirements = [RequirementInput(UUID(item["requirementId"]), item["requirementTitle"],
                                                  item["skill"], item["weight"]) for item in report["items"]]
                material_manifest = json.loads((OUT.parent / "material-manifest.json").read_text(encoding="utf-8"))
                claims = parse_resume(Path(material_manifest["resume"]).read_text(encoding="utf-8"))
                baseline = enrich_evidence(match_candidate(requirements, claims, files), files)
                changes = []
                for previous, current in zip(baseline.items, report["items"], strict=True):
                    expected = [(e.file_path, e.line_start, e.line_end, e.snippet, e.content_hash) for e in previous.evidence_list]
                    actual = [(e["filePath"], e["lineStart"], e["lineEnd"], e["snippet"], e["contentHash"]) for e in current["evidenceList"]]
                    assert str(previous.requirement_id) == current["requirementId"]
                    assert expected == actual, current["skill"]
                    classification = classify_evidence({"skill": previous.skill, "evidenceList": [asdict(e) for e in previous.evidence_list],
                                                        "ruleClassificationVersion": "practice-evidence-v5-redis-operation"}, previous.verdict)
                    assert (classification["evidence_level"], previous.verdict, previous.final_score, previous.formula_version) == (
                        current["evidenceLevel"], current["verdict"], current["finalScore"], current["formulaVersion"])
                    changes.append({"skill": current["skill"], "referencesUnchanged": True,
                                    "level": current["evidenceLevel"], "beforeExplanation": previous.explanation,
                                    "afterExplanation": current["explanation"], "beforeGap": classification["evidence_level_gap"],
                                    "afterGap": current["evidenceLevelGap"]})
                save("comparison.json", changes)
            after = {name: json.loads(sql(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]') FROM {name} t")) for name in tables}
            for name, rows in before.items():
                ids = {row["id"] for row in rows}
                assert [row for row in after[name] if row["id"] in ids] == rows, name
                if name not in {"match_reports", "match_items"}:
                    assert after[name] == rows, name
            manifest = {str(path.relative_to(STAGE)).replace("\\", "/"): sha(path.read_bytes())
                        for path in BACKEND.rglob("*.py") if ".tmp" not in path.relative_to(BACKEND).parts}
            save("source-hashes.json", manifest)
            save("result.json", {"baseCommit": head, "reportId": report["id"], "taskId": report["taskId"],
                                  "baseline": "unchanged production selection/context modules, same V2 frozen input; not a saved V1 report",
                                  "source": str(BACKEND), "database": DB, "dbPort": 55442, "storage": str(storage),
                                  "apiPort": port, "externalAi": False, "historicalRowsUnchanged": True,
                                  "oldReportsUnchanged": True, "referencesAndRatingsUnchanged": True,
                                  "pausedDisplayIncluded": False, "normalSiteTouched": False,
                                  "originalPreviewRestarted": False, "ownedApiStopped": True})
            print(json.dumps({"reportId": report["id"], "referencesAndRatingsUnchanged": True}))
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
