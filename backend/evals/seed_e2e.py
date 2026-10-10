"""Seed the isolated E2E double-delivery fixture behind product APIs only.

E2E-01 task card plus the Codex first-round isolation review: the fixture runs
against an isolated ``cp_e2e_<run-id>`` PostgreSQL database, an isolated storage
directory and a loopback-only API. This module is the only supported seeding entry
point and enforces the isolation guards itself:

- ``guard_database_url`` refuses any URL whose dialect is not asyncpg, whose host is
  not loopback, whose name does not match ``cp_e2e_[a-z0-9-]+``, or whose URL carries
  a query or fragment that could override connection parameters.
- Seeding (not only database creation) requires the exact ``cp_e2e_<run-id>`` name.
- ``guard_base_url`` refuses non-loopback hosts, any port other than the isolated
  8001 (a business backend may listen on 8000/3000), any path other than
  ``/api/v1``, and userinfo/query/fragment targets.
- The CLI seeds only with a startup manifest written by ``scripts/Start-E2E.ps1``
  (own PID plus start time, run id, database name, storage directory, forced mock
  AI); the backend PID must be alive with a matching creation time. Every refusal
  happens before the first HTTP request or database connection.
- Account passwords come from ``secrets`` and are written only to the ignored local
  state file (``backend/.tmp/e2e/<run-id>.json``); they are never printed or logged.
- A run id seeds exactly once. Re-running with the same run id only verifies the
  recorded fixture (read-only HTTP GETs plus fixture-row reads); it never creates a
  second account, delivery or notification, and never un-withdraws a withdrawn
  delivery. A fresh fixture requires an explicit new run id.
- Materials are synthetic and generated here; business tables, existing resumes and
  demo deliveries are never read or copied.

The actual ``cp_e2e_*`` database creation (``--create-database``) and any Alembic
migration stay review-gated: they must only be executed after Codex sign-off, via
``scripts/Start-E2E.ps1``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.analysis import AnalysisTask, MatchItem, MatchReport
from app.models.enums import TaskStatus
from app.models.identity import StudentProfile
from app.models.notification import Notification
from app.models.portfolio import Resume, ResumeVersion
from app.models.recruitment import Application, ApplicationEvent

RUN_ID_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,31})")
DATABASE_NAME_PATTERN = re.compile(r"cp_e2e_[a-z0-9](?:[a-z0-9-]{0,62})")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
POSTGRESQL_SCHEME = "postgresql+asyncpg"
E2E_BACKEND_PORT = 8001
DEFAULT_BASE_URL = f"http://127.0.0.1:{E2E_BACKEND_PORT}/api/v1"
DEFAULT_STATE_DIR = Path(__file__).resolve().parents[1] / ".tmp" / "e2e"
DEFAULT_MANIFEST_DIR = Path(__file__).resolve().parents[1] / ".tmp" / "e2e-run"
STORAGE_KEY_TEMPLATE = "e2e/{run_id}/resume-{student_key}-v1.txt"

# Delivery plan: slot -> (student key, job slot). Student and student A2 are two
# different synthetic students; A and A2 deliver to the same job A so the later
# browser stage can exercise notification filtering and "withdraw A, A2/B remain".
DELIVERY_PLAN: tuple[tuple[str, str, str], ...] = (
    ("A", "student", "A"),
    ("B", "student", "B"),
    ("A2", "studentA2", "A"),
)
STUDENT_LABELS = {"student": "", "studentA2": "A2"}
JOB_SLOTS = ("A", "B")


def _resume_text(student_label: str) -> str:
    return (
        "E2E 合成简历（非真实材料，仅供隔离测试）\n"
        f"姓名：E2E 合成学生{student_label}\n"
        "技能声明：能够使用 Python 编写数据处理脚本\n"
        "项目：合成数据看板（仅声明，未附证据）\n"
    )


def _resume_material(student_label: str) -> dict:
    """Fixed per-student material with the real cited line facts for the snapshot."""
    text = _resume_text(student_label)
    raw = text.encode("utf-8")
    lines = text.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("技能声明"))
    return {
        "bytes": raw,
        "contentHash": hashlib.sha256(raw).hexdigest(),
        "citationLineStart": index + 1,
        "citationLineEnd": index + 1,
        "citationSnippet": lines[index],
    }


class IsolationError(RuntimeError):
    """Raised when a target, state or replay violates the E2E isolation contract."""


def guard_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise IsolationError("run id must match [a-z0-9][a-z0-9-]{0,31}; got an invalid value")
    return run_id


def expected_database_name(run_id: str) -> str:
    return f"cp_e2e_{guard_run_id(run_id)}"


def guard_database_url(database_url: str) -> str:
    """Refuse any non-loopback or non-``cp_e2e_`` database before migration or seeding."""
    parsed = urlsplit(database_url)
    if parsed.scheme != POSTGRESQL_SCHEME:
        raise IsolationError("E2E database URL must use the postgresql+asyncpg scheme")
    if parsed.query or parsed.fragment:
        raise IsolationError("E2E database URL must not carry a query or fragment")
    host = (parsed.hostname or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise IsolationError(f"E2E database host must be loopback; got {host or 'missing'}")
    name = parsed.path.lstrip("/")
    if not DATABASE_NAME_PATTERN.fullmatch(name):
        raise IsolationError("E2E database name must match cp_e2e_[a-z0-9-]; refusing the target")
    return name


def assert_run_database(name: str, run_id: str) -> str:
    expected = expected_database_name(run_id)
    if name != expected:
        raise IsolationError(f"E2E database name must be {expected} for this run; got {name}")
    return name


def guard_base_url(base_url: str) -> str:
    """Refuse anything but the isolated loopback backend (business ports included)."""
    parsed = urlsplit(base_url)
    if parsed.scheme != "http":
        raise IsolationError("E2E API base URL must use http on loopback")
    if parsed.username is not None or parsed.password is not None:
        raise IsolationError("E2E API base URL must not carry userinfo")
    if parsed.query or parsed.fragment:
        raise IsolationError("E2E API base URL must not carry a query or fragment")
    host = (parsed.hostname or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise IsolationError(f"E2E API host must be loopback; got {host or 'missing'}")
    try:
        port = parsed.port
    except ValueError:
        raise IsolationError("E2E API base URL has an invalid port") from None
    if port != E2E_BACKEND_PORT:
        raise IsolationError(
            f"E2E API port must be {E2E_BACKEND_PORT}; port {port} may be a business backend"
        )
    path = parsed.path.rstrip("/")
    if path != "/api/v1":
        raise IsolationError('E2E API base path must be exactly "/api/v1"')
    # urlsplit unpacks IPv6 brackets; the rebuilt URL needs them back or ::1
    # would become the invalid "http://::1:8001/api/v1".
    bracketed = f"[{host}]" if ":" in host else host
    return f"http://{bracketed}:{E2E_BACKEND_PORT}/api/v1"


def normalized_snapshot_hash(snapshot: object) -> str:
    """Canonical SHA-256 over the frozen report snapshot; stable across re-reads."""
    canonical = json.dumps(
        snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_startup_manifest(manifest_path: Path) -> dict:
    path = Path(manifest_path)
    if not path.exists():
        raise IsolationError(
            f"no E2E startup manifest at {path}; the seeder only runs against a backend "
            "started by scripts/Start-E2E.ps1 for this run id"
        )
    # Windows PowerShell 5 Set-Content -Encoding utf8 prepends a BOM; utf-8-sig
    # accepts both that and the plain utf-8 a BOM-less writer produces.
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise IsolationError(
            f"E2E startup manifest at {path} is not valid JSON: {exc.msg}"
        ) from None
    if not isinstance(manifest, dict):
        raise IsolationError("E2E startup manifest must be a JSON object")
    return manifest


_DOTNET_FRACTION = re.compile(r"(\.\d{6})\d+")


def parse_utc_timestamp(value: object) -> datetime:
    """Parse the .NET ``o`` stamps the manifest uses (7 fraction digits, ``Z``)."""
    text = str(value).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    text = _DOTNET_FRACTION.sub(r"\1", text, count=1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise IsolationError(f"not an ISO-8601 instant: {value!r}") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _windows_process_started_at(pid: int) -> datetime | None:
    """Creation time (UTC) of a live PID, or None when it is gone or has exited."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:  # Non-Windows has no safe probe here; refuse to seed.
        return None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Defaults truncate 64-bit HANDLEs through c_int; every kernel32 call here
    # needs explicit signatures on 64-bit Windows.
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None

    def stamp(filetime: wintypes.FILETIME) -> int:
        return (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime

    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return None
        # While any handle keeps an exited PID reserved, OpenProcess still
        # succeeds; liveness therefore needs the exit status, not just a handle
        # and a creation time.
        if stamp(exit_time) != 0:
            return None
        created = stamp(creation)
        if created <= 0:
            return None
        return datetime.fromtimestamp(created / 10_000_000 - 11644473600, tz=UTC)
    finally:
        kernel32.CloseHandle(handle)


def verify_startup_manifest(
    manifest: dict,
    *,
    run_id: str,
    database_name: str,
    storage_dir: Path,
    backend_port: int = E2E_BACKEND_PORT,
    process_probe: Callable[[int], datetime | None] = _windows_process_started_at,
) -> dict:
    """Bind the seeding to the recorded isolated startup; refuse without proof."""
    expected = {
        "runId": run_id,
        "databaseName": expected_database_name(run_id),
        "backendPort": backend_port,
        "aiExternalEnabled": "false",
        "aiProvider": "mock",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise IsolationError(f"startup manifest {key} mismatch; refusing to seed")
    recorded_storage = str(manifest.get("storageDir", ""))
    if not recorded_storage:
        raise IsolationError("startup manifest has no storageDir; refusing to seed")
    if os.path.normcase(str(Path(recorded_storage).resolve())) != os.path.normcase(
        str(Path(storage_dir).resolve())
    ):
        raise IsolationError("startup manifest storageDir mismatch; refusing to seed")
    backend = manifest.get("backend") or {}
    try:
        pid = int(backend.get("id", 0))
    except (TypeError, ValueError):
        raise IsolationError("startup manifest backend PID is invalid; refusing to seed") from None
    if pid <= 0:
        raise IsolationError("startup manifest backend PID is invalid; refusing to seed")
    started_at = process_probe(pid)
    if started_at is None:
        raise IsolationError(
            f"backend PID {pid} is not running; refusing to seed against an unverified process"
        )
    try:
        recorded_time = parse_utc_timestamp(backend.get("startedAt"))
    except IsolationError:
        raise IsolationError(
            "startup manifest backend start time is invalid; refusing to seed"
        ) from None
    # .NET StartTime and FILETIME round-trip at millisecond precision; PID reuse
    # moves the creation time by far more than this tolerance.
    if abs((started_at - recorded_time).total_seconds()) > 2:
        raise IsolationError(
            "backend PID start time does not match the manifest; refusing to seed"
        )
    return backend


def _payload(response: httpx.Response) -> dict:
    response.raise_for_status()
    body = response.json()
    if body.get("code") != 0:
        raise IsolationError(f"unexpected API response code: {body.get('code')}")
    return body["data"]


async def _register(client: httpx.AsyncClient, email: str, password: str, role: str) -> dict:
    display_name = "E2E 合成企业" if role == "enterprise" else "E2E 合成学生"
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "displayName": display_name,
            "role": role,
        },
    )
    if response.status_code == 409:
        raise IsolationError(
            "an account for this run id already exists but no fixture state was found; "
            "never adopt it - choose a new run id instead"
        )
    response.raise_for_status()
    return _payload(response)["user"]


async def _login(client: httpx.AsyncClient, email: str, password: str, role: str) -> dict:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        raise IsolationError(
            f"fixture login failed for {email}; the state file does not match a live fixture"
        )
    user = _payload(response)["user"]
    if user["role"] != role:
        raise IsolationError(f"fixture account {email} has an unexpected role")
    return user


def _job_payload(enterprise_id: str, company_name: str, slot: str) -> dict:
    return {
        "enterpriseId": enterprise_id,
        "title": f"E2E 岗位{slot}（合成）",
        "companyName": company_name,
        "description": "隔离端到端夹具岗位：仅用于合成测试，不是实际招聘。",
        "status": "published",
        "category": "software",
        "city": "合成城市",
        "employmentType": "internship",
        "requirements": [
            {
                "rawText": f"岗位{slot}要求：能够使用 Python 编写数据处理脚本",
                "skillName": "Python",
            }
        ],
    }


def _evidence_snapshot(job: dict, material: dict) -> dict:
    requirement = job["requirements"][0]
    return {
        "skill": "Python",
        "requirementTitle": requirement["rawText"],
        "claimed": True,
        # Both deliveries on a job cite the same R1-E1 item so the reply-reference
        # chain of the later browser stage can be exercised against either snapshot.
        "evidenceList": [
            {
                "citationId": "R1-E1",
                "evidenceType": "resume_claim",
                "skill": "Python",
                "filePath": "e2e/合成简历.txt",
                "lineStart": material["citationLineStart"],
                "lineEnd": material["citationLineEnd"],
                "snippet": material["citationSnippet"],
                "strength": "claimed",
                "explanation": "仅简历声明，未附可执行证据（合成夹具）",
                "contentHash": material["contentHash"],
            }
        ],
    }


async def _insert_student_resume(
    session: AsyncSession,
    *,
    student_user_id: UUID,
    student_label: str,
    storage_key: str,
    material: dict,
) -> str:
    profile = await session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_user_id)
    )
    if profile is None:
        raise IsolationError("synthetic student profile is missing; registration failed")
    resume = Resume(student_id=profile.id, title=f"E2E 合成简历{student_label}（合成材料）")
    session.add(resume)
    await session.flush()
    version = ResumeVersion(
        resume_id=resume.id,
        version_number=1,
        storage_key=storage_key,
        mime_type="text/plain",
        content_hash=material["contentHash"],
        size_bytes=len(material["bytes"]),
        parse_status="completed",
        original_filename=f"e2e-合成简历{student_label}.txt",
    )
    session.add(version)
    await session.flush()
    return str(version.id)


async def _insert_student_report(
    session: AsyncSession,
    *,
    student_user_id: UUID,
    student_label: str,
    slot: str,
    job: dict,
    version_id: str,
    material: dict,
) -> str:
    """One named fixed report for one (student, job) pair over the shared version."""
    profile = await session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_user_id)
    )
    if profile is None:
        raise IsolationError(f"synthetic student profile for slot {slot} is missing")
    display_name = f"E2E 合成学生{student_label}"
    # match_reports.analysis_task_id is unique: one completed task backs each report.
    task = AnalysisTask(
        created_by=student_user_id, task_type="job_match", status=TaskStatus.COMPLETED
    )
    session.add(task)
    await session.flush()
    report = MatchReport(
        analysis_task_id=task.id,
        job_id=UUID(job["id"]),
        # Formal AnalysisService freezes candidateId as the account User.id; the
        # profile id above is a different identity and must never stand in for it.
        candidate_ref=str(student_user_id),
        candidate_name=display_name,
        summary=f"E2E 固定报告 {slot}（合成夹具）",
        overall_score=55,
        job_snapshot={
            "title": job["title"], "category": job.get("category", "software"),
            # Match AnalysisService's frozen requirement schema; omitting it
            # makes an unchanged live requirement look like a new requirement.
            "requirements": [{
                "id": row["id"], "title": row["rawText"],
                "skill": row["skillName"], "weight": row["weight"],
            } for row in job["requirements"]],
        },
        materials_snapshot=[
            {
                "kind": "resume",
                "id": version_id,
                "title": f"E2E 合成简历{student_label}（合成材料）",
                "versionNumber": 1,
                "contentHash": material["contentHash"],
            }
        ],
        gaps=[],
        claimed_only=["能够使用 Python 编写数据处理脚本"],
    )
    session.add(report)
    await session.flush()
    session.add(
        MatchItem(
            report_id=report.id,
            requirement_id=UUID(job["requirements"][0]["id"]),
            rule_base_score=0.55,
            weight=job["requirements"][0]["weight"],
            final_score=55,
            verdict="claimed_only",
            explanation="仅见简历声明，等待企业核验（合成夹具）",
            formula_version="e2e-fixture-v1",
            evidence_snapshot=_evidence_snapshot(job, material),
        )
    )
    await session.flush()
    return str(report.id)


async def _insert_fixture_rows(
    session: AsyncSession,
    *,
    student_user_ids: dict[str, UUID],
    job_by_slot: dict[str, dict],
    storage_key_by_student: dict[str, str],
    material_by_student: dict[str, dict],
) -> tuple[dict[str, str], dict[str, str]]:
    # One resume version per student; every report of that student cites the same
    # version, so both deliveries of one student share the identical material item.
    versions = {
        key: await _insert_student_resume(
            session,
            student_user_id=student_user_ids[key],
            student_label=STUDENT_LABELS[key],
            storage_key=storage_key_by_student[key],
            material=material_by_student[key],
        )
        for key in student_user_ids
    }
    reports = {}
    for slot, student_key, job_slot in DELIVERY_PLAN:
        reports[slot] = await _insert_student_report(
            session,
            student_user_id=student_user_ids[student_key],
            student_label=STUDENT_LABELS[student_key],
            slot=slot,
            job=job_by_slot[job_slot],
            version_id=versions[student_key],
            material=material_by_student[student_key],
        )
    await session.commit()
    return versions, reports


async def _load_application_snapshots(
    session_factory: async_sessionmaker, application_ids: list[str]
) -> dict[str, dict]:
    snapshots: dict[str, dict] = {}
    async with session_factory() as session:
        for application_id in application_ids:
            row = await session.get(Application, UUID(application_id))
            if row is None:
                raise IsolationError(f"application {application_id} missing after creation")
            snapshots[application_id] = row.report_snapshot
    return snapshots


async def _create_fixture(
    client_factory: Callable[[], httpx.AsyncClient],
    session_factory: async_sessionmaker,
    *,
    run_id: str,
    state_path: Path,
    storage_dir: Path,
) -> dict:
    passwords = {key: secrets.token_urlsafe(18) for key in ("student", "studentA2", "enterprise")}
    emails = {
        "student": f"e2e-{run_id}-student@e2e.example.com",
        "studentA2": f"e2e-{run_id}-student-a2@e2e.example.com",
        "enterprise": f"e2e-{run_id}-enterprise@e2e.example.com",
    }
    # Each role needs its own cookie session: one shared client would leave only the
    # last registered identity signed in for every later request.
    async with (
        client_factory() as enterprise_client,
        client_factory() as student_client,
        client_factory() as a2_client,
    ):
        student = await _register(
            student_client, emails["student"], passwords["student"], "student"
        )
        student_a2 = await _register(
            a2_client, emails["studentA2"], passwords["studentA2"], "student"
        )
        enterprise = await _register(
            enterprise_client, emails["enterprise"], passwords["enterprise"], "enterprise"
        )
        org = _payload(
            await enterprise_client.post("/enterprises", json={"name": f"E2E 合成企业 {run_id}"})
        )
        job_by_slot = {
            slot: _payload(
                await enterprise_client.post(
                    "/jobs", json=_job_payload(org["id"], org["name"], slot)
                )
            )
            for slot in JOB_SLOTS
        }
        material_by_student = {
            key: _resume_material(STUDENT_LABELS[key]) for key in STUDENT_LABELS
        }
        storage_key_by_student = {
            key: STORAGE_KEY_TEMPLATE.format(run_id=run_id, student_key=key)
            for key in STUDENT_LABELS
        }
        for key, storage_key in storage_key_by_student.items():
            (storage_dir / storage_key).parent.mkdir(parents=True, exist_ok=True)
            (storage_dir / storage_key).write_bytes(material_by_student[key]["bytes"])
        async with session_factory() as session:
            versions, reports = await _insert_fixture_rows(
                session,
                student_user_ids={
                    "student": UUID(student["id"]),
                    "studentA2": UUID(student_a2["id"]),
                },
                job_by_slot=job_by_slot,
                storage_key_by_student=storage_key_by_student,
                material_by_student=material_by_student,
            )
        clients = {"student": student_client, "studentA2": a2_client}
        deliveries: dict[str, dict] = {}
        for slot, student_key, _job_slot in DELIVERY_PLAN:
            response = await clients[student_key].post(
                "/applications",
                json={"reportId": reports[slot], "shareConsent": True},
            )
            if response.status_code != 201:
                raise IsolationError(
                    f"synthetic delivery {slot} failed: HTTP {response.status_code}: "
                    f"{response.text}"
                )
            delivery = _payload(response)
            if delivery["status"] != "submitted":
                raise IsolationError(f"synthetic delivery {slot} did not start as submitted")
            deliveries[slot] = delivery
        snapshots = await _load_application_snapshots(
            session_factory, [delivery["id"] for delivery in deliveries.values()]
        )
        state = {
            "runId": run_id,
            "createdAt": datetime.now(UTC).isoformat(),
            "apiBaseUrl": str(enterprise_client.base_url),
            "accounts": {
                key: {
                    "email": emails[key],
                    "password": passwords[key],
                    "userId": user["id"],
                }
                for key, user in (
                    ("student", student),
                    ("studentA2", student_a2),
                    ("enterprise", enterprise),
                )
            },
            "enterprise": {
                "organizationId": org["id"],
                "jobIdA": job_by_slot["A"]["id"],
                "jobIdB": job_by_slot["B"]["id"],
            },
            "materials": {
                key: {
                    "resumeVersionId": versions[key],
                    "storageKey": storage_key_by_student[key],
                    "contentHash": material_by_student[key]["contentHash"],
                    "citationLineStart": material_by_student[key]["citationLineStart"],
                    "citationLineEnd": material_by_student[key]["citationLineEnd"],
                    "citationSnippet": material_by_student[key]["citationSnippet"],
                }
                for key in ("student", "studentA2")
            },
            "reports": dict(reports),
            "applications": {
                slot: {
                    "id": deliveries[slot]["id"],
                    "student": student_key,
                    "snapshotSha256": normalized_snapshot_hash(snapshots[deliveries[slot]["id"]]),
                }
                for slot, student_key, _job_slot in DELIVERY_PLAN
            },
        }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    result = await _verify_fixture(client_factory, session_factory, state)
    result["mode"] = "created"
    return result


async def _verify_fixture(
    client_factory: Callable[[], httpx.AsyncClient],
    session_factory: async_sessionmaker,
    state: dict,
) -> dict:
    """Read-only replay: GETs through the product API plus fixture-row reads only."""
    async with (
        client_factory() as enterprise_client,
        client_factory() as student_client,
        client_factory() as a2_client,
    ):
        enterprise = await _login(
            enterprise_client,
            state["accounts"]["enterprise"]["email"],
            state["accounts"]["enterprise"]["password"],
            "enterprise",
        )
        students = {}
        for key, client in (("student", student_client), ("studentA2", a2_client)):
            students[key] = await _login(
                client,
                state["accounts"][key]["email"],
                state["accounts"][key]["password"],
                "student",
            )
        recorded_user_ids = {
            key: state["accounts"][key]["userId"] for key in ("student", "studentA2", "enterprise")
        }
        if (
            enterprise["id"] != recorded_user_ids["enterprise"]
            or students["student"]["id"] != recorded_user_ids["student"]
            or students["studentA2"]["id"] != recorded_user_ids["studentA2"]
        ):
            raise IsolationError("fixture accounts do not match the recorded user ids")
        mine = {
            "student": _payload(await student_client.get("/applications/mine")),
            "studentA2": _payload(await a2_client.get("/applications/mine")),
        }
        recorded_by_student: dict[str, set[str]] = {"student": set(), "studentA2": set()}
        for record in state["applications"].values():
            recorded_by_student[record["student"]].add(record["id"])
        for key, items in mine.items():
            if {item["id"] for item in items} != recorded_by_student[key]:
                raise IsolationError(
                    f"student {key} deliveries no longer match the recorded fixture; "
                    "refusing to seed or restore anything"
                )
        applications: dict[str, dict] = {}
        async with session_factory() as session:
            for slot, record in state["applications"].items():
                row = await session.get(Application, UUID(record["id"]))
                if row is None:
                    raise IsolationError(f"recorded application {slot} disappeared")
                if str(row.report_id) != state["reports"][slot]:
                    raise IsolationError(
                        f"recorded application {slot} points at an unexpected report"
                    )
                if normalized_snapshot_hash(row.report_snapshot) != record["snapshotSha256"]:
                    raise IsolationError(f"frozen report snapshot for delivery {slot} changed")
                submitted_events = await session.scalar(
                    select(func.count())
                    .select_from(ApplicationEvent)
                    .where(
                        ApplicationEvent.application_id == row.id,
                        ApplicationEvent.event_type == "submitted",
                    )
                )
                submitted_notices = await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .join(ApplicationEvent, Notification.event_id == ApplicationEvent.id)
                    .where(
                        ApplicationEvent.application_id == row.id,
                        ApplicationEvent.event_type == "submitted",
                        Notification.recipient_id
                        == UUID(state["accounts"]["enterprise"]["userId"]),
                    )
                )
                if submitted_events != 1 or submitted_notices != 1:
                    raise IsolationError(
                        f"delivery {slot} must keep exactly one submitted event and one "
                        "enterprise notification; a replay would duplicate them"
                    )
                applications[slot] = {
                    "id": record["id"],
                    "student": record["student"],
                    "status": row.status,
                }
        # Each enterprise board must expose exactly the non-withdrawn recorded
        # deliveries for that job (job A carries both A and A2), order not assumed.
        job_slots_by_job = {"A": ("A", "A2"), "B": ("B",)}
        for job_slot, job_key in {"A": "jobIdA", "B": "jobIdB"}.items():
            board_ids = {
                item["id"]
                for item in _payload(
                    await enterprise_client.get(
                        f"/jobs/{state['enterprise'][job_key]}/applications"
                    )
                )
            }
            expected_ids = {
                state["applications"][slot]["id"]
                for slot in job_slots_by_job[job_slot]
                if applications[slot]["status"] != "withdrawn"
            }
            if board_ids != expected_ids:
                raise IsolationError(
                    f"enterprise board for job {job_slot} does not match the recorded "
                    "non-withdrawn deliveries"
                )
            for record in applications.values():
                if record["id"] in board_ids:
                    record["enterpriseBoardVisible"] = True
    for slot, record in applications.items():
        record.setdefault("enterpriseBoardVisible", False)
        record["snapshotSha256"] = state["applications"][slot]["snapshotSha256"]
    return {
        "runId": state["runId"],
        "credentialsStateFile": "<written next to the run state; never printed>",
        "jobs": {"A": state["enterprise"]["jobIdA"], "B": state["enterprise"]["jobIdB"]},
        "reports": {slot: state["reports"][slot] for slot in ("A", "B", "A2")},
        "materials": {
            key: state["materials"][key]["resumeVersionId"] for key in ("student", "studentA2")
        },
        "applications": applications,
        "withdrawnRestored": False,
    }


async def seed_fixture(
    client_factory: Callable[[], httpx.AsyncClient],
    session_factory: async_sessionmaker,
    *,
    run_id: str,
    state_path: Path,
    storage_dir: Path,
    verify_only: bool = False,
) -> dict:
    run_id = guard_run_id(run_id)
    state_path = Path(state_path)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("runId") != run_id:
            raise IsolationError("state file belongs to a different run id")
        result = await _verify_fixture(client_factory, session_factory, state)
        result["mode"] = "verified"
        return result
    if verify_only:
        raise IsolationError(f"no fixture state for run id {run_id}; nothing to verify")
    return await _create_fixture(
        client_factory,
        session_factory,
        run_id=run_id,
        state_path=state_path,
        storage_dir=storage_dir,
    )


async def create_database(database_url: str, run_id: str) -> bool:
    """Create ``cp_e2e_<run-id>`` on the loopback server.

    Review-gated: ZCode must not execute this; Codex runs it through Start-E2E.ps1
    after the isolation review. The connection string is never printed.
    """
    name = assert_run_database(guard_database_url(database_url), run_id)
    parts = urlsplit(database_url)
    maintenance = urlunsplit(
        (parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment)
    )
    import asyncpg

    connection = await asyncpg.connect(
        maintenance.replace(f"{POSTGRESQL_SCHEME}://", "postgresql://", 1)
    )
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if exists:
            return False
        await connection.execute(f'CREATE DATABASE "{name}"')
        return True
    finally:
        # asyncpg.Connection has close(), not aclose(); a wrong attribute here
        # would fail exactly when the guarded branch is finally exercised.
        await connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed or verify the isolated E2E fixture")
    parser.add_argument("--run-id", required=True, help="fixture run id, e.g. e2e-card01")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--database-url", default=None, help="defaults to E2E_DATABASE_URL; never printed"
    )
    parser.add_argument(
        "--storage-dir",
        default=None,
        help="defaults to E2E_STORAGE_DIR; must match the backend STORAGE_BASE_DIR",
    )
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--manifest-dir", default=str(DEFAULT_MANIFEST_DIR))
    parser.add_argument(
        "--verify-only", action="store_true", help="verify the existing fixture; never create"
    )
    parser.add_argument(
        "--create-database",
        action="store_true",
        help="review-gated: create cp_e2e_<run-id> on the loopback server, then exit",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    database_url = args.database_url or os.environ.get("E2E_DATABASE_URL", "")
    storage_dir = args.storage_dir or os.environ.get("E2E_STORAGE_DIR", "")
    if not database_url:
        print(
            "E2E_DATABASE_URL (or --database-url) is required; it is read from the "
            "environment and never printed",
            file=sys.stderr,
        )
        return 2
    # Every refusal below happens before the first HTTP request or database connect.
    run_id = guard_run_id(args.run_id)
    database_name = assert_run_database(guard_database_url(database_url), run_id)
    base_url = guard_base_url(args.base_url)
    if args.create_database:
        created = await create_database(database_url, run_id)
        print(f"database {database_name}: {'created' if created else 'already exists'}")
        return 0
    if not storage_dir:
        print("E2E_STORAGE_DIR (or --storage-dir) is required for seeding", file=sys.stderr)
        return 2
    manifest = load_startup_manifest(Path(args.manifest_dir) / f"processes-{run_id}.json")
    verify_startup_manifest(
        manifest,
        run_id=run_id,
        database_name=database_name,
        storage_dir=Path(storage_dir),
        backend_port=E2E_BACKEND_PORT,
    )
    engine = create_async_engine(database_url, hide_parameters=True, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    state_path = Path(args.state_dir) / f"{run_id}.json"

    def client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=base_url, timeout=30, trust_env=False)

    try:
        result = await seed_fixture(
            client_factory,
            factory,
            run_id=run_id,
            state_path=state_path,
            storage_dir=Path(storage_dir),
            verify_only=args.verify_only,
        )
    finally:
        await engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["mode"] == "verified":
        withdrawn = [
            slot
            for slot, record in result["applications"].items()
            if record["status"] == "withdrawn"
        ]
        if withdrawn:
            print(
                f"withdrawn deliveries remain withdrawn and were not restored: "
                f"{', '.join(withdrawn)}; use a new run id for a fresh fixture"
            )
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(_async_main(args))
    except IsolationError as exc:
        print(f"ISOLATION REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
