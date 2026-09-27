"""Bounded multi-direction planning: three enterprise drafts and one student plan.

Default prints the plan only. Live mode makes four one-attempt official
DeepSeek calls through real ASGI routes and an isolated PostgreSQL schema:
one draft per direction, then a single student plan whose shortlist covers
three different job categories. Only generated synthetic accounts, jobs,
resume and code are used; the generated schema is dropped afterwards.
This is API persistence acceptance, not browser interaction, and no raw
model record is committed to git.
"""

import argparse
import asyncio
import hashlib
import io
import json
import secrets
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.agents.provider import EVIDENCE_PROMPT_VERSION, _redact_external_value
from app.models.analysis import AiUsageLog, AnalysisTask
from app.schemas.analysis import CareerPlanAnalysis, JobRecommendationView
from app.services.career_planning import PLAN_VERSION, _planning_input, validate_plan
from evals.verify_two_sided_api import data, isolated_api, wait_upload

SYNTHETIC_SECRET = "synthetic-not-real-credential-tail"
APP_CODE = (
    "from fastapi import FastAPI, HTTPException\n\n"
    "app = FastAPI()\n\n\n"
    '@app.get("/health")\n'
    'def health(name: str, api_key: str = "' + SYNTHETIC_SECRET + '"):\n'
    "    if not name.strip():\n"
    '        raise HTTPException(status_code=400, detail="name required")\n'
    '    return {"status": "ok", "name": name.strip()}\n'
)
ORDERS_SQL = (
    "CREATE TABLE orders (\n"
    "    order_id INTEGER PRIMARY KEY,\n"
    "    city VARCHAR(64) NOT NULL,\n"
    "    amount NUMERIC(12, 2) NOT NULL,\n"
    "    created_at TIMESTAMP NOT NULL\n"
    ");\n\n"
    "SELECT city, SUM(amount) AS total_amount, COUNT(*) AS order_count\n"
    "FROM orders\n"
    "WHERE amount > 0\n"
    "GROUP BY city\n"
    "ORDER BY total_amount DESC;\n"
)
TEST_CODE = (
    "import pytest\n\n\n"
    '@pytest.mark.parametrize("raw_name,expected_status", [("", 400), ("ada", 200)])\n'
    "def test_health_status(raw_name, expected_status):\n"
    "    response = call_health(raw_name)\n"
    '    assert response["status"] == expected_status\n\n\n'
    "def test_order_amount_rejected():\n"
    "    with pytest.raises(ValueError):\n"
    "        validate_order_amount(-5)\n"
)
CASE_FILES = {"app.py": APP_CODE, "orders.sql": ORDERS_SQL, "test_api.py": TEST_CODE}
DIRECTIONS = [
    {
        "key": "backend-fastapi",
        "category": "software",
        "title": "合成多方向后端实习岗位",
        "description": (
            "合成后端实习岗位：要求使用 Python 和 FastAPI 编写查询接口，包含输入校验"
            "与错误响应；提供异常请求的处理代码。\n"
            '演示注记，不是岗位要求：PASSWORD="' + SYNTHETIC_SECRET + '"'
        ),
    },
    {
        "key": "sql-analysis",
        "category": "data_analysis",
        "title": "合成多方向数据分析实习岗位",
        "description": (
            "合成数据分析实习岗位：要求使用 SQL 编写订单数据的分组统计查询；提供订单表"
            "结构定义并汇总各城市金额。\n"
            '演示注记，不是岗位要求：TOKEN="' + SYNTHETIC_SECRET + '"'
        ),
    },
    {
        "key": "test-ops",
        "category": "operations",
        "title": "合成多方向测试实习岗位",
        "description": (
            "合成测试实习岗位：要求使用 Python 和 pytest 为查询接口编写自动化测试与断言；"
            "覆盖参数校验的异常用例。\n"
            '演示注记，不是岗位要求：KEY="' + SYNTHETIC_SECRET + '"'
        ),
    },
]
JOB_REQUIREMENT_KEYS = (
    "rawText",
    "skillName",
    "weight",
    "isRequired",
    "sourceQuote",
    "sourceStart",
    "sourceEnd",
)


def direction_sources_exact(plan, version_id):
    hashes = {
        name: hashlib.sha256(content.encode()).hexdigest()
        for name, content in CASE_FILES.items()
    }
    prefix = version_id + "/"
    seen = 0
    for job in plan["recommendations"]:
        for evidence in job["evidence"]:
            seen += 1
            path = evidence["filePath"]
            if not path.startswith(prefix):
                return False
            name = path[len(prefix) :]
            lines = CASE_FILES[name].splitlines()
            start, end = evidence["lineStart"], evidence["lineEnd"]
            if (
                name not in hashes
                or evidence["projectVersionId"] != version_id
                or evidence["contentHash"] != hashes[name]
                or not 1 <= start <= end <= len(lines)
                or evidence["snippet"] != "\n".join(lines[start - 1 : end])[:900]
            ):
                return False
    return seen > 0


def evaluate_direction_checks(record):
    directions = record["directions"]
    plan = record["plan"]
    advice = (plan.get("aiPlan") or {}).get("advice", [])
    by_job = {item["jobId"]: item for item in plan["recommendations"]}
    allowed = {key: {e["citationId"] for e in item["evidence"]} for key, item in by_job.items()}
    logs = record["usage"]
    validated = (
        plan.get("aiStatus") == "validated"
        and not plan.get("aiFallbackUsed")
        and plan.get("aiModel") == "deepseek-flash"
        and bool(advice)
    )
    issues = plan.get("aiValidationIssues") or []
    conflict_auditable = (
        plan.get("aiStatus") == "visible_code_fact_conflict"
        and not plan.get("aiPlan")
        and bool(issues)
        and bool(issues[0].get("rejectedClaim"))
    )
    checks = {
        "consentAndRoleRejected": record["deniedStatuses"] == [422, 403, 403, 422],
        "draftsUnconfirmedAndUnpublished": all(
            direction["draft"]["confirmed"] is False for direction in directions
        )
        and record["jobsAfterDrafts"] == 0
        and all(direction["createdStatus"] == "draft" for direction in directions),
        "draftQuotesExact": all(
            bool(direction["draft"]["requirements"])
            and all(
                direction["description"][item["sourceStart"] : item["sourceEnd"]]
                == item["sourceQuote"]
                for item in direction["draft"]["requirements"]
            )
            for direction in directions
        ),
        "enterpriseVerificationGuidance": all(
            item["evidenceRequest"] and item["verificationQuestion"] and item["weightReason"]
            for direction in directions
            for item in direction["draft"]["requirements"]
        ),
        "publishedRequirementsPreserved": all(
            direction["job"]["status"] == "published"
            and direction["jobReloaded"] == direction["job"]
            and {
                (item["sourceQuote"], item["sourceStart"], item["sourceEnd"])
                for item in direction["job"]["requirements"]
            }
            == {
                (item["sourceQuote"], item["sourceStart"], item["sourceEnd"])
                for item in direction["draft"]["requirements"]
            }
            for direction in directions
        ),
        "shortlistCoversThreeCategories": {
            item["category"] for item in plan["recommendations"]
        }
        == {direction["category"] for direction in directions},
        "exactSyntheticSources": record["planEvidenceExact"],
        "onlySyntheticMaterials": {
            (material["kind"], material["id"]) for material in plan["materials"]
        }
        == {("resume", record["resumeVersionId"]), ("project", record["projectVersionId"])},
        "planReloadStable": record["planReloaded"] == plan,
        "ownerIsolation": record["foreignTaskStatuses"] == [404, 404, 404, 404]
        and record["enterpriseLatestPlan"] is None,
        "exactlyFourOfficialUsageRows": len(logs) == 4
        and Counter(log["taskType"] for log in logs) == {"job_draft": 3, "career_plan": 1}
        and all(
            log["model"] == "deepseek-flash"
            and log["provider"] == "deepseek"
            and log["inputTokens"] > 0
            and log["outputTokens"] > 0
            for log in logs
        ),
        "textCredentialAbsentFromPreparedContexts": record["preparedContextsSafe"],
        "studentAiValidated": validated,
        "conflictRejectedClaimAuditable": conflict_auditable,
    }
    if validated:
        consistent = False
        try:
            validate_plan(
                CareerPlanAnalysis.model_validate(plan["aiPlan"]),
                [JobRecommendationView.model_validate(job) for job in plan["recommendations"]],
            )
            consistent = True
        except ValueError:
            pass
        checks.update(
            {
                "adviceCoversAllDirections": {item["jobId"] for item in advice}
                == set(by_job),
                "citationsStayWithinOwnJob": all(
                    set(item["citationIds"]).issubset(allowed[item["jobId"]])
                    and len(item["citationIds"]) == len(set(item["citationIds"]))
                    and (bool(item["citationIds"]) or not allowed[item["jobId"]])
                    for item in advice
                ),
                "actionableTasksPerDirection": all(
                    bool(item["taskPlan"])
                    and item["taskPlan"]["deliverable"]
                    and item["taskPlan"]["steps"]
                    and item["taskPlan"]["acceptanceChecks"]
                    for item in advice
                ),
                "visibleChecksConsistent": consistent,
            }
        )
    return checks, validated, conflict_auditable


async def run_directions_case(record):
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
                            "displayName": "合成多方向验收身份",
                            "role": role,
                        },
                    )
                )["user"]

            enterprise = await register(employer, "enterprise")
            owner = await register(student, "student")
            organization = data(
                await employer.post("/api/v1/enterprises", json={"name": "合成多方向验收企业"})
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
            project = data(
                await student.post("/api/v1/projects", json={"name": "合成多方向代码作品"})
            )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, content in CASE_FILES.items():
                    archive.writestr(name, content)
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
            record["stage"] = "permission_gates"
            record["deniedStatuses"] = [
                (
                    await employer.post(
                        "/api/v1/jobs/ai-draft",
                        json={
                            "description": record["directions"][0]["description"],
                            "externalAiConsent": False,
                        },
                    )
                ).status_code,
                (
                    await student.post(
                        "/api/v1/jobs/ai-draft",
                        json={
                            "description": record["directions"][0]["description"],
                            "externalAiConsent": True,
                        },
                    )
                ).status_code,
                (await employer.post("/api/v1/career-plans", json=selection)).status_code,
                (
                    await student.post(
                        "/api/v1/career-plans", json={**selection, "externalAiConsent": False}
                    )
                ).status_code,
            ]
            assert record["deniedStatuses"] == [422, 403, 403, 422]
            record["stage"] = "enterprise_drafts"
            for direction in record["directions"]:
                direction["draft"] = data(
                    await employer.post(
                        "/api/v1/jobs/ai-draft",
                        json={
                            "description": direction["description"],
                            "externalAiConsent": True,
                        },
                    )
                )
            record["jobsAfterDrafts"] = data(await employer.get("/api/v1/jobs/mine"))["total"]
            for direction in record["directions"]:
                job = data(
                    await employer.post(
                        "/api/v1/jobs",
                        json={
                            "enterpriseId": organization["id"],
                            "title": direction["title"],
                            "companyName": organization["name"],
                            "description": direction["description"],
                            "status": "draft",
                            "category": direction["category"],
                            "city": "深圳",
                            "employmentType": "internship",
                            "requirements": [
                                {key: item[key] for key in JOB_REQUIREMENT_KEYS}
                                for item in direction["draft"]["requirements"]
                            ],
                        },
                    )
                )
                direction["createdStatus"] = job["status"]
                direction["job"] = data(
                    await employer.patch(f"/api/v1/jobs/{job['id']}", json={"status": "published"})
                )
                direction["jobReloaded"] = data(await employer.get(f"/api/v1/jobs/{job['id']}"))
            record["stage"] = "student_plan"
            plan = data(await student.post("/api/v1/career-plans", json=selection))
            record["plan"] = plan
            record["planReloaded"] = data(await student.get("/api/v1/career-plans/latest"))
            record["planEvidenceExact"] = direction_sources_exact(plan, version["versionId"])
            record["directionEvidenceCounts"] = {}
            for direction in record["directions"]:
                matched = [
                    item["evidence"]
                    for item in plan["recommendations"]
                    if item["category"] == direction["category"]
                ]
                record["directionEvidenceCounts"][direction["category"]] = (
                    len(matched[0]) if matched else 0
                )
            planning = _planning_input(
                [JobRecommendationView.model_validate(job) for job in plan["recommendations"]],
                [],
            )
            prepared_contexts = [
                {"description": direction["description"]}
                for direction in record["directions"]
            ]
            prepared_contexts.append(planning)
            record["preparedContextsSafe"] = all(
                SYNTHETIC_SECRET not in json.dumps(_redact_external_value(item))
                for item in prepared_contexts
            )
            record["rawPreparedContextContainsCredential"] = {
                "enterpriseDrafts": [
                    SYNTHETIC_SECRET in direction["description"]
                    for direction in record["directions"]
                ],
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
                plan_task = next(
                    task
                    for task in rows
                    if task.task_type == "career_plan"
                    and str(task.created_by) == owner["id"]
                )
                assert str(plan_task.id) == plan["planId"]
                draft_tasks = [
                    task
                    for task in rows
                    if task.task_type == "job_draft"
                    and str(task.created_by) == enterprise["id"]
                ]
                assert len(draft_tasks) == len(record["directions"])
                record["planTaskId"] = str(plan_task.id)
                record["draftTaskIds"] = [str(task.id) for task in draft_tasks]
                logs = list(
                    await session.scalars(
                        select(AiUsageLog).where(
                            AiUsageLog.analysis_task_id.in_([task.id for task in rows])
                        )
                    )
                )
                by_task = {task.id: task.task_type for task in rows}
                record["usage"] = [
                    {
                        "taskType": by_task[log.analysis_task_id],
                        "model": log.model,
                        "provider": log.unit_price_snapshot.get("provider"),
                        "inputTokens": log.input_tokens,
                        "outputTokens": log.output_tokens,
                        "cacheHitTokens": log.cache_hit_tokens,
                        "latencyMs": log.latency_ms,
                    }
                    for log in logs
                ]
            foreign_status = [
                (
                    await employer.get("/api/v1/analysis-tasks/" + record["planTaskId"])
                ).status_code
            ]
            for task_id in record["draftTaskIds"]:
                foreign_status.append(
                    (await student.get("/api/v1/analysis-tasks/" + task_id)).status_code
                )
            record["foreignTaskStatuses"] = foreign_status
            record["enterpriseLatestPlan"] = data(
                await employer.get("/api/v1/career-plans/latest")
            )
            record["checks"], validated, conflict_auditable = evaluate_direction_checks(record)
            record["aiStatus"] = record["plan"].get("aiStatus")
            record["aiValidationIssues"] = record["plan"].get("aiValidationIssues") or []
            record["outcome"] = (
                "validated"
                if validated
                else "conflict_rejected"
                if conflict_auditable
                else record["plan"].get("aiStatus") or "unknown"
            )
            record["passed"] = all(
                value
                for key, value in record["checks"].items()
                if key not in {"studentAiValidated", "conflictRejectedClaimAuditable"}
            ) and (validated or conflict_auditable)
            record["stage"] = "complete"
    record["passed"] = record["passed"] and record.get("temporarySchemaRemoved", False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.live and not args.allow_paid:
        parser.error("Live verification requires --allow-paid")
    if not args.live:
        print("Plan only; --live --allow-paid makes four one-attempt synthetic model calls.")
        return 0
    if args.output.exists():
        parser.error("Use a new output; do not overwrite acceptance evidence")
    record = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "promptVersion": EVIDENCE_PROMPT_VERSION,
        "planVersion": PLAN_VERSION,
        "scope": "Real ASGI routes, isolated PostgreSQL, synthetic material, official DeepSeek",
        "directions": [
            {key: direction[key] for key in ("key", "category", "title", "description")}
            for direction in DIRECTIONS
        ],
        "browserClicks": "not_run",
        "billingVerified": False,
        "humanSemanticReview": "pending",
        "passed": False,
    }
    try:
        asyncio.run(run_directions_case(record))
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
                    "outcome",
                    "stage",
                    "temporarySchemaRemoved",
                    "checks",
                    "directionEvidenceCounts",
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
