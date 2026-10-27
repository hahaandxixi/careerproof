"""Opt-in preparation for the owned home-discovery preview; real rules/API workflow.

Run from backend: python -m evals.seed_market_applications --runtime .tmp/private-runtime.json
Does not relax seed_e2e's separate isolation contract, insert reports, or call AI.
Passwords and resumable progress stay only in the ignored sibling state file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from evals.seed_e2e import _login, _payload, normalized_snapshot_hash
from evals.seed_role_materials import seed
from evals.verify_deepseek_tool_report import wait

ROOT = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:8140/api/v1"
CONTAINER = "careerproof-home-discovery-20261027"
RECIPES = (
    ("implemented", "event-api", "Python 实现材料学生（合成）"),
    ("statement", "event-api", "Python 仅声明学生（合成）"),
    ("frontend", "event-console", "React 实现材料学生（合成）"),
)


def guard_runtime(runtime, source_root=ROOT):
    parsed = urlsplit(runtime["env"]["DATABASE_URL"])
    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path) != (
        "postgresql+asyncpg", "127.0.0.1", 55447, "/cp_home_discovery_test_20261027",
    ) or parsed.query or parsed.fragment or runtime.get("container") != CONTAINER:
        raise ValueError("Not the explicitly owned synthetic preview database")
    storage = Path(runtime["env"]["STORAGE_BASE_DIR"]).resolve()
    if storage != (source_root / "backend/.tmp/storage").resolve():
        raise ValueError("Preview storage does not match this checkout")


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".new")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run(runtime_path):
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    guard_runtime(runtime)
    container = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER]))[0]
    if (container["Config"]["Labels"].get("careerproof.owner") != "home-discovery-20261027"
        or container["HostConfig"]["PortBindings"]["5432/tcp"] != [
            {"HostIp": "127.0.0.1", "HostPort": "55447"}
        ] or not container["State"]["Running"]):
        raise ValueError("Container ownership/binding not confirmed")
    # Bind this process to explicit settings before importing services/settings.
    os.environ.update(runtime["env"])
    os.environ.update(AI_EXTERNAL_ENABLED="false", AI_PROVIDER="mock", APP_ENV="test")
    state_path = runtime_path.with_name("market-applications.private.json")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {"accounts": {}, "slots": {}}
        for key, _, _ in RECIPES:
            state["accounts"][key] = {
                "email": f"market-{key}-20261027@example.com",
                "password": secrets.token_urlsafe(22),
            }
        save(state_path, state)  # Save before registration; safe to resume after interruption.
    owner = asyncio.run(verify_target_and_import(runtime))
    catalog = json.loads((ROOT / "demo/market-scenarios.json").read_text(encoding="utf-8"))
    specs = {item["key"]: item for item in catalog["scenarios"]}
    assets = ROOT / "jianli/public/demo-assets/scenarios"
    records = []
    with httpx.Client(base_url=API, timeout=60, trust_env=False) as enterprise:
        user = _sync_login(enterprise, runtime["enterpriseEmail"], runtime["password"])
        if user["id"] != owner or user["role"] != "enterprise":
            raise ValueError("API identity is not the verified database owner")
        jobs = _payload(enterprise.get("/jobs/mine", params={"pageSize": 100}))["items"]
        for key, scenario_key, label in RECIPES:
            spec = specs[scenario_key]
            targets = [j for j in jobs if j["title"] == spec["title"] and j["isDemo"]
                       and j["companyName"] == catalog["companyName"]]
            if len(targets) != 1:
                raise ValueError("Expected one unchanged curated target job")
            job = targets[0]
            slot = state["slots"].setdefault(key, {})
            account = state["accounts"][key]
            with httpx.Client(base_url=API, timeout=60, trust_env=False) as student:
                registered = student.post("/auth/register", json={**account,
                    "displayName": label, "role": "student"})
                if registered.status_code not in (201, 409):
                    registered.raise_for_status()
                student_user = _sync_login(student, **account)
                if student_user["role"] != "student":
                    raise ValueError("Unexpected recipe account role")
                if "resumeVersionId" not in slot:
                    if key == "statement":
                        # Reuse existing named material after an interrupted run.
                        resumes = _payload(student.get("/resumes"))
                        matching = [r for r in resumes if r["title"] == label]
                        if matching:
                            versions = matching[0]["versions"]
                            if len(matching) != 1 or len(versions) != 1:
                                raise ValueError("Ambiguous statement material")
                            if versions[0]["status"] != "completed":
                                wait(student, versions[0]["taskId"])
                            slot["resumeVersionId"] = versions[0]["id"]
                        else:
                            upload = _payload(student.post("/resumes", data={"title": label},
                                files={"file": ("statement.txt", (
                                    "合成教学材料，人物经历均虚构。\n"
                                    "姓名：仅声明学生\n技能：Python、FastAPI、SQL、pytest。\n"
                                    "自述做过报名接口，但未提交项目源码或测试。\n"
                                ).encode(), "text/plain")}))
                            wait(student, upload["taskId"])
                            slot["resumeVersionId"] = upload["versionId"]
                        slot["projectVersionIds"] = []
                    else:
                        uploads = []
                        seed(student, [{"caseId": key, "title": label,
                            "resumeName": label, "resumeFilename": spec["resumeFile"],
                            "projectName": label + "作品", "projectFilename": spec["projectFile"]}],
                            assets, uploads)
                        slot["resumeVersionId"] = uploads[0]["resumeVersionId"]
                        slot["projectVersionIds"] = [uploads[0]["projectVersionId"]]
                    save(state_path, state)
                if "reportId" not in slot:
                    if "taskId" not in slot:
                        accepted = _payload(student.post("/matches", json={
                            "jobId": job["id"], "resumeVersionId": slot["resumeVersionId"],
                            "projectVersionIds": slot["projectVersionIds"],
                            "externalAiConsent": False,
                        }))
                        slot["taskId"] = accepted["taskId"]
                        save(state_path, state)
                    task, _ = wait(student, slot["taskId"])
                    slot["reportId"] = task["reportId"]
                    save(state_path, state)
                report = _payload(student.get(f"/match-reports/{slot['reportId']}"))
                if report["jobId"] != job["id"] or report["analysisMode"] != "rules":
                    raise ValueError("Report must come from the actual rules workflow")
                if "applicationId" not in slot:
                    delivery = _payload(student.post("/applications", json={
                        "reportId": slot["reportId"], "shareConsent": True,
                    }))
                    slot["applicationId"] = delivery["id"]
                    save(state_path, state)
                # Opening a frozen report is an explicit audited product action.
                # Detail GET intentionally exports no report; never bypass that gate.
                application = _payload(
                    enterprise.post(f"/applications/{slot['applicationId']}/view")
                )
                if (application["reportId"] != slot["reportId"]
                    or application["status"] == "withdrawn"):
                    raise ValueError("Saved delivery no longer matches; do not replace it")
                snapshot_hash = normalized_snapshot_hash(application["report"])
                if slot.get("snapshotSha256", snapshot_hash) != snapshot_hash:
                    raise ValueError("Frozen report changed")
                slot["snapshotSha256"] = snapshot_hash
                save(state_path, state)
                records.append({"case": key, "jobId": job["id"], "reportId": slot["reportId"],
                    "applicationId": slot["applicationId"], "snapshotSha256": snapshot_hash,
                    "verdicts": [item["verdict"] for item in report["items"]]})
    return records


def _sync_login(client, email, password):
    return _payload(client.post("/auth/login", json={"email": email, "password": password}))["user"]


async def verify_target_and_import(runtime):
    from app.models.identity import User
    from scripts.import_market_scenarios import seed_scenarios

    engine = create_async_engine(runtime["env"]["DATABASE_URL"], hide_parameters=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            database = await session.scalar(text("select current_database()"))
            if database != "cp_home_discovery_test_20261027":
                raise ValueError("Database identity mismatch")
            owner = await session.scalar(
                select(User).where(User.email == runtime["enterpriseEmail"])
            )
            if owner is None:
                raise ValueError("Preview enterprise account is missing")
            # Check the running API against the same owned DB before the first seed write.
            async with httpx.AsyncClient(base_url=API, trust_env=False) as client:
                api_user = await _login(
                    client, runtime["enterpriseEmail"], runtime["password"], "enterprise"
                )
            if api_user["id"] != str(owner.id):
                raise ValueError("API and database identities differ")
            await seed_scenarios(session, owner.id)
            return str(owner.id)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    args = parser.parse_args()
    results = run(args.runtime.resolve())
    public_path = args.runtime.resolve().with_name("market-applications-result.json")
    public_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Verified {len(results)} synthetic authorizations; result: {public_path}")


if __name__ == "__main__":
    main()
