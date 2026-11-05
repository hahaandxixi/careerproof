"""Bounded real API verification, dedicated synthetic clone only. No external AI."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

ROOT = Path(r"D:/jbcode/web ai/jianli")
WORK = ROOT / "backend/.tmp/product-polish-20261022"
SOURCE = WORK / "source/backend"
OUT = ROOT / "docs/evidence/20261022-product-polish/materials"
os.chdir(SOURCE)
sys.path.insert(0, str(SOURCE))
from app.core.config import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import httpx

url = urlparse(settings.database_url)
assert (url.hostname, url.port, url.path) == ("127.0.0.1", 55445, "/cp_product_polish_20261022"), "Wrong database: stopped before HTTP"
assert settings.storage_base_dir.resolve() == (WORK / "storage").resolve(), "Wrong storage: stopped before HTTP"
assert settings.ai_external_enabled is False, "External AI must be disabled"
assert Path(sys.modules["app.core.config"].__file__).resolve().is_relative_to(SOURCE.resolve())

result = {"sourceCommit": "01232d27e8768121592b6c05300e0b5ba5170a55", "source": str(SOURCE), "api": "http://127.0.0.1:8113", "database": {"host": url.hostname, "port": url.port, "name": url.path.lstrip("/")}, "storage": str(settings.storage_base_dir), "externalAI": settings.ai_external_enabled, "calls": []}

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

def persist():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "api-flow.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

async def database_facts():
    engine = create_async_engine(settings.database_url, connect_args={"timeout": 5})
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            counts = {name: (await conn.execute(text(f"SELECT count(*) FROM {name}"))).scalar_one() for name in ["ai_request_attempts", "ai_usage_logs"]}
            snapshots = (await conn.execute(text("SELECT id, report_snapshot FROM applications ORDER BY id"))).all()
            return {**counts, "applicationSnapshotsHash": digest([tuple(row) for row in snapshots]), "applicationCount": len(snapshots)}
    finally:
        await engine.dispose()


def run():
    credentials = json.loads((ROOT / "backend/.tmp/complete-project-20261021/credentials.json").read_text(encoding="utf-8"))
    image = WORK / "fixtures/Resume.PNG"
    result["image"] = {"filename": image.name, "bytes": image.stat().st_size, "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
    print("Isolated settings verified; reading initial facts", flush=True)
    result["databaseBefore"] = asyncio.run(database_facts())
    print("Initial facts read; starting local API flow", flush=True)
    with httpx.Client(base_url="http://127.0.0.1:8113/api/v1", timeout=100, trust_env=False) as client:
        def call(method, path, **kwargs):
            print(f"{method} {path}", flush=True)
            response = client.request(method, path, **kwargs)
            result["calls"].append({"method": method, "path": path, "status": response.status_code})
            if response.status_code >= 400:
                raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:600]}")
            envelope = response.json()
            assert envelope.get("code") == 0, f"API rejected {path}: {envelope.get('code')}"
            return envelope["data"]

        identity = call("POST", "/auth/login", json={"email": credentials["studentEmail"], "password": credentials["password"]})
        assert identity["user"]["role"] == "student"
        result["userId"] = identity["user"]["id"]
        base_id = "fda4ec24-3534-4a4e-80aa-2d5959b0c87e"
        base = call("GET", f"/match-reports/{base_id}")
        assert len(base["items"]) >= 5, "Need the full five-requirement project report"
        projects = [value["id"] for value in base["materials"] if value["kind"] == "project"]
        resumes = [value["id"] for value in base["materials"] if value["kind"] == "resume"]
        assert projects and len(resumes) == 1
        files = [file for version in projects for file in call("GET", f"/project-versions/{version}/files")]
        assert any("test" in file["relativePath"].lower() for file in files), "No behavioral test materials"
        assert any(file["relativePath"].lower().endswith(".py") for file in files), "No Python implementation"
        result["baseReport"] = {"id": base_id, "sha256": digest(base), "jobId": base["jobId"], "materials": base["materials"], "requirementCount": len(base["items"]), "projectFileCount": len(files), "projectFiles": [value["relativePath"] for value in files]}
        with image.open("rb") as handle:
            uploaded = call("POST", "/resumes", data={"title": "产品验收图片简历 · 20261022"}, files={"file": (image.name, handle, "image/png")})
        result["imageUpload"] = uploaded
        persist()

        def wait_task(task_id):
            deadline = time.monotonic() + 100
            states = []
            while time.monotonic() < deadline:
                task = call("GET", f"/analysis-tasks/{task_id}")
                state = {"status": task["status"], "progress": task["progress"], "currentStep": task.get("currentStep")}
                if not states or states[-1] != state: states.append(state)
                if task["status"] in {"completed", "failed", "cancelled"}:
                    return task, states
                time.sleep(0.7)
            raise TimeoutError(f"task did not finish: {task_id}")

        image_task, image_states = wait_task(uploaded["taskId"])
        result["imageTask"] = {"id": image_task["id"], "status": image_task["status"], "states": image_states, "errorMessage": image_task.get("errorMessage")}
        assert image_task["status"] == "completed", image_task.get("errorMessage")
        preview = call("GET", f"/resume-versions/{uploaded['versionId']}/preview")
        extracted = "\n".join(section["content"] for section in preview["sections"])
        result["imagePreview"] = {"id": preview["id"], "status": preview["status"], "sectionCount": len(preview["sections"]), "characters": len(extracted), "text": extracted}
        assert preview["status"] == "completed" and extracted.strip(), "PNG OCR produced no text"
        persist()

        payload = {"jobId": base["jobId"], "resumeVersionId": resumes[0], "projectVersionIds": projects, "externalAiConsent": False, "usePreviousReport": False}
        result["rulesRequest"] = payload
        accepted = call("POST", "/matches", json=payload)
        result["rulesAccepted"] = accepted
        persist()
        task, states = wait_task(accepted["taskId"])
        result["rulesTask"] = {"id": task["id"], "status": task["status"], "states": states, "errorMessage": task.get("errorMessage"), "steps": task.get("steps"), "totalCostRmb": task.get("totalCostRmb")}
        assert task["status"] == "completed", task.get("errorMessage")
        fresh = call("GET", f"/match-reports/{task['reportId']}")
        result["freshReport"] = fresh
        assert fresh["id"] != base_id, "Must preserve old report and create a new one"
        assert {(value["kind"], value["id"], value["contentHash"]) for value in fresh["materials"]} == {(value["kind"], value["id"], value["contentHash"]) for value in base["materials"]}
        assert fresh["analysisMode"] == "rules" and not fresh.get("aiToolCalls")
        assert fresh.get("aiProvider") in {None, "rules"} and not fresh.get("aiUsage")
        old = call("GET", f"/match-reports/{base_id}")
        result["oldReportUnchanged"] = digest(old) == result["baseReport"]["sha256"]
        assert result["oldReportUnchanged"]
        result["databaseAfter"] = asyncio.run(database_facts())
        assert result["databaseBefore"] == result["databaseAfter"], "AI counts or immutable application snapshots changed"
        result["passed"] = True
        result["limitations"] = ["执行端在专属合成环境验证，不计首次独立用户验收", "PNG真实API和OCR已验证；浏览器原生文件交互由父任务另验", "仅规则报告，无真实模型质量结论；不代替人工语义复核", "本轮未创建补证任务、未投递、未进入企业查看/回复"]
    persist()
    print(json.dumps({"passed": result["passed"], "imageVersionId": uploaded["versionId"], "imageTaskId": uploaded["taskId"], "ocrCharacters": len(extracted), "rulesReportId": fresh["id"], "rulesTaskId": task["id"], "requirements": len(fresh["items"]), "oldReportUnchanged": result["oldReportUnchanged"], "databaseFactsUnchanged": result["databaseBefore"] == result["databaseAfter"]}, ensure_ascii=False))

if __name__ == "__main__":
    try:
        run()
    except BaseException as error:
        result["passed"] = False
        result["failure"] = {"type": type(error).__name__, "message": str(error)}
        persist()
        raise
