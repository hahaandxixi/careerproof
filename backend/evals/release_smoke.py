"""Repeatable HTTP smoke chain on a named local mock E2E run, never business data.

This exercises public HTTP APIs, real parser workers and persisted reports. It
does not operate a browser or prove UI usability or real model quality. Start a
fresh run with Start-E2E.ps1 first; each run may be exercised once. Failures keep
the partial progress and all existing rows instead of silently retrying writes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.models.recruitment import Application
from evals.seed_e2e import (
    _windows_process_started_at,
    assert_unlinked_state_path,
    verify_startup_manifest,
)


def prepare_run(root: Path, run: str, venv: str, stage: str) -> None:
    """Prepare a fresh isolated run through the existing reviewed launcher.

    The connection string stays in the child environment. Existing services,
    runs, fixtures and parent environment are never stopped or overwritten.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", run):
        raise ValueError("Invalid E2E run id")
    if not re.fullmatch(r"\.venv(?:-[a-z0-9-]+)?", venv):
        raise ValueError("Invalid backend environment")
    if stage and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", stage):
        raise ValueError("Invalid frontend stage")
    url = make_url(settings.database_url)
    if url.drivername != "postgresql+asyncpg" or url.host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only a local PostgreSQL connection is allowed")
    env = os.environ.copy()
    env["E2E_DATABASE_URL"] = url.set(database=f"cp_e2e_{run}").render_as_string(
        hide_password=False
    )
    env["E2E_STORAGE_DIR"] = str(root / ".tmp/e2e-storage" / run)
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(root.parent / "scripts/Start-E2E.ps1"),
        "-RunId",
        run,
        "-BackendVenv",
        venv,
        "-SyntheticVerification",
        "-ActivateSyntheticBudget",
    ]
    if stage:
        cmd += ["-FrontendStage", stage]
    subprocess.run(cmd, cwd=root, env=env, check=True)


def validate_run(
    root: Path, run: str, *, process_probe=_windows_process_started_at
) -> tuple[dict, dict]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", run):
        raise ValueError("Invalid E2E run id")
    files = [root / ".tmp/e2e" / f"{run}.json", root / ".tmp/e2e-run" / f"processes-{run}.json"]
    for file in files:
        assert_unlinked_state_path(file)
    credentials, manifest = [json.loads(f.read_text(encoding="utf-8-sig")) for f in files]
    if (
        credentials.get("runId") != run
        or manifest.get("runId") != run
        or credentials.get("apiBaseUrl") != "http://127.0.0.1:8001/api/v1/"
        or manifest.get("backendPort") != 8001
        or manifest.get("frontendPort") != 3001
        or manifest.get("databaseName") != f"cp_e2e_{run}"
        or manifest.get("aiProvider") != "mock"
        or str(manifest.get("aiExternalEnabled")).lower() != "false"
        or manifest.get("syntheticVerification") is not True
        or manifest.get("backendTarget") != "evals.e2e_verification:create_app --factory"
    ):
        raise ValueError("Requires this run's isolated mock verification entry")
    expected = (root / ".tmp/e2e-storage" / run).resolve()
    if Path(manifest.get("storageDir", "")).resolve() != expected:
        raise ValueError("Storage does not belong to this E2E run")
    verify_startup_manifest(
        manifest,
        run_id=run,
        database_name=f"cp_e2e_{run}",
        storage_dir=expected,
        process_probe=process_probe,
    )
    return credentials, manifest


def archive(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return output.getvalue()


def smoke_account(root: Path, run: str) -> dict[str, str]:
    """Give smoke writes a separate synthetic owner, leaving seed replay intact."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", run):
        raise ValueError("Invalid E2E run id")
    path = root / ".tmp/release-smoke" / f"{run}.credentials.json"
    assert_unlinked_state_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    account = {
        "email": f"smoke-{run}@example.com",
        "password": secrets.token_urlsafe(24),
        "displayName": "合成首版验收学生",
        "role": "student",
    }
    with path.open("x", encoding="utf-8") as file:
        json.dump(account, file, ensure_ascii=False)
    return account


async def snapshot_hashes(run: str) -> dict[str, str]:
    url = make_url(settings.database_url)
    if url.drivername != "postgresql+asyncpg" or url.host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only a local PostgreSQL connection is allowed")
    engine = create_async_engine(url.set(database=f"cp_e2e_{run}"), hide_parameters=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            if await connection.scalar(text("SELECT current_database()")) != f"cp_e2e_{run}":
                raise ValueError("Wrong database")
            rows = await connection.execute(select(Application.id, Application.report_snapshot))
            return {
                str(id_): hashlib.sha256(
                    json.dumps(
                        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                    ).encode()
                ).hexdigest()
                for id_, value in rows
            }
    finally:
        await engine.dispose()


async def verify_reconsent(data, student, hr, other, job_id, old_id, new_report,
                           old_notices=()) -> dict:
    """Check explicit student consent, new frozen source and permanent old denial."""
    board_url = f"/api/v1/jobs/{job_id}/applications"
    board = await data(hr, "GET", board_url)
    assert old_id not in {item["id"] for item in board}, "Withdrawn row remains on board"
    payload = {"reportId": new_report["id"], "shareConsent": True}
    await data(student, "POST", "/api/v1/applications", expected=422,
               json={**payload, "shareConsent": False})
    renewed = await data(student, "POST", "/api/v1/applications", expected=201, json=payload)
    new_id = renewed["id"]
    assert new_id != old_id and renewed["reportId"] == new_report["id"]
    assert renewed["status"] == "submitted"
    assert renewed["consentVersion"] and not renewed.get("replyText")
    assert not renewed.get("replyKind") and not renewed.get("replyReferences")
    again = await data(student, "POST", "/api/v1/applications", expected=201, json=payload)
    assert again["id"] == new_id, "Repeated consent created another application"
    detail = await data(hr, "GET", f"/api/v1/applications/{new_id}")
    assert detail["reportId"] == new_report["id"]
    await data(other, "GET", f"/api/v1/applications/{new_id}", expected=404)
    opened = await data(hr, "POST", f"/api/v1/applications/{new_id}/view")
    assert opened["report"] == new_report, "New application copied a stale snapshot"
    reread = await data(hr, "POST", f"/api/v1/applications/{new_id}/view")
    assert reread["report"] == opened["report"]
    board = await data(hr, "GET", board_url)
    ids = [item["id"] for item in board]
    assert old_id not in ids and ids.count(new_id) == 1
    for method, suffix in [("GET", ""), ("POST", "/view"), ("POST", "/resume-download")]:
        await data(hr, method, f"/api/v1/applications/{old_id}{suffix}", expected=404)
    await data(hr, "POST", f"/api/v1/applications/{old_id}/reply", expected=404,
               json={"kind": "continue", "text": "合成旧授权不得复活"})
    for notice in old_notices:
        await data(hr, "GET", f"/api/v1/notifications/{notice}/target", expected=404)
    return opened


async def exercise(run: str, root: Path) -> Path:
    credentials, _ = validate_run(root, run)
    path = root / ".tmp/release-smoke" / f"{run}.json"
    assert_unlinked_state_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # CreateNew means a rerun cannot discard an earlier failure or repeat writes.
    with path.open("x", encoding="utf-8") as file:
        json.dump({"runId": run, "status": "starting", "steps": []}, file)
    result = {
        "runId": run,
        "scope": "HTTP only; local mock; no browser/real model",
        "status": "running",
        "steps": [],
        "ids": {},
    }

    def persist():
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(name, **facts):
        result["steps"].append({"name": name, "passed": True, **facts})
        persist()

    async def data(client, method, endpoint, expected=200, **kwargs):
        response = await client.request(method, endpoint, **kwargs)
        if response.status_code != expected:
            # Do not dump request bodies, credentials, cookies or raw error payloads.
            raise RuntimeError(
                f"{method} {endpoint}: expected {expected}, got {response.status_code}"
            )
        return response.json()["data"] if expected < 400 else None

    async def settle(client, task):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            view = await data(client, "GET", f"/api/v1/analysis-tasks/{task}")
            if view["status"] == "completed":
                return view
            if view["status"] in {"failed", "cancelled"}:
                raise RuntimeError(f"Task {task} ended {view['status']}")
            await asyncio.sleep(0.5)
        raise TimeoutError(f"Task {task} did not settle in 120 seconds")

    try:
        original = await snapshot_hashes(run)
        fixture_snapshot_count = len(original)
        async with (
            httpx.AsyncClient(
                base_url="http://127.0.0.1:8001",
                timeout=30,
                trust_env=False,
                follow_redirects=False,
            ) as student,
            httpx.AsyncClient(
                base_url="http://127.0.0.1:8001",
                timeout=30,
                trust_env=False,
                follow_redirects=False,
            ) as hr,
            httpx.AsyncClient(
                base_url="http://127.0.0.1:8001",
                timeout=30,
                trust_env=False,
                follow_redirects=False,
            ) as other,
        ):
            for client, slot in [(hr, "enterprise"), (other, "studentA2")]:
                account = credentials["accounts"][slot]
                await data(
                    client,
                    "POST",
                    "/api/v1/auth/login",
                    json={"email": account["email"], "password": account["password"]},
                )
            await data(
                student,
                "POST",
                "/api/v1/auth/register",
                expected=201,
                json=smoke_account(root, run),
            )
            record("independent_role_sessions")
            org = await data(
                hr,
                "POST",
                "/api/v1/enterprises",
                expected=201,
                json={"name": f"合成首版验收-{run}"},
            )
            job = await data(
                hr,
                "POST",
                "/api/v1/jobs",
                expected=201,
                json={
                    "enterpriseId": org["id"],
                    "companyName": org["name"],
                    "title": "合成Python实习岗位",
                    "status": "published",
                    "category": "software",
                    "requirements": [
                        {"rawText": f"提供{skill}相关实践材料", "skillName": skill, "weight": 2}
                        for skill in ["Python", "SQL", "pytest"]
                    ],
                },
            )
            result["ids"]["job"] = job["id"]
            resume = await data(
                student,
                "POST",
                "/api/v1/resumes",
                expected=202,
                data={"title": "合成首版简历"},
                files={
                    "file": (
                        "release-resume.txt",
                        "合成学生声明Python与SQL技能；本人贡献、运行结果仍需核对。".encode(),
                        "text/plain",
                    )
                },
            )
            project = await data(
                student,
                "POST",
                "/api/v1/projects",
                expected=201,
                json={"name": "合成首版作品", "requestId": str(uuid4())},
            )
            old = await data(
                student,
                "POST",
                f"/api/v1/projects/{project['id']}/versions",
                expected=202,
                data={"requestId": str(uuid4())},
                files={
                    "file": (
                        "release-v1.zip",
                        archive({"README.md": "合成自述：会Python和SQL；暂无实现。"}),
                        "application/zip",
                    )
                },
            )
            for upload in [resume, old]:
                await settle(student, upload["taskId"])
            task = await data(
                student,
                "POST",
                "/api/v1/matches",
                expected=202,
                json={
                    "jobId": job["id"],
                    "resumeVersionId": resume["versionId"],
                    "projectVersionIds": [old["versionId"]],
                    "externalAiConsent": False,
                },
            )
            completed = await settle(student, task["taskId"])
            base = await data(student, "GET", f"/api/v1/match-reports/{completed['reportId']}")
            result["ids"]["baseReport"] = base["id"]
            assert len(base["items"]) == 3
            record(
                "uploads_parsed_and_report_generated",
                requirementCount=3,
                mode="mock/rule fallback; not real AI success",
            )
            await data(
                student,
                "POST",
                "/api/v1/applications",
                expected=422,
                json={"reportId": base["id"], "shareConsent": False},
            )
            application = await data(
                student,
                "POST",
                "/api/v1/applications",
                expected=201,
                json={"reportId": base["id"], "shareConsent": True},
            )
            aid = application["id"]
            result["ids"]["application"] = aid
            again = await data(
                student,
                "POST",
                "/api/v1/applications",
                expected=201,
                json={"reportId": base["id"], "shareConsent": True},
            )
            assert again["id"] == aid
            await data(other, "GET", f"/api/v1/applications/{aid}", expected=404)
            await data(hr, "GET", f"/api/v1/match-reports/{base['id']}", expected=404)
            opened = await data(hr, "POST", f"/api/v1/applications/{aid}/view")
            frozen = opened["report"]
            focus = base["items"][0]
            await data(
                hr,
                "POST",
                f"/api/v1/applications/{aid}/reply",
                json={
                    "kind": "continue",
                    "text": (
                        f"【第1项：{focus['requirementTitle']}】\n"
                        "合成问题：请补实现与本人负责部分，运行仍待核验。"
                    ),
                    "references": [{"requirementId": focus["requirementId"], "citationIds": []}],
                },
            )
            reply = await data(
                student,
                "GET",
                f"/api/v1/match-reports/{base['id']}/enterprise-replies/{focus['requirementId']}",
            )
            assert reply["applicationId"] == aid
            downloaded = await hr.post(f"/api/v1/applications/{aid}/resume-download")
            assert downloaded.status_code == 200 and downloaded.content
            student_notices = await data(student, "GET", "/api/v1/notifications")
            linked_notice = None
            for n in student_notices["items"]:
                if n["accessible"] and not n["readAt"]:
                    target = await data(student, "GET", f"/api/v1/notifications/{n['id']}/target")
                    if aid in target["href"]:
                        linked_notice = n["id"]
                        break
            assert linked_notice, "No linked unread student notification"
            read = await data(student, "POST", f"/api/v1/notifications/{linked_notice}/read")
            assert read["unreadCount"] == student_notices["unreadCount"] - 1
            record("explicit_consent_idempotency_role_permissions_and_linked_reply")
            growth = await data(
                student,
                "POST",
                f"/api/v1/match-reports/{base['id']}/growth-tasks",
                expected=201,
                json={
                    "requirementId": focus["requirementId"],
                    "gapKind": "implementation",
                    "deliverable": "合成Python新版源码与本人分工说明（运行待核验）",
                    "steps": ["补总数计算实现", "提供本人分工说明并保留运行待核验状态"],
                    "acceptanceChecks": ["引用能定位新版源码", "静态源码不冒充执行成功"],
                },
            )
            gid = growth["id"]
            result["ids"]["growthTask"] = gid
            new = await data(
                student,
                "POST",
                f"/api/v1/projects/{project['id']}/versions",
                expected=202,
                data={"requestId": str(uuid4())},
                files={
                    "file": (
                        "release-v2.zip",
                        archive(
                            {
                                "main.py": "def total(values):\n    return sum(values)\n",
                                "tests/test_total.py": (
                                    "from main import total\n\ndef test_total():\n"
                                    "    assert total([1, 2]) == 3\n"
                                ),
                                "README.md": "合成静态源码，仅供演示；未执行，贡献与运行待核验。",
                            }
                        ),
                        "application/zip",
                    )
                },
            )
            await settle(student, new["taskId"])
            await data(
                student,
                "PUT",
                f"/api/v1/growth-tasks/{gid}/materials",
                json={
                    "resumeVersionId": resume["versionId"],
                    "projectVersionIds": [new["versionId"]],
                },
            )
            await data(
                student,
                "POST",
                f"/api/v1/growth-tasks/{gid}/analyze",
                expected=202,
                json={"externalAiConsent": False},
            )
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                view = await data(student, "GET", f"/api/v1/growth-tasks/{gid}")
                if view["status"] in {"compared", "failed"}:
                    break
                await asyncio.sleep(0.5)
            assert view["status"] == "compared", "Growth analysis did not complete"
            comparison = view["comparison"]
            assert comparison["baseId"] == base["id"]
            assert comparison["targetId"] != base["id"]
            assert "materials" in comparison["contextChanges"]
            assert "requirements" not in comparison["contextChanges"]
            assert len(comparison["items"]) == 3
            assert any(item["addedEvidence"] for item in comparison["items"])
            result["ids"]["newReport"] = comparison["targetId"]
            record(
                "new_materials_report_and_item_changes",
                requirementCount=3,
                items=[
                    {
                        "title": i["title"],
                        "changes": i["changes"],
                        "addedEvidence": len(i["addedEvidence"]),
                    }
                    for i in comparison["items"]
                ],
            )
            reread = await data(hr, "POST", f"/api/v1/applications/{aid}/view")
            assert reread["report"] == frozen
            await data(hr, "GET", f"/api/v1/growth-tasks/{gid}", expected=403)
            await data(other, "GET", f"/api/v1/growth-tasks/{gid}", expected=404)
            notice = await data(hr, "GET", "/api/v1/notifications")
            own_notices = []
            for n in notice["items"]:
                if n["accessible"]:
                    target = await data(hr, "GET", f"/api/v1/notifications/{n['id']}/target")
                    if aid in target["href"]:
                        own_notices.append(n["id"])
            assert own_notices
            await data(student, "POST", f"/api/v1/applications/{aid}/withdraw")
            for verb, suffix in [("GET", ""), ("POST", "/view"), ("POST", "/resume-download")]:
                await data(hr, verb, f"/api/v1/applications/{aid}{suffix}", expected=404)
            for nid in own_notices:
                await data(hr, "GET", f"/api/v1/notifications/{nid}/target", expected=404)
            await data(
                hr,
                "POST",
                f"/api/v1/applications/{aid}/reply",
                expected=404,
                json={"kind": "continue", "text": "合成撤回后访问，应被拒绝"},
            )
            target_report = await data(
                student, "GET", f"/api/v1/match-reports/{comparison['targetId']}"
            )
            renewed = await verify_reconsent(
                data, student, hr, other, job["id"], aid, target_report, own_notices
            )
            result["ids"]["renewedApplication"] = renewed["id"]
            original[aid] = hashlib.sha256(json.dumps(
                frozen, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()).hexdigest()
            original[renewed["id"]] = hashlib.sha256(json.dumps(
                target_report, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()).hexdigest()
            record("frozen_snapshot_private_growth_withdraw_and_reconsent",
                   reportId=target_report["id"], applicationId=renewed["id"])
        final = await snapshot_hashes(run)
        assert all(final.get(k) == v for k, v in original.items())
        record("all_original_fixture_snapshots_unchanged", count=fixture_snapshot_count,
               smokeSnapshotsChecked=len(original) - fixture_snapshot_count)
        result["status"] = "passed"
        persist()
        return path
    except BaseException as exc:
        result["status"] = "failed"
        # HTTP helper errors are bounded and contain no response data/credentials.
        result["errorType"] = type(exc).__name__
        persist()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Prepare a fresh isolated E2E run; Docker must already be ready",
    )
    parser.add_argument("--backend-venv", default=".venv-dependency23")
    parser.add_argument("--frontend-stage", default="dep-frontend-20261010")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.prepare:
            prepare_run(root, args.run_id, args.backend_venv, args.frontend_stage)
        output = asyncio.run(exercise(args.run_id, root))
    except Exception as exc:
        print(f"Release HTTP smoke did not pass: {type(exc).__name__}; partial state retained")
        return 1
    print(f"Release HTTP smoke passed; evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
