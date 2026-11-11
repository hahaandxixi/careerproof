"""Create only one synthetic growth task and one project version; never attach/analyze."""
from __future__ import annotations
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import uuid
import httpx

ROOT = Path(r"D:/jbcode/web ai/jianli")
WORK = ROOT / "backend/.tmp/product-polish-20261022"
OUT = ROOT / "docs/evidence/20261022-product-polish/materials"
RECORD = OUT / "growth-prepare.json"
if RECORD.exists():
    raise SystemExit("A growth preparation record already exists; refuse to create duplicates")
# Reuse only the verified isolation guard and read-only facts function; importing
# this module cannot call its run() entrypoint or make HTTP requests.
spec = importlib.util.spec_from_file_location("isolated_materials_flow", WORK / "materials-api-flow.py")
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)
assert flow.settings.ai_external_enabled is False

zip_path = ROOT / "output/demo/CareerProof-campus-signup-v2-runtime.zip"
zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
assert zip_sha == "58b3ced4e093d346b7f466d5cc36243639357590d8ab692445d6de9202fb1518", "Immutable package changed: stopped before HTTP"
record = {"api": "http://127.0.0.1:8113", "sourceCommit": "01232d27e8768121592b6c05300e0b5ba5170a55", "database": {"port": 55445, "name": "cp_product_polish_20261022"}, "storage": str(flow.settings.storage_base_dir), "externalAI": False, "calls": [], "baseReportId": "59ac4fa1-4792-4c14-b268-51119b129076", "package": {"path": str(zip_path), "sha256": zip_sha, "bytes": zip_path.stat().st_size}, "requestId": str(uuid.uuid4()), "limitation": "Identical V2 bytes create a version-selection fixture, not new implementation or evidence of improvement"}

def persist():
    RECORD.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

def run():
    record["databaseBefore"] = asyncio.run(flow.database_facts())
    credentials = json.loads((ROOT / "backend/.tmp/complete-project-20261021/credentials.json").read_text(encoding="utf-8"))
    with httpx.Client(base_url="http://127.0.0.1:8113/api/v1", timeout=100, trust_env=False) as client:
        def call(method, path, **kwargs):
            print(f"{method} {path}", flush=True)
            response = client.request(method, path, **kwargs)
            record["calls"].append({"method": method, "path": path, "status": response.status_code})
            response.raise_for_status()
            result = response.json()
            assert result.get("code") == 0, result.get("code")
            return result["data"]
        identity = call("POST", "/auth/login", json={"email": credentials["studentEmail"], "password": credentials["password"]})
        assert identity["user"]["role"] == "student"
        record["userId"] = identity["user"]["id"]
        report = call("GET", f"/match-reports/{record['baseReportId']}")
        record["baseReportHash"] = flow.digest(report)
        sql = [item for item in report["items"] if item["skill"] == "SQL"]
        assert len(sql) == 1
        record["requirementId"] = sql[0]["requirementId"]
        old_versions = [item["id"] for item in report["materials"] if item["kind"] == "project"]
        projects = call("GET", "/projects")
        targets = [project for project in projects if any(version["id"] in old_versions for version in project["versions"])]
        assert len(targets) == 1, "Expected one full-project target"
        project = targets[0]
        record["projectId"] = project["id"]
        record["projectName"] = project["name"]
        record["previousVersions"] = [{key: version.get(key) for key in ["id", "versionNumber", "status", "originalFilename"]} for version in project["versions"]]
        record["expectedNextVersionNumber"] = max(version["versionNumber"] for version in project["versions"]) + 1
        record["growthPayload"] = {
            "requirementId": sql[0]["requirementId"], "gapKind": "review",
            "deliverable": "核对现有测试与运行记录对应源码版本（不承诺等级提升）",
            "steps": ["核对已上传的测试与运行记录引用", "明确选择刚上传的项目版本，再确认保存材料选择"],
            "acceptanceChecks": ["文件、行号与源码版本可对应", "未把重复上传视为实现变化或等级提升"]}
        persist()
        growth = call("POST", f"/match-reports/{record['baseReportId']}/growth-tasks", json=record["growthPayload"])
        record["growth"] = growth
        assert growth["status"] == "planned" and not growth["materials"] and not growth.get("analysisTaskId")
        persist()
        with zip_path.open("rb") as handle:
            uploaded = call("POST", f"/projects/{project['id']}/versions", data={"requestId": record["requestId"], "materialRole": "portfolio"}, files={"file": (zip_path.name, handle, "application/zip")})
        record["upload"] = uploaded
        persist()
        deadline = time.monotonic() + 100
        states = []
        while time.monotonic() < deadline:
            task = call("GET", f"/analysis-tasks/{uploaded['taskId']}")
            state = {"status": task["status"], "progress": task["progress"], "currentStep": task.get("currentStep")}
            if not states or states[-1] != state: states.append(state)
            if task["status"] in {"completed", "failed", "cancelled"}: break
            time.sleep(0.7)
        else: raise TimeoutError("project scan did not finish")
        record["scanTask"] = {"id": task["id"], "status": task["status"], "errorMessage": task.get("errorMessage"), "states": states}
        assert task["status"] == "completed", task.get("errorMessage")
        versions = call("GET", f"/projects/{project['id']}/versions")
        version = next(value for value in versions if value["id"] == uploaded["versionId"])
        record["newVersion"] = version
        assert version["versionNumber"] == record["expectedNextVersionNumber"]
        growth_after = call("GET", f"/growth-tasks/{growth['id']}")
        record["growthAfterUpload"] = growth_after
        assert growth_after["status"] == "planned" and growth_after["materials"] == [] and not growth_after.get("analysisTaskId")
        assert flow.digest(growth_after) == flow.digest(growth), "Upload must not mutate selected task"
        old = call("GET", f"/match-reports/{record['baseReportId']}")
        record["baseReportUnchanged"] = flow.digest(old) == record["baseReportHash"]
        assert record["baseReportUnchanged"]
        record["databaseAfter"] = asyncio.run(flow.database_facts())
        assert record["databaseBefore"] == record["databaseAfter"]
        record["returnPath"] = f"/growth/{growth['id']}?uploadedKind=project&uploadedVersion={uploaded['versionId']}"
        record["browserReturnURL"] = f"http://127.0.0.1:3135{record['returnPath']}"
        record["passed"] = True
        persist()
        print(json.dumps({"passed": True,"growthId": growth["id"],"projectId": project["id"],"newVersionId": uploaded["versionId"],"versionNumber": version["versionNumber"],"scanTaskId": task["id"],"returnPath": record["returnPath"],"selectionSaved": False,"analysisStarted": False},ensure_ascii=False))

if __name__ == "__main__":
    try: run()
    except BaseException as error:
        record["passed"] = False
        record["failure"] = {"type": type(error).__name__, "message": str(error)}
        persist()
        raise
