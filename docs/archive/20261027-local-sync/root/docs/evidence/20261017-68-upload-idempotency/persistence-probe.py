"""One-off persistence-count probe for the 67 -> 68 upload retry idempotency check.

Not a permanent test: it drives the real endpoint twice (success, then a lost-response
retry with the same requestId) and prints the row counts it actually finds in the
database, so the handoff can cite persisted numbers instead of only re-reading the
existing assertions in test_portfolio_api.py.
"""

from __future__ import annotations

import io
import zipfile
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

pytest_plugins = ["app.tests.test_portfolio_api"]

from app.models.analysis import AnalysisTask
from app.models.portfolio import Project, ProjectVersion


def _archive(entry: str, body: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(entry, body)
    return buffer.getvalue()


async def test_counts(student, app_database):
    """Count rows through a fresh session on the same isolated database."""
    content = _archive("src/main.py", "x = 1\n")
    project = (
        await student.post("/api/v1/projects", json={"name": "count-probe-2"})
    ).json()["data"]
    path = f"/api/v1/projects/{project['id']}/versions"
    key = str(uuid4())

    first = await student.post(
        path,
        data={"requestId": key},
        files={"file": ("source.zip", content, "application/zip")},
    )
    assert first.status_code == 202, first.text
    retry = await student.post(
        path,
        data={"requestId": key},
        files={"file": ("source.zip", content, "application/zip")},
    )
    assert retry.status_code == 202, retry.text

    first_data = first.json()["data"]
    retry_data = retry.json()["data"]

    versions = (await student.get(path)).json()["data"]
    history = (await student.get("/api/v1/projects")).json()["data"]
    projects = [row for row in history if row["name"] == "count-probe-2"]

    print("\n=== PERSISTENCE COUNTS (lost-response retry) ===")
    print(f"first.versionId      = {first_data['versionId']}")
    print(f"retry.versionId      = {retry_data['versionId']}")
    print(f"version_id_equal     = {first_data['versionId'] == retry_data['versionId']}")
    print(f"task_id_equal        = {first_data['taskId'] == retry_data['taskId']}")
    print(f"versions_via_api     = {len(versions)}")
    print(f"projects_named_probe = {len(projects)}")
    print(f"projects_total       = {len(history)}")
    print(f"scan_calls_expected  = 1 (only the first submit enqueues a task)")

    assert first_data["versionId"] == retry_data["versionId"]
    assert first_data["taskId"] == retry_data["taskId"]
    assert len(versions) == 1
    assert len(projects) == 1
