"""Official SDK stdio -> loopback HTTP -> real authorization/database routes.

Synthetic saved reports only; no inference, production database or user uploads.
SQLite proves protocol/authorization plumbing, not PostgreSQL lock concurrency.
"""

import asyncio
import hashlib
import json
import os
import socket
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import uvicorn
from sqlalchemy import select

from app.models.analysis import AiUsageLog, AnalysisTask, MatchItem, MatchReport
from app.models.audit import AuditLog
from app.models.enums import TaskStatus
from app.tests.test_jobs_api import job_payload, jobs_db, organization, register  # noqa: F401


@asynccontextmanager
async def loopback_app(app):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", lifespan="off", ws="none", access_log=False, log_level="error"
        )
    )
    # Dependency overrides use this test's SQLite only. Lifespan recovery is
    # intentionally disabled so it cannot inspect/dispatch production tasks.
    running = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if running.done():
                    await running
                    raise RuntimeError("Synthetic HTTP server stopped before startup")
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(running, timeout=5)
        finally:
            listener.close()


async def seed_reports(factory, job, student, stranger):
    source = (
        "def label(name: str):\n"
        '    PASSWORD = "synthetic stdio credential with spaces"\n'
        "    return name.strip()"
    )
    ids = []
    snapshots = []
    requirement = job["requirements"][0]
    async with factory() as session:
        for index, person in enumerate((student, student, stranger)):
            task = AnalysisTask(
                created_by=UUID(person["id"]), task_type="job_match", status=TaskStatus.COMPLETED
            )
            session.add(task)
            await session.flush()
            snippet = "def label(name: str):\n    pass" if index == 0 else source
            evidence = {
                "citationId": "R1-E1",
                "provenance": "portfolio",
                "skill": "Python",
                "evidenceType": "python_code",
                "filePath": "synthetic-version/label.py",
                "lineStart": 1,
                "lineEnd": len(snippet.splitlines()),
                "snippet": snippet,
                "strength": "low",
                "explanation": "合成保存片段，未执行。",
                "contentHash": hashlib.sha256(snippet.encode()).hexdigest(),
            }
            snapshot = {
                "requirementTitle": requirement["rawText"],
                "skill": "Python",
                "evidence": evidence,
                "evidenceList": [evidence],
            }
            report = MatchReport(
                analysis_task_id=task.id,
                job_id=UUID(job["id"]),
                candidate_ref=person["id"],
                candidate_name="合成协议学生",
                job_snapshot={
                    "title": "MCP协议合成岗位",
                    "requirements": [
                        {
                            "id": requirement["id"],
                            "title": requirement["rawText"],
                            "skill": "Python",
                            "weight": 5,
                        }
                    ],
                },
                summary='合成协议报告 PASSWORD="synthetic stdio credential with spaces"',
                created_at=datetime.now(UTC) + timedelta(seconds=index),
            )
            session.add(report)
            await session.flush()
            session.add(
                MatchItem(
                    report_id=report.id,
                    requirement_id=UUID(requirement["id"]),
                    rule_base_score=0,
                    weight=5,
                    verdict="partial",
                    explanation="合成保存证据，不认证本人能力。",
                    formula_version="synthetic",
                    evidence_snapshot=snapshot,
                )
            )
            ids.append(str(report.id))
            snapshots.append(snapshot)
        await session.commit()
    return ids, snapshots


def structured(result):
    assert not result.isError, "Official client received a tool error"
    return result.structuredContent or json.loads(result.content[0].text)


async def test_official_stdio_client_reads_scoped_routes_filters_and_revokes(jobs_db):  # noqa: F811
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    app, factory = jobs_db
    async with (
        loopback_app(app) as base_url,
        httpx.AsyncClient(base_url=base_url, trust_env=False, timeout=10) as hr,
        httpx.AsyncClient(base_url=base_url, trust_env=False, timeout=10) as owner,
        httpx.AsyncClient(base_url=base_url, trust_env=False, timeout=10) as other,
    ):
        await register(hr, "stdio-hr@example.com")
        org = await organization(hr, "合成MCP组织")
        job_response = await hr.post("/api/v1/jobs", json=job_payload(org))
        assert job_response.status_code == 201
        job = job_response.json()["data"]
        student = await register(owner, "stdio-student@example.com", "student")
        stranger = await register(other, "stdio-other@example.com", "student")
        ids, original_snapshots = await seed_reports(factory, job, student, stranger)
        response = await owner.post(
            "/api/v1/mcp-tools/grants",
            json={"report_ids": ids[:2], "external_client_consent": True},
        )
        assert response.status_code == 200
        grant = response.json()["data"]
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
        }
        environment.update(
            CAREERPROOF_API_URL=base_url, CAREERPROOF_MCP_TOKEN=grant["token"], PYTHONUTF8="1"
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            cwd=str(Path(__file__).resolve().parents[2]),
            env=environment,
        )
        revoked = False
        try:
            async with asyncio.timeout(40):
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        tools = (await client.list_tools()).tools
                        assert {tool.name for tool in tools} == {
                            "search_evidence",
                            "get_report_summary",
                            "compare_reports",
                        }
                        assert all(
                            tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
                            for tool in tools
                        )
                        summary = structured(
                            await client.call_tool("get_report_summary", {"report_id": ids[1]})
                        )
                        assert summary["result"]["reportId"] == ids[1]
                        assert "synthetic stdio credential" not in json.dumps(summary)
                        assert "untrusted" in summary["boundary"]
                        search = structured(
                            await client.call_tool(
                                "search_evidence",
                                {"report_id": ids[1], "query": "Python", "limit": 1},
                            )
                        )
                        hit = search["result"]["evidence"][0]
                        assert hit["citationId"] == "R1-E1"
                        assert "name: str" in hit["snippet"]
                        assert "synthetic stdio credential" not in hit["snippet"]
                        assert (
                            hit["contentHash"] == original_snapshots[1]["evidence"]["contentHash"]
                        )
                        comparison = structured(
                            await client.call_tool(
                                "compare_reports", {"base_id": ids[0], "target_id": ids[1]}
                            )
                        )
                        assert comparison["result"]["baseId"] == ids[0]
                        assert comparison["result"]["targetId"] == ids[1]
                        assert comparison["result"]["items"][0]["addedEvidence"]
                        denied = await client.call_tool("get_report_summary", {"report_id": ids[2]})
                        assert denied.isError
                        invalid = await client.call_tool(
                            "search_evidence",
                            {"report_id": ids[1], "query": "Python", "limit": 99},
                        )
                        assert invalid.isError
                        assert grant["token"] not in str(denied) + str(invalid)
                        assert "synthetic stdio credential" not in str(denied) + str(invalid)
                        removal = await owner.delete(f"/api/v1/mcp-tools/grants/{grant['grantId']}")
                        assert removal.status_code == 200
                        revoked = True
                        after_revoke = await client.call_tool(
                            "get_report_summary", {"report_id": ids[1]}
                        )
                        assert after_revoke.isError
        finally:
            if not revoked:
                cleanup = await owner.delete(f"/api/v1/mcp-tools/grants/{grant['grantId']}")
                assert cleanup.status_code == 200
        async with factory() as session:
            calls = list(
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.action == "mcp.call", AuditLog.resource_id == grant["grantId"]
                    )
                )
            )
            statuses = [row.details["status"] for row in calls]
            assert statuses.count("completed") == 3 and statuses.count("rejected") == 2
            assert statuses.count("revoked_or_missing") == 1 and len(calls) == 6
            assert grant["token"] not in json.dumps([row.details for row in calls])
            assert "synthetic stdio credential" not in json.dumps([row.details for row in calls])
            items = list(await session.scalars(select(MatchItem)))
            assert {str(item.report_id): item.evidence_snapshot for item in items} == dict(
                zip(ids, original_snapshots, strict=True)
            )
            assert len(list(await session.scalars(select(MatchReport)))) == 3
            assert list(await session.scalars(select(AiUsageLog))) == []
