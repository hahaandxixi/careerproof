"""Explicitly paid local DeepSeek image concurrency/cache verification.

Uploads a fresh synthetic image. No quota changes, retries, saved-data rewrites,
or credential export. Two simultaneous HTTP requests may consume up to two model
calls if deduplication is broken; success requires one saved observation/usage.
"""

import argparse
import asyncio
import hashlib
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.agents.vision_provider import VISION_PROMPT_VERSION
from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.models.analysis import AiUsageLog, AnalysisTask
from app.models.portfolio import ProjectVersion
from evals.demo_credentials import get_demo_credentials
from evals.verify_deepseek_tool_report import BASE, data, wait
from evals.verify_visual_report import create_fixture


async def _scoped_rows(owner_id, version_id):
    engine.echo = False
    async with async_session_factory() as session:
        version = await session.get(ProjectVersion, UUID(version_id))
        tasks = list(
            await session.scalars(
                select(AnalysisTask).where(
                    AnalysisTask.created_by == UUID(owner_id),
                    AnalysisTask.task_type == "visual_review",
                    AnalysisTask.input_snapshot["projectVersionId"].as_string() == version_id,
                )
            )
        )
        ids = [task.id for task in tasks]
        usage = (
            list(
                await session.scalars(
                    select(AiUsageLog).where(AiUsageLog.analysis_task_id.in_(ids))
                )
            )
            if ids
            else []
        )
        return {
            "sourceHash": version.content_hash if version else None,
            "tasks": [
                {
                    "id": str(t.id),
                    "status": t.status.value,
                    "sourceHash": t.input_snapshot.get("sourceHash"),
                    "promptVersion": t.input_snapshot.get("promptVersion"),
                }
                for t in tasks
            ],
            "usage": [
                {
                    "taskId": str(u.analysis_task_id),
                    "model": u.model,
                    "provider": u.unit_price_snapshot.get("provider"),
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "cache_hit_tokens": u.cache_hit_tokens,
                    "latency_ms": u.latency_ms,
                }
                for u in usage
            ],
        }


async def scoped_rows(owner_id, version_id):
    # asyncio.run creates separate loops; do not reuse asyncpg pooled connections
    # across them. Dispose only this verifier process's read-only DB engine.
    try:
        return await _scoped_rows(owner_id, version_id)
    finally:
        await engine.dispose()


async def concurrent_requests(cookies, version_id):
    gate = asyncio.Event()
    ready = [asyncio.Event(), asyncio.Event()]

    async def invoke(index):
        async with httpx.AsyncClient(
            base_url=BASE, cookies=cookies, timeout=240, trust_env=False
        ) as client:
            ready[index].set()
            await gate.wait()
            start = time.perf_counter()
            try:
                response = await client.post(
                    f"/project-versions/{version_id}/visual-review",
                    json={"externalImageConsent": True},
                )
                return {
                    "httpStatus": response.status_code,
                    "started": start,
                    "finished": time.perf_counter(),
                    "result": data(response) if response.is_success else None,
                }
            except Exception as exc:
                return {
                    "errorType": type(exc).__name__,
                    "started": start,
                    "finished": time.perf_counter(),
                    "result": None,
                }

    tasks = [asyncio.create_task(invoke(i)) for i in range(2)]
    try:
        await asyncio.gather(*(event.wait() for event in ready))
        gate.set()
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def evaluate_checks(record):
    responses = record["responses"]
    before, after = record["before"], record["after"]
    results = [r.get("result") for r in responses]
    completed = len(results) == 2 and all(
        r.get("httpStatus") == 200 and result and result.get("status") == "completed"
        for r, result in zip(responses, results, strict=True)
    )
    saved = results[0] if completed else {}
    usage = saved.get("usage") or {}
    tasks, logs = after["tasks"], after["usage"]
    single = len(tasks) == len(logs) == 1
    checks = {
        "freshUncachedVersion": not before["tasks"]
        and not before["usage"]
        and record["cacheBefore"] is None,
        "httpIntervalsOverlap": len(responses) == 2
        and max(r["started"] for r in responses) < min(r["finished"] for r in responses),
        "bothCompleted": bool(completed),
        "identicalPersistedResult": bool(
            completed and results[0] == results[1] and saved == record["reloaded"]
        ),
        "currentSourceExact": completed
        and before["sourceHash"]
        == after["sourceHash"]
        == record["fixtureHash"]
        == saved.get("sourceHash")
        and saved.get("projectVersionId") == record["projectVersionId"]
        and saved.get("promptVersion") == VISION_PROMPT_VERSION,
        "oneObservationAndUsage": single
        and tasks[0]["id"] == saved.get("id")
        and tasks[0]["status"] == "completed"
        and tasks[0]["sourceHash"] == record["fixtureHash"]
        and tasks[0]["promptVersion"] == VISION_PROMPT_VERSION
        and logs[0]["taskId"] == saved.get("id"),
        "officialDeepSeekUsage": bool(
            single
            and saved.get("model") == "deepseek-flash"
            and logs[0]["model"] == "deepseek-flash"
            and logs[0]["provider"] == "deepseek"
            and usage.get("input_tokens", 0) > 0
            and usage.get("output_tokens", 0) > 0
            and all(
                logs[0][key] == usage.get(key)
                for key in ("input_tokens", "output_tokens", "cache_hit_tokens", "latency_ms")
            )
        ),
        "enterpriseDenied": record["enterpriseStatuses"] == [404, 404, 404],
    }
    return checks


def run_case(record):
    endpoint = urlparse(BASE)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only a local API is allowed")
    if make_url(settings.database_url).host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only the local PostgreSQL is allowed")
    with tempfile.TemporaryDirectory(prefix="cp-visual-concurrency-") as folder:
        fixture = Path(folder) / "synthetic-concurrency.png"
        create_fixture(fixture)
        with Image.open(fixture) as original:
            image = original.copy()
        ImageDraw.Draw(image).text(
            (50, 495), "Synthetic concurrency " + uuid4().hex, fill="#0f172a"
        )
        image.save(fixture)
        raw = fixture.read_bytes()
        record["fixtureHash"] = hashlib.sha256(raw).hexdigest()
        with httpx.Client(base_url=BASE, timeout=240, trust_env=False) as client:
            record["stage"] = "upload"
            owner = data(client.post("/auth/login", json=get_demo_credentials("student")))["user"]
            project = data(
                client.post("/projects", json={"name": "合成视觉并发 " + uuid4().hex[:8]})
            )
            record["projectId"] = project["id"]
            upload = data(
                client.post(
                    f"/projects/{project['id']}/versions",
                    files={"file": (fixture.name, raw, "image/png")},
                )
            )
            record["projectVersionId"] = upload["versionId"]
            record["uploadTaskId"] = upload["taskId"]
            wait(client, upload["taskId"], timeout=120)
            version_id = upload["versionId"]
            record["cacheBefore"] = data(
                client.get(f"/project-versions/{version_id}/visual-review")
            )
            record["before"] = asyncio.run(scoped_rows(owner["id"], version_id))
            if record["cacheBefore"] is not None or record["before"]["tasks"]:
                raise ValueError("A new uncached version is required")
            record["stage"] = "concurrent_requests"
            record["responses"] = asyncio.run(concurrent_requests(client.cookies, version_id))
            record["stage"] = "saved_result"
            record["reloaded"] = data(client.get(f"/project-versions/{version_id}/visual-review"))
            record["after"] = asyncio.run(scoped_rows(owner["id"], version_id))
            record["stage"] = "permission_check"
            with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as enterprise:
                data(enterprise.post("/auth/login", json=get_demo_credentials("enterprise")))
                result_id = (record["reloaded"] or {}).get("id")
                record["enterpriseStatuses"] = [
                    enterprise.get(f"/project-versions/{version_id}/image").status_code,
                    enterprise.get(f"/project-versions/{version_id}/visual-review").status_code,
                    enterprise.patch(
                        f"/visual-reviews/{result_id}", json={"status": "accepted", "note": ""}
                    ).status_code
                    if result_id
                    else None,
                ]
            record["checks"] = evaluate_checks(record)
            record["passed"] = all(record["checks"].values())
            record["stage"] = "complete"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.live and not args.allow_paid:
        parser.error("Live concurrency verification requires --allow-paid")
    if not args.live:
        print("Plan only; --live --allow-paid may consume at most two one-attempt vision calls.")
        return 0
    if args.output.exists():
        parser.error("Use a new output; never overwrite an acceptance record")
    record = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "passed": False,
        "promptVersion": VISION_PROMPT_VERSION,
        "billingVerified": False,
        "humanSemanticReview": "pending",
        "browserClicks": "not_run",
        "boundary": (
            "HTTP/cache/usage check; no PostgreSQL lock observer or semantic certification."
        ),
    }
    try:
        run_case(record)
    except Exception as exc:
        record["errorType"] = type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                key: record.get(key)
                for key in ("passed", "stage", "projectVersionId", "checks", "errorType")
            },
            ensure_ascii=False,
        )
    )
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
