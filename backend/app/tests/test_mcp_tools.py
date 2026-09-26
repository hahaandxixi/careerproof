"""MCP scopes and audit regressions. No external model calls."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.models.analysis import AnalysisTask, MatchReport
from app.models.audit import AuditLog
from app.schemas.mcp_tools import EvidenceQuery
from app.services.mcp_tools import dispatch, sanitize_export
from app.tests.test_jobs_api import job_payload, jobs_db, organization, register  # noqa: F401


async def test_scoped_grants_read_only_revoke_and_independent_audit(jobs_db):  # noqa: F811
    app, factory = jobs_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as owner,
        AsyncClient(transport=transport, base_url="http://test") as stranger,
    ):
        await register(hr, "mcp-hr@example.com")
        org = await organization(hr)
        job = (await hr.post("/api/v1/jobs", json=job_payload(org))).json()["data"]
        student = await register(owner, "mcp-owner@example.com", "student")
        other = await register(stranger, "mcp-other@example.com", "student")
        ids = []
        async with factory() as session:
            for user in (student, student, other):
                task = AnalysisTask(created_by=UUID(user["id"]), task_type="job_match")
                session.add(task)
                await session.flush()
                report = MatchReport(
                    analysis_task_id=task.id,
                    job_id=UUID(job["id"]),
                    candidate_ref=user["id"],
                    summary="contact: private@example.com",
                    created_at=datetime.now(UTC) + timedelta(seconds=len(ids)),
                )
                session.add(report)
                await session.flush()
                ids.append(str(report.id))
            await session.commit()
        grant_url = "/api/v1/mcp-tools/grants"
        payload = {"report_ids": ids[:2], "external_client_consent": True}
        assert (await hr.post(grant_url, json=payload)).status_code == 403
        assert (await owner.post(grant_url, json={"report_ids": ids[:1]})).status_code == 403
        assert (
            await owner.post(grant_url, json={**payload, "report_ids": [ids[2]]})
        ).status_code == 404
        grant = (await owner.post(grant_url, json=payload)).json()["data"]
        auth = {"Authorization": f"Bearer {grant['token']}"}
        endpoint = "/api/v1/mcp-tools/invoke"
        call = {"tool": "get_report_summary", "arguments": {"report_id": ids[0]}}
        # A login cookie is not an MCP grant; an MCP token is not a login token.
        assert (await owner.post(endpoint, json=call)).status_code == 401
        assert (await owner.get("/api/v1/users/me", headers=auth)).status_code == 401
        response = await owner.post(endpoint, json=call, headers=auth)
        assert response.status_code == 200, response.text
        assert "private@example.com" not in response.text
        assert "candidateName" not in response.text and "candidateId" not in response.text
        # Issued subject, not whichever user's cookie happens to be present.
        assert (await stranger.post(endpoint, json=call, headers=auth)).status_code == 200
        denied = {**call, "arguments": {"report_id": ids[2]}}
        assert (await owner.post(endpoint, json=denied, headers=auth)).status_code == 404
        assert (
            await owner.post(
                endpoint,
                json={
                    "tool": "compare_reports",
                    "arguments": {"base_id": ids[0], "target_id": ids[1]},
                },
                headers=auth,
            )
        ).status_code == 200
        assert (
            await owner.post(endpoint, json={**call, "tool": "delete_report"}, headers=auth)
        ).status_code == 422
        assert (
            await owner.post(
                endpoint,
                json={**call, "arguments": {"report_id": ids[0], "owner_id": other["id"]}},
                headers=auth,
            )
        ).status_code == 422
        expired = jwt.decode(
            grant["token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        expired["exp"] = int(datetime.now(UTC).timestamp()) - 1
        bad_auth = {
            "Authorization": "Bearer "
            + jwt.encode(expired, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        }
        assert (await owner.post(endpoint, json=call, headers=bad_auth)).status_code == 401
        assert (await stranger.delete(f"{grant_url}/{grant['grantId']}")).status_code == 404
        assert (await owner.delete(f"{grant_url}/{grant['grantId']}")).status_code == 200
        assert (await owner.post(endpoint, json=call, headers=auth)).status_code == 401
        capped = (await owner.post(grant_url, json=payload)).json()["data"]
        async with factory() as session:
            session.add_all(
                [
                    AuditLog(
                        actor_id=UUID(student["id"]),
                        action="mcp.call",
                        resource_type="mcp_grant",
                        resource_id=capped["grantId"],
                        details={"status": "completed"},
                    )
                    for _ in range(40)
                ]
            )
            await session.commit()
        assert (
            await owner.post(
                endpoint, json=call, headers={"Authorization": f"Bearer {capped['token']}"}
            )
        ).status_code == 429
        await owner.delete(f"{grant_url}/{capped['grantId']}")
        async with factory() as session:
            audits = list(await session.scalars(select(AuditLog)))
            text = json.dumps([row.details for row in audits])
            assert grant["token"] not in text and "private@example.com" not in text
            assert {"mcp.grant", "mcp.call", "mcp.revoke", "mcp.auth_denied"} <= {
                row.action for row in audits
            }
            assert {"completed", "rejected", "revoked_or_missing"} <= {
                row.details.get("status") for row in audits if row.action == "mcp.call"
            }
            assert len(list(await session.scalars(select(MatchReport)))) == 3


async def test_report_search_is_bounded_snapshot_search(monkeypatch):
    evidence = SimpleNamespace(
        citation_id="R1-E1",
        file_path="app.py",
        line_start=1,
        line_end=4,
        content_hash="synthetic-hash",
        provenance="portfolio",
        snippet="def create_app(): return FastAPI()",
    )
    report = SimpleNamespace(
        id=uuid4(), items=[SimpleNamespace(skill="FastAPI", evidence_list=[evidence])]
    )

    async def saved(*_args):
        return report

    monkeypatch.setattr("app.services.mcp_tools.owned_report", saved)
    args = EvidenceQuery(report_id=report.id, query="FastAPI", limit=1)
    result = await dispatch(None, None, "search_evidence", args)
    assert result["evidence"][0]["citationId"] == "R1-E1"
    assert result["evidence"][0]["contentHash"] == "synthetic-hash"
    args.query = "unrelated SQL"
    assert (await dispatch(None, None, "search_evidence", args))["evidence"] == []


def test_export_redacts_identifiers_and_credential_shapes():
    raw = {
        "snippet": "email: private@example.com phone: 13800138000 "
        "API_KEY=synthetic-private-value sk-0123456789abcdefghijkl "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvbmUifQ.signature"
    }
    safe = json.dumps(sanitize_export(raw))
    for secret in (
        "private@example.com",
        "13800138000",
        "synthetic-private-value",
        "sk-0123456789abcdefghijkl",
        "eyJhbGci",
    ):
        assert secret not in safe
