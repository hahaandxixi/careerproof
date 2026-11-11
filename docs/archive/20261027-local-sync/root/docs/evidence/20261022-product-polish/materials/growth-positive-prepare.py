"""Prepare one editable V1-baseline task through the dedicated synthetic API.

No upload, material attachment or analysis. A completed existing task is a stop.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx

ROOT = Path(r"D:/jbcode/web ai/jianli")
WORK = ROOT / "backend/.tmp/product-polish-20261022"
OUT = ROOT / "docs/evidence/20261022-product-polish/materials"
RECORD = OUT / "growth-positive-prepare.json"
if RECORD.exists():
    raise SystemExit("Positive preparation already recorded; refuse another creation")
spec = importlib.util.spec_from_file_location("guarded_materials_flow", WORK / "materials-api-flow.py")
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)
# Importing this module validates exact source, DB55445, dedicated storage and AI=false.
record = {
    "api": "http://127.0.0.1:8113", "externalAI": False,
    "database": {"host": "127.0.0.1", "port": 55445, "name": "cp_product_polish_20261022"},
    "source": str(flow.SOURCE), "storage": str(flow.settings.storage_base_dir),
    "baseReportId": "4cd00c84-855f-4d26-8a3b-6fe31a076535",
    "uploadedVersionId": "53366c20-1973-48a4-8b18-c27ca4ceaa7e", "calls": [],
    "uploads": 0, "materialSaves": 0, "analyses": 0,
}


def persist():
    RECORD.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run():
    credentials = json.loads((ROOT / "backend/.tmp/complete-project-20261021/credentials.json").read_text(encoding="utf-8"))
    with httpx.Client(base_url="http://127.0.0.1:8113/api/v1", timeout=45, trust_env=False) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            record["calls"].append({"method": method, "path": path, "status": response.status_code})
            response.raise_for_status()
            result = response.json()
            assert result.get("code") == 0, "Non-success API envelope"
            return result["data"]

        identity = call("POST", "/auth/login", json={"email": credentials["studentEmail"], "password": credentials["password"]})
        assert identity["user"]["role"] == "student"
        report = call("GET", f"/match-reports/{record['baseReportId']}")
        record["baseReportHashBefore"] = flow.digest(report)
        requirement = [item for item in report["items"] if item["skill"].lower() == "pytest"]
        assert len(requirement) == 1, "Expected one pytest requirement; no task created"
        requirement = requirement[0]
        record["requirementId"] = requirement["requirementId"]
        record["requirementTitle"] = requirement["requirementTitle"]
        projects = call("GET", "/projects")
        target = [(project, version) for project in projects for version in project["versions"] if version["id"] == record["uploadedVersionId"]]
        assert len(target) == 1 and target[0][1]["status"] == "completed", "V4 must be owned and completed"
        project, version = target[0]
        baseline_versions = [material["id"] for material in report["materials"] if material["kind"] == "project"]
        assert any(old["id"] in baseline_versions for old in project["versions"]), "Baseline must use same owned project"
        record["baseMaterials"] = report["materials"]
        record["targetVersion"] = {key: version.get(key) for key in ["id", "versionNumber", "contentHash", "status", "originalFilename"]}
        record["projectId"] = project["id"]
        existing = call("GET", f"/match-reports/{report['id']}/growth-tasks/{requirement['requirementId']}")
        if existing is not None:
            record["reused"] = True
            growth = existing
        else:
            record["reused"] = False
            payload = {
                "requirementId": requirement["requirementId"], "gapKind": "execution",
                "deliverable": "核对新版行为测试及上传的运行记录与固定源码版本之间的对应关系",
                "steps": ["对照旧版固定报告中已保存的测试引用", "明确选择现有新版材料后，核对运行记录、测试与实现的对应范围"],
                "acceptanceChecks": ["引用能定位到保存版本的文件与行号", "上传的运行输出不被当作平台独立执行或本人贡献认证", "不承诺等级提升"],
            }
            record["createPayload"] = payload
            # Persist before the sole possible task creation to avoid an ambiguous retry.
            persist()
            growth = call("POST", f"/match-reports/{report['id']}/growth-tasks", json=payload)
        record["growth"] = growth
        assert growth["status"] in {"planned", "materials_selected"} and not growth.get("analysisTaskId"), "Existing task is not editable; stopped without duplicates"
        old_after = call("GET", f"/match-reports/{report['id']}")
        record["baseReportHashAfter"] = flow.digest(old_after)
        record["baseReportUnchanged"] = record["baseReportHashBefore"] == record["baseReportHashAfter"]
        assert record["baseReportUnchanged"]
        record["returnPath"] = f"/growth/{growth['id']}?uploadedKind=project&uploadedVersion={record['uploadedVersionId']}"
        record["browserURL"] = "http://127.0.0.1:3135" + record["returnPath"]
        record["passed"] = True
        persist()
        print(json.dumps({"passed": True, "growthId": growth["id"], "status": growth["status"], "reused": record["reused"], "returnPath": record["returnPath"], "baseReportUnchanged": True, "materialSaves": 0, "analyses": 0}))


if __name__ == "__main__":
    try:
        run()
    except BaseException as error:
        record["passed"] = False
        record["failure"] = {"type": type(error).__name__, "message": str(error)}
        persist()
        raise
