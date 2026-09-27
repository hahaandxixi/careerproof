"""Explicit bounded DeepSeek calls through real routes and isolated PostgreSQL.

Default: two calls. Frozen-draft reuse: one student call, no enterprise generation.

Only generated accounts, a synthetic job, resume and code are used. The generated
schema is dropped after records are collected; no production rows or user service
are changed. This is ASGI/API persistence acceptance, not browser interaction.
"""

import argparse
import asyncio
import hashlib
import json
import re
import secrets
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.provider import EVIDENCE_PROMPT_VERSION, _redact_external_value
from app.core.config import settings
from app.core.database import Base, get_session
from app.main import create_app
from app.models.analysis import AiUsageLog, AnalysisTask
from app.schemas.analysis import CareerPlanAnalysis, JobRecommendationView
from app.services.career_planning import PLAN_VERSION, _planning_input, validate_plan
from app.services.job_drafting import validate_draft
from evals.verify_deepseek_tool_report import data

SYNTHETIC_SECRET = "synthetic-not-real-credential-tail"
DESCRIPTION = (
    "合成后端实习岗位：要求使用 Python 和 FastAPI 编写查询接口，包含输入校验与错误响应；"
    "提供正常和异常请求的接口测试代码及运行记录。\n"
    '演示注记，不是岗位要求：PASSWORD="' + SYNTHETIC_SECRET + '"'
)
CODE = (
    "from fastapi import FastAPI, HTTPException\napp = FastAPI()\n"
    '@app.get("/health")\ndef health(name: str, api_key: str = "' + SYNTHETIC_SECRET + '"):\n'
    '    if not name.strip():\n        raise HTTPException(400, detail="name required")\n'
    '    return {"status": "ok", "name": name.strip()}\n'
)


# These hashes identify the two preserved, synthetic enterprise acceptance records.
# Arbitrary resumes or enterprise records cannot be replayed through this helper.
_APPROVED_DRAFT_RECORDS = {
    "b9ea0b6aa96113ab22a05bab4988a577b64829f47bf8ede748de7445a9d44fcd",
    "a5382665c8d8c0b6463b0a3576fbde0eae0b2e1f2e851e65b0d656df7d8ad6d1",
}


def load_reusable_draft(path):
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest not in _APPROVED_DRAFT_RECORDS:
        raise ValueError("Only a frozen synthetic enterprise record may be reused")
    saved = json.loads(content)
    draft = saved["draft"]
    if saved["job"]["description"] != DESCRIPTION or draft["model"] != "deepseek-flash":
        raise ValueError("Frozen draft source or model mismatch")
    if draft["confirmed"] is not False:
        raise ValueError("A frozen draft must require confirmation")
    keys = (
        "raw_text",
        "skill_name",
        "weight",
        "is_required",
        "source_quote",
        "evidence_request",
        "verification_question",
        "weight_reason",
    )
    raw = {
        "requirements": [
            {
                key: item["".join([key.split("_")[0], *[p.title() for p in key.split("_")[1:]]])]
                for key in keys
            }
            for item in draft["requirements"]
        ]
    }
    validated = validate_draft(raw, DESCRIPTION, "deepseek-flash", None)
    if not all(
        r.evidence_request and r.verification_question and r.weight_reason
        for r in validated.requirements
    ):
        raise ValueError("Frozen draft lacks verification guidance")
    checked = validated.model_dump(mode="json", by_alias=True)
    if checked["requirements"] != draft["requirements"]:
        raise ValueError("Frozen draft positions no longer match current validation")
    return checked, digest


@asynccontextmanager
async def isolated_api(record):
    from app.api.v1 import analysis as routes
    from app.services import analysis, portfolio

    database_url = settings.database_url
    url = make_url(database_url)
    if url.drivername != "postgresql+asyncpg" or url.host not in {"127.0.0.1", "localhost"}:
        raise ValueError("An explicitly local PostgreSQL is required")
    schema = "cp_eval_" + uuid4().hex
    assert re.fullmatch(r"cp_eval_[0-9a-f]{32}", schema)
    engine = create_async_engine(
        database_url,
        hide_parameters=True,
        connect_args={"server_settings": {"search_path": schema + ",public"}},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    created = False
    bindings = [
        (analysis, "async_session_factory"),
        (portfolio, "async_session_factory"),
        (routes, "async_session_factory"),
    ]
    saved = [(module, name, getattr(module, name)) for module, name in bindings]
    storage, attempts = settings.storage_base_dir, settings.deepseek_max_attempts
    app = create_app()
    try:
        async with engine.begin() as connection:
            await connection.execute(text('CREATE SCHEMA "' + schema + '"'))
        created = True
        record["isolationSchema"] = schema
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, checkfirst=False))
        with tempfile.TemporaryDirectory(prefix="cp-two-sided-") as folder:
            temp_root = Path(folder).resolve()
            assert temp_root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            settings.storage_base_dir = temp_root / "materials"
            # Limits stay unchanged. Only this verifier's transport retries are
            # disabled to bound the test to one request per side.
            settings.deepseek_max_attempts = 1
            for module, name in bindings:
                setattr(module, name, factory)

            async def sessions():
                async with factory() as session:
                    yield session

            app.dependency_overrides[get_session] = sessions
            yield app, factory
    finally:
        if created:
            try:
                async with factory() as session:
                    logs = (
                        await session.execute(
                            select(AiUsageLog, AnalysisTask.task_type).join(
                                AnalysisTask, AiUsageLog.analysis_task_id == AnalysisTask.id
                            )
                        )
                    ).all()
                    record["usage"] = [
                        {
                            "taskType": task_type,
                            "model": log.model,
                            "provider": log.unit_price_snapshot.get("provider"),
                            "inputTokens": log.input_tokens,
                            "outputTokens": log.output_tokens,
                            "cacheHitTokens": log.cache_hit_tokens,
                            "latencyMs": log.latency_ms,
                        }
                        for log, task_type in logs
                    ]
            except Exception as exc:
                record["usageCaptureErrorType"] = type(exc).__name__
                record["passed"] = False
        app.dependency_overrides.clear()
        settings.storage_base_dir, settings.deepseek_max_attempts = storage, attempts
        for module, name, old in saved:
            setattr(module, name, old)
        try:
            if created:
                assert re.fullmatch(r"cp_eval_[0-9a-f]{32}", schema)
                async with engine.begin() as connection:
                    await connection.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
                record["temporarySchemaRemoved"] = True
        finally:
            await engine.dispose()


async def wait_upload(client, task_id):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        task = data(await client.get("/api/v1/analysis-tasks/" + task_id))
        if task["status"] == "completed":
            return
        if task["status"] in {"failed", "cancelled"}:
            raise ValueError("Synthetic material parse failed")
        await asyncio.sleep(0.2)
    raise TimeoutError("Synthetic material parse did not finish")


def plan_sources_exact(plan, version_id):
    digest = hashlib.sha256(CODE.encode()).hexdigest()
    lines, seen = CODE.splitlines(), 0
    for job in plan["recommendations"]:
        for evidence in job["evidence"]:
            start, end = evidence["lineStart"], evidence["lineEnd"]
            if (
                evidence["filePath"] != version_id + "/app.py"
                or evidence["contentHash"] != digest
                or evidence["projectVersionId"] != version_id
                or not 1 <= start <= end <= len(lines)
                or evidence["snippet"] != "\n".join(lines[start - 1 : end])
            ):
                return False
            seen += 1
    return seen > 0


def evaluate_checks(record):
    draft, job, plan = record["draft"], record["job"], record["plan"]
    requirements = draft["requirements"]
    advice = (plan.get("aiPlan") or {}).get("advice", [])
    by_job = {item["jobId"]: item for item in plan["recommendations"]}
    allowed = {key: {e["citationId"] for e in item["evidence"]} for key, item in by_job.items()}
    logs = record["usage"]
    consistent = False
    if plan.get("aiPlan"):
        try:
            validate_plan(
                CareerPlanAnalysis.model_validate(plan["aiPlan"]),
                [JobRecommendationView.model_validate(j) for j in plan["recommendations"]],
            )
            consistent = True
        except ValueError:
            pass
    return {
        "consentAndRoleRejected": record["deniedStatuses"] == [422, 403, 403, 422],
        "noAutomaticPublication": draft["confirmed"] is False
        and record["jobsAfterDraft"] == 0
        and record["createdStatus"] == "draft",
        "draftQuotesExact": bool(requirements)
        and all(
            DESCRIPTION[r["sourceStart"] : r["sourceEnd"]] == r["sourceQuote"] for r in requirements
        ),
        "enterpriseVerificationGuidance": all(
            r["evidenceRequest"] and r["verificationQuestion"] and r["weightReason"]
            for r in requirements
        ),
        "confirmedPublishedSourcePreserved": job["status"] == "published"
        and record["jobReloaded"] == job
        and {(r["sourceQuote"], r["sourceStart"], r["sourceEnd"]) for r in job["requirements"]}
        == {(r["sourceQuote"], r["sourceStart"], r["sourceEnd"]) for r in requirements},
        "exactSyntheticSources": record["planSourcesExact"],
        "visibleChecksConsistent": consistent,
        "studentAiValidated": plan["aiStatus"] == "validated"
        and not plan["aiFallbackUsed"]
        and plan["aiModel"] == "deepseek-flash"
        and bool(advice),
        "onlySyntheticJobAndMaterials": set(by_job) == {job["id"]}
        and {(m["kind"], m["id"]) for m in plan["materials"]}
        == {("resume", record["resumeVersionId"]), ("project", record["projectVersionId"])},
        "citedActionableTasks": {a["jobId"] for a in advice} == set(by_job)
        and all(
            bool(a["taskPlan"])
            and a["taskPlan"]["deliverable"]
            and a["taskPlan"]["steps"]
            and a["taskPlan"]["acceptanceChecks"]
            and set(a["citationIds"]).issubset(allowed[a["jobId"]])
            and len(a["citationIds"]) == len(set(a["citationIds"]))
            and (bool(a["citationIds"]) or not allowed[a["jobId"]])
            for a in advice
        ),
        "planReloadStable": record["planReloaded"] == plan,
        "ownerIsolation": record["foreignTaskStatuses"]
        == ([404] if record.get("enterpriseDraftReused") else [404, 404])
        and record["enterpriseLatestPlan"] is None,
        (
            "exactlyOneOfficialStudentUsageRow"
            if record.get("enterpriseDraftReused")
            else "exactlyTwoOfficialUsageRows"
        ): len(logs) == (1 if record.get("enterpriseDraftReused") else 2)
        and {u["taskType"] for u in logs}
        == (
            {"career_plan"} if record.get("enterpriseDraftReused") else {"career_plan", "job_draft"}
        )
        and all(
            u["model"] == "deepseek-flash"
            and u["provider"] == "deepseek"
            and u["inputTokens"] > 0
            and u["outputTokens"] > 0
            for u in logs
        ),
        "textCredentialAbsentFromPreparedContexts": record["preparedContextsSafe"],
    }


async def run_case(record, reused_draft=None):
    import io
    import zipfile

    record["stage"] = "isolation"
    async with isolated_api(record) as (app, factory):
        transport = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(
                transport=transport, base_url="http://synthetic", timeout=240
            ) as employer,
            httpx.AsyncClient(
                transport=transport, base_url="http://synthetic", timeout=240
            ) as student,
        ):

            async def register(client, role):
                return data(
                    await client.post(
                        "/api/v1/auth/register",
                        json={
                            "email": uuid4().hex + "@example.com",
                            "password": secrets.token_urlsafe(24),
                            "displayName": "合成验收身份",
                            "role": role,
                        },
                    )
                )["user"]

            enterprise = await register(employer, "enterprise")
            owner = await register(student, "student")
            organization = data(
                await employer.post("/api/v1/enterprises", json={"name": "合成API验收企业"})
            )
            resume = data(
                await student.post(
                    "/api/v1/resumes",
                    data={"title": "合成简历"},
                    files={
                        "file": (
                            "synthetic.txt",
                            "合成学生：接触过Python和FastAPI。".encode(),
                            "text/plain",
                        )
                    },
                )
            )
            await wait_upload(student, resume["taskId"])
            record["resumeVersionId"] = resume["versionId"]
            project = data(await student.post("/api/v1/projects", json={"name": "合成代码作品"}))
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("app.py", CODE)
            version = data(
                await student.post(
                    f"/api/v1/projects/{project['id']}/versions",
                    files={"file": ("synthetic.zip", buffer.getvalue(), "application/zip")},
                )
            )
            await wait_upload(student, version["taskId"])
            record["projectVersionId"] = version["versionId"]
            selection = {
                "resumeVersionId": resume["versionId"],
                "projectVersionIds": [version["versionId"]],
                "limit": 3,
                "externalAiConsent": True,
            }
            draft_request = {"description": DESCRIPTION, "externalAiConsent": True}
            record["stage"] = "permission_gates"
            record["deniedStatuses"] = [
                (
                    await employer.post(
                        "/api/v1/jobs/ai-draft", json={**draft_request, "externalAiConsent": False}
                    )
                ).status_code,
                (await student.post("/api/v1/jobs/ai-draft", json=draft_request)).status_code,
                (await employer.post("/api/v1/career-plans", json=selection)).status_code,
                (
                    await student.post(
                        "/api/v1/career-plans", json={**selection, "externalAiConsent": False}
                    )
                ).status_code,
            ]
            assert record["deniedStatuses"] == [422, 403, 403, 422]
            record["stage"] = "enterprise_draft"
            if reused_draft is None:
                draft = data(await employer.post("/api/v1/jobs/ai-draft", json=draft_request))
            else:
                draft, digest = reused_draft
                record["enterpriseDraftReused"] = True
                record["reusedDraftRecordSha256"] = digest
                record["enterpriseGenerationThisRun"] = "not_run"
            record["draft"] = draft
            record["jobsAfterDraft"] = data(await employer.get("/api/v1/jobs/mine"))["total"]
            job = data(
                await employer.post(
                    "/api/v1/jobs",
                    json={
                        "enterpriseId": organization["id"],
                        "title": "合成后端实习岗位",
                        "companyName": organization["name"],
                        "description": DESCRIPTION,
                        "status": "draft",
                        "category": "software",
                        "city": "深圳",
                        "employmentType": "internship",
                        "requirements": [
                            {
                                key: r[key]
                                for key in (
                                    "rawText",
                                    "skillName",
                                    "weight",
                                    "isRequired",
                                    "sourceQuote",
                                    "sourceStart",
                                    "sourceEnd",
                                )
                            }
                            for r in draft["requirements"]
                        ],
                    },
                )
            )
            record["createdStatus"] = job["status"]
            job = data(
                await employer.patch(f"/api/v1/jobs/{job['id']}", json={"status": "published"})
            )
            record["job"] = job
            record["jobReloaded"] = data(await employer.get(f"/api/v1/jobs/{job['id']}"))
            record["stage"] = "student_plan"
            plan = data(await student.post("/api/v1/career-plans", json=selection))
            record["plan"] = plan
            record["planReloaded"] = data(await student.get("/api/v1/career-plans/latest"))
            record["planSourcesExact"] = plan_sources_exact(plan, version["versionId"])
            planning = _planning_input(
                [JobRecommendationView.model_validate(j) for j in plan["recommendations"]], []
            )
            record["preparedContextsSafe"] = all(
                SYNTHETIC_SECRET not in json.dumps(_redact_external_value(v))
                for v in ({"description": DESCRIPTION}, planning)
            )
            record["rawPreparedContextContainsCredential"] = {
                "enterprise": SYNTHETIC_SECRET in DESCRIPTION,
                "student": SYNTHETIC_SECRET in json.dumps(planning),
            }
            record["stage"] = "database_verification"
            async with factory() as session:
                rows = list(
                    await session.scalars(
                        select(AnalysisTask).where(
                            AnalysisTask.task_type.in_(["job_draft", "career_plan"])
                        )
                    )
                )
                draft_task = (
                    next(
                        t
                        for t in rows
                        if t.task_type == "job_draft" and str(t.created_by) == enterprise["id"]
                    )
                    if reused_draft is None
                    else None
                )
                plan_task = next(
                    t
                    for t in rows
                    if t.task_type == "career_plan" and str(t.created_by) == owner["id"]
                )
                assert str(plan_task.id) == plan["planId"]
                logs = list(
                    await session.scalars(
                        select(AiUsageLog).where(
                            AiUsageLog.analysis_task_id.in_([t.id for t in rows])
                        )
                    )
                )
                by_task = {t.id: t.task_type for t in rows}
                record["usage"] = [
                    {
                        "taskType": by_task[u.analysis_task_id],
                        "model": u.model,
                        "provider": u.unit_price_snapshot.get("provider"),
                        "inputTokens": u.input_tokens,
                        "outputTokens": u.output_tokens,
                        "cacheHitTokens": u.cache_hit_tokens,
                        "latencyMs": u.latency_ms,
                    }
                    for u in logs
                ]
                if draft_task is not None:
                    record["draftTaskId"] = str(draft_task.id)
                record["planTaskId"] = str(plan_task.id)
            record["foreignTaskStatuses"] = [
                (await employer.get("/api/v1/analysis-tasks/" + record["planTaskId"])).status_code,
            ]
            if draft_task is not None:
                record["foreignTaskStatuses"].append(
                    (
                        await student.get("/api/v1/analysis-tasks/" + record["draftTaskId"])
                    ).status_code
                )
            record["enterpriseLatestPlan"] = data(await employer.get("/api/v1/career-plans/latest"))
            record["checks"] = evaluate_checks(record)
            record["passed"] = all(record["checks"].values())
            record["stage"] = "complete"
    record["passed"] = record["passed"] and record.get("temporarySchemaRemoved", False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--reuse-draft-record",
        type=Path,
        help="Reuse an approved frozen synthetic draft; only student generation runs",
    )
    args = parser.parse_args()
    if args.live and not args.allow_paid:
        parser.error("Live verification requires --allow-paid")
    if not args.live:
        calls = "one student" if args.reuse_draft_record else "two"
        print(f"Plan only; --live --allow-paid makes {calls} one-attempt synthetic model calls.")
        return 0
    if args.output.exists():
        parser.error("Use a new output; do not overwrite acceptance evidence")
    record = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "planVersion": PLAN_VERSION,
        "scope": "Real ASGI routes, isolated PostgreSQL, synthetic material, official DeepSeek",
        "passed": False,
        "browserClicks": "not_run",
        "billingVerified": False,
        "humanSemanticReview": "pending",
    }
    try:
        if args.reuse_draft_record:
            reused = load_reusable_draft(args.reuse_draft_record)
            asyncio.run(run_case(record, reused))
        else:
            asyncio.run(run_case(record))
    except Exception as exc:
        record["passed"] = False
        record["errorType"] = type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                key: record.get(key)
                for key in (
                    "passed",
                    "stage",
                    "temporarySchemaRemoved",
                    "checks",
                    "usage",
                    "errorType",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
