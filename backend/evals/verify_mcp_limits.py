"""Opt-in local PostgreSQL MCP concurrency checks; no external model calls.

Only reads an existing synthetic demo report. Grants are ephemeral and revoked
in finally blocks; tokens, headers and tool results are never saved.
"""

import argparse
import asyncio
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import httpx
import jwt
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.models.audit import AuditLog
from evals.demo_credentials import get_demo_credentials
from evals.verify_deepseek_tool_report import BASE, data


async def checks(report_id):
    engine.echo = False
    if engine.dialect.name != "postgresql":
        raise ValueError("This verification requires local PostgreSQL row locks")
    endpoint = urlparse(BASE)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("This verification only accepts a local HTTP API")
    outcomes = {"externalModelCalls": 0, "reportId": str(report_id), "grants": []}
    async with httpx.AsyncClient(base_url=BASE, timeout=15, trust_env=False) as client:
        data(await client.post("/auth/login", json=get_demo_credentials("student")))
        saved = data(await client.get(f"/match-reports/{report_id}"))
        if saved["candidateName"] != "演示学生" or "合成" not in saved["jobTitle"]:
            raise ValueError("Select an existing synthetic demo student's report")

        async def grant():
            result = data(
                await client.post(
                    "/mcp-tools/grants",
                    json={
                        "report_ids": [str(report_id)],
                        "external_client_consent": True,
                    },
                )
            )
            outcomes["grants"].append({"id": result["grantId"], "revoked": False})
            return result

        async def revoke(item):
            response = await client.delete(f"/mcp-tools/grants/{item['grantId']}")
            response.raise_for_status()
            next(g for g in outcomes["grants"] if g["id"] == item["grantId"])["revoked"] = True

        call = {"tool": "get_report_summary", "arguments": {"report_id": str(report_id)}}
        limited = await grant()
        try:
            semaphore = asyncio.Semaphore(8)

            async def invoke():
                async with semaphore:
                    response = await client.post(
                        "/mcp-tools/invoke",
                        json=call,
                        headers={"Authorization": f"Bearer {limited['token']}"},
                    )
                    return response.status_code

            started = time.monotonic()
            statuses = Counter(await asyncio.gather(*(invoke() for _ in range(48))))
            async with async_session_factory() as session:
                audit_rows = list(
                    await session.scalars(
                        select(AuditLog).where(
                            AuditLog.action == "mcp.call",
                            AuditLog.resource_id == limited["grantId"],
                        )
                    )
                )
            audit_statuses = Counter(row.details["status"] for row in audit_rows)
            outcomes["concurrency"] = {
                "requests": 48,
                "concurrency": 8,
                "httpStatuses": dict(statuses),
                "auditStatuses": dict(audit_statuses),
                "elapsedMs": round((time.monotonic() - started) * 1000),
                "passed": statuses == {200: 40, 429: 8}
                and audit_statuses == {"completed": 40, "limit_rejected": 8},
            }
        finally:
            await revoke(limited)

        expiring = await grant()
        try:
            claims = jwt.decode(
                expiring["token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
            # Narrow the existing grant's token deadline only, never its scope.
            claims["exp"] = int(datetime.now(UTC).timestamp()) + 4
            token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
            observed_wait = False
            pending = None
            async with async_session_factory() as session, session.begin():
                await session.scalar(
                    select(AuditLog)
                    .where(
                        AuditLog.action == "mcp.grant",
                        AuditLog.resource_id == expiring["grantId"],
                    )
                    .with_for_update()
                )
                pending = asyncio.create_task(
                    client.post(
                        "/mcp-tools/invoke",
                        json=call,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                )
                while datetime.now(UTC).timestamp() < claims["exp"] + 0.2:
                    # Query text can be stale with reused prepared statements;
                    # identify the actual blocker instead of matching SQL text.
                    waiting = await session.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                            "WHERE pid <> pg_backend_pid() AND wait_event_type = 'Lock' "
                            "AND wait_event = 'transactionid' "
                            "AND pg_blocking_pids(pid) @> ARRAY[pg_backend_pid()])"
                        )
                    )
                    observed_wait |= bool(waiting)
                    await asyncio.sleep(0.1)
            response = await pending
            async with async_session_factory() as session:
                rows = list(
                    await session.scalars(
                        select(AuditLog).where(
                            AuditLog.action == "mcp.call",
                            AuditLog.resource_id == expiring["grantId"],
                        )
                    )
                )
            expired_audit = len(rows) == 1 and rows[0].details.get("status") == "expired"
            result_absent = "result" not in (response.json().get("data") or {})
            outcomes["expiresWhileWaiting"] = {
                "lockWaitProbe": "transactionid_blocked_by_this_session_v2",
                "postgresLockWaitObserved": observed_wait,
                "httpStatus": response.status_code,
                "expiredAudit": expired_audit,
                "resultAbsent": result_absent,
                "passed": observed_wait
                and response.status_code == 401
                and expired_audit
                and result_absent,
            }
        finally:
            await revoke(expiring)
    outcomes["passed"] = (
        outcomes["concurrency"]["passed"]
        and outcomes["expiresWhileWaiting"]["passed"]
        and all(g["revoked"] for g in outcomes["grants"])
    )
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report-id", type=UUID)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.run:
        print("No calls made. --run reads a local synthetic report and tests temporary MCP grants.")
        return 0
    if not args.report_id:
        parser.error("--report-id is required")
    output = args.output or Path(__file__).with_name(
        f"mcp-limits-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    if output.exists():
        parser.error("Use a new output path; existing evidence is never overwritten")
    try:
        result = asyncio.run(checks(args.report_id))
    except Exception as exc:
        result = {
            "passed": False,
            "externalModelCalls": 0,
            "errorType": type(exc).__name__,
            "cleanup": "Revocation attempted in finally; inspect local MCP audit if unsuccessful",
        }
    result["generatedAt"] = datetime.now(UTC).isoformat()
    with output.open("x", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps({"output": str(output), **result}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
