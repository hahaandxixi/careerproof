"""MCP scopes and audit regressions. No external model calls."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.models.analysis import AnalysisTask, MatchReport
from app.models.audit import AuditLog
from app.schemas.mcp_tools import EvidenceQuery
from app.services.mcp_tools import (
    dispatch,
    grant_expired,
    sanitize_export,
    sanitize_tool_result,
)
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
                    summary=(
                        "contact: private@example.com "
                        'PASSWORD="synthetic quoted gateway credential"'
                    ),
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
        assert "synthetic quoted gateway credential" not in response.text
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
            reports = list(await session.scalars(select(MatchReport)))
            assert all(
                "synthetic quoted gateway credential" in report.summary for report in reports
            )


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
    synthetic_key = "sk-" + "0123456789abcdefghijkl"
    raw = {
        "snippet": "email: private@example.com phone: 13800138000 "
        + "API_KEY=synthetic-private-value "
        + synthetic_key
        + " "
        + "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvbmUifQ.signature"
    }
    safe = json.dumps(sanitize_export(raw))
    for secret in (
        "private@example.com",
        "13800138000",
        "synthetic-private-value",
        synthetic_key,
        "eyJhbGci",
    ):
        assert secret not in safe


def test_grant_deadlines_fail_closed_and_use_the_earlier_expiry():
    now = datetime.now(UTC)
    future = now + timedelta(minutes=5)
    past = now - timedelta(seconds=1)
    grant = SimpleNamespace(details={"expiresAt": future.isoformat()})
    assert not grant_expired({"exp": future.timestamp()}, grant)
    assert grant_expired({"exp": past.timestamp()}, grant)
    grant.details["expiresAt"] = past.isoformat()
    assert grant_expired({"exp": future.timestamp()}, grant)
    for invalid in (None, "invalid", future.replace(tzinfo=None).isoformat()):
        grant.details["expiresAt"] = invalid
        assert grant_expired({"exp": future.timestamp()}, grant)
    assert grant_expired({}, grant)


@pytest.mark.parametrize("fault", ["database_failure", "expires_after_dispatch"])
async def test_failed_or_expired_tool_keeps_audit_and_does_not_export(jobs_db, monkeypatch, fault):  # noqa: F811
    app, factory = jobs_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as owner,
    ):
        await register(hr, f"mcp-fault-hr-{fault}@example.com")
        org = await organization(hr)
        job = (await hr.post("/api/v1/jobs", json=job_payload(org))).json()["data"]
        student = await register(owner, f"mcp-fault-{fault}@example.com", "student")
        async with factory() as session:
            task = AnalysisTask(created_by=UUID(student["id"]), task_type="job_match")
            session.add(task)
            await session.flush()
            report = MatchReport(
                analysis_task_id=task.id,
                job_id=UUID(job["id"]),
                candidate_ref=student["id"],
                summary="synthetic private result",
            )
            session.add(report)
            await session.commit()
            report_id = str(report.id)
        grant = (
            await owner.post(
                "/api/v1/mcp-tools/grants",
                json={
                    "report_ids": [report_id],
                    "external_client_consent": True,
                },
            )
        ).json()["data"]
        if fault == "database_failure":

            async def failed_dispatch(session, *_args):
                await session.execute(text("SELECT nonexistent_synthetic_column FROM audit_logs"))

            monkeypatch.setattr("app.services.mcp_tools.dispatch", failed_dispatch)
        else:
            checks = iter((False, True))
            monkeypatch.setattr("app.services.mcp_tools.grant_expired", lambda *_: next(checks))
        call = {"tool": "get_report_summary", "arguments": {"report_id": report_id}}
        response = await owner.post(
            "/api/v1/mcp-tools/invoke",
            json=call,
            headers={"Authorization": f"Bearer {grant['token']}"},
        )
        assert response.status_code == (503 if fault == "database_failure" else 401)
        assert "synthetic private result" not in response.text
        assert "nonexistent_synthetic_column" not in response.text
        async with factory() as session:
            calls = list(
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.action == "mcp.call",
                        AuditLog.resource_id == grant["grantId"],
                    )
                )
            )
            assert len(calls) == 1
            assert calls[0].details["status"] == (
                "failed" if fault == "database_failure" else "expired"
            )
            assert grant["token"] not in json.dumps(calls[0].details)
            # A rejected/failed admitted call still consumes one of the forty slots.
            session.add_all(
                [
                    AuditLog(
                        actor_id=UUID(student["id"]),
                        action="mcp.call",
                        resource_type="mcp_grant",
                        resource_id=grant["grantId"],
                        details={"status": "completed"},
                    )
                    for _ in range(39)
                ]
            )
            await session.commit()
        monkeypatch.setattr("app.services.mcp_tools.grant_expired", lambda *_: False)
        capped = await owner.post(
            "/api/v1/mcp-tools/invoke",
            json=call,
            headers={"Authorization": f"Bearer {grant['token']}"},
        )
        assert capped.status_code == 429


@pytest.mark.parametrize(
    "source, secret",
    [
        ('PASSWORD = "first half second half"', "second half"),
        ("password='first half second half'", "second half"),
        ('{"client_secret": "synthetic secret with spaces"}', "synthetic secret with spaces"),
        ('DB_PASSWORD = "a\\"quoted password suffix"', "password suffix"),
        ('service_token = """first line\nsecond secret line"""', "second secret line"),
        ("Authorization: Bearer synthetic-bearer-value", "synthetic-bearer-value"),
        ("Authorization: Basic c3ludGhldGljOnNlY3JldA==", "c3ludGhldGljOnNlY3JldA=="),
        ("postgresql://synthetic-user:synthetic-password@localhost/db", "synthetic-password"),
        (
            'KEY="-----BEGIN PRIVATE KEY-----\nSYNTHETIC-KEY-MATERIAL\n-----END PRIVATE KEY-----"',
            "SYNTHETIC-KEY-MATERIAL",
        ),
        ("-----BEGIN OPENSSH PRIVATE KEY-----\nSYNTHETIC-TRUNCATED-KEY", "SYNTHETIC-TRUNCATED-KEY"),
    ],
)
def test_mcp_export_redacts_entire_credential_not_only_first_word(source, secret):
    safe = json.dumps(sanitize_export({"snippet": source}))
    assert secret not in safe
    assert "redacted credential" in safe


def test_mcp_export_redacts_known_standalone_tokens_recursively():
    credentials = [
        "ghp_" + "a" * 36,
        "github_pat_" + "b" * 55,
        "glpat-" + "c" * 24,
        "AKIA" + "D" * 16,
    ]
    raw = {"items": [{"snippet": "credentials: " + " ".join(credentials)}]}
    safe = json.dumps(sanitize_export(raw))
    assert all(value not in safe for value in credentials)
    assert safe.count("redacted credential") == len(credentials)


def test_mcp_export_preserves_python_annotation_context_but_redacts_personal_names():
    source = 'def greet(name: str, username: str):\n    # name: 张三\n    return "姓名：李四"'
    raw = {
        "items": [
            {"filePath": "version/example.py", "snippet": source, "contentHash": "frozen-source"}
        ]
    }
    safe = sanitize_export(raw)
    assert "name: str, username: str" in safe["items"][0]["snippet"]
    assert "张三" not in safe["items"][0]["snippet"]
    assert "李四" not in safe["items"][0]["snippet"]
    assert safe["items"][0]["contentHash"] == "frozen-source"
    assert raw["items"][0]["snippet"] == source


@pytest.mark.parametrize("quote", ['"', "'"])
def test_mcp_export_redacts_cut_off_quoted_password_through_trailing_escape(quote):
    source = "PASSWORD = " + quote + "synthetic first portion private tail" + chr(92)
    safe = sanitize_export({"snippet": source})["snippet"]
    assert "private tail" not in safe and "synthetic first" not in safe


def test_mcp_export_redacts_structured_credential_values_without_mutating_source():
    raw = {
        "headers": {"Authorization": "Bearer synthetic-auth-header"},
        "nested": [{"api_key": "synthetic structured value", "password": "another private value"}],
        "lineStart": 7,
        "contentHash": "source-hash",
    }
    safe = sanitize_export(raw)
    assert "synthetic-auth-header" not in json.dumps(safe)
    assert "synthetic structured value" not in json.dumps(safe)
    assert "another private value" not in json.dumps(safe)
    assert safe["contentHash"] == "source-hash" and safe["lineStart"] == 7
    assert raw["headers"]["Authorization"] == "Bearer synthetic-auth-header"


def test_mcp_export_keeps_valid_source_hash_and_uuid_without_exempting_text():
    identifier = "13800138-0000-4000-8000-a13800138000"
    digest = "821565e542f5768547b98f8489a8f14286353423b68b7022d6ab856a36afdc2e"
    raw = {
        "reportId": identifier,
        "items": [
            {
                "requirementId": identifier,
                "contentHash": digest,
                "filePath": identifier + "/13800138000-owner@example.com.py",
                "snippet": "contact: 13800138000 owner@example.com",
            }
        ],
        "summary": identifier,
    }
    safe = sanitize_export(raw)
    item = safe["items"][0]
    assert safe["reportId"] == identifier and item["requirementId"] == identifier
    assert item["contentHash"] == digest
    assert item["filePath"].startswith(identifier + "/")
    assert "13800138000" not in item["filePath"].split("/", 1)[1]
    assert "owner@example.com" not in item["filePath"] + item["snippet"]
    assert "13800138000" not in item["snippet"]
    assert safe["summary"] != identifier
    assert raw["items"][0]["contentHash"] == digest
    assert raw["items"][0]["snippet"] == "contact: 13800138000 owner@example.com"


@pytest.mark.parametrize("field", ["contentHash", "reportId", "requirementId", "filePath"])
def test_mcp_metadata_field_names_do_not_bypass_private_text_filter(field):
    raw = {field: "13800138000 owner@example.com PASSWORD='synthetic private tail'"}
    safe = sanitize_export(raw)[field]
    assert "13800138000" not in safe and "owner@example.com" not in safe
    assert "synthetic private tail" not in safe


@pytest.mark.parametrize(
    "source,truncated,redacted",
    [
        ("def label(name: str): return name.strip()", False, False),
        ("x" * 1000, False, False),
        ("x" * 1001, True, False),
        ('def f(api_key: str = "synthetic private tail"):\n    return 1', False, True),
        (
            "# " + "x" * 920 + '\nPASSWORD="' + "synthetic private tail " * 70 + '"\nreturn 1',
            False,
            True,
        ),
    ],
    ids=["exact", "exact-limit", "cut", "annotated-credential", "credential-crosses-cut"],
)
def test_search_export_distinguishes_exact_redacted_and_truncated_text(source, truncated, redacted):
    import copy

    original = {
        "evidence": [
            {
                "filePath": "version/app.py",
                "snippet": source,
                "lineStart": 1,
                "lineEnd": 20,
                "contentHash": "original-hash",
            }
        ]
    }
    snapshot = copy.deepcopy(original)
    result = sanitize_tool_result("search_evidence", original)
    hit = result["evidence"][0]
    assert hit["snippetTruncated"] is truncated
    assert hit["snippetRedacted"] is redacted
    assert hit["sourceRangeBasis"] == "saved_original_excerpt"
    assert hit["contentHashBasis"] == "original_source"
    assert hit["snippetReturnedChars"] == len(hit["snippet"]) <= 1000
    assert hit["lineEnd"] == 20 and hit["contentHash"] == "original-hash"
    assert "synthetic private tail" not in hit["snippet"]
    if not truncated and not redacted:
        assert hit["snippet"] == source
    assert original == snapshot
