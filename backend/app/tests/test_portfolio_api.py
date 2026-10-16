"""Exercise real HTTP, cookies, repositories and uploads against an isolated database.

SQLite covers persistence and uniqueness; these tests do not validate PostgreSQL
row-lock semantics or apply the production Alembic migration.
"""

import asyncio
import io
import zipfile
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_session
from app.main import create_app
from app.models.analysis import AnalysisTask
from app.models.identity import RefreshToken, StudentProfile, User
from app.models.login_limit import LoginLimit
from app.models.portfolio import (
    Project,
    ProjectFile,
    ProjectVersion,
    Resume,
    ResumeSection,
    ResumeVersion,
)
from app.services import portfolio as portfolio_service


def project_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("src/main.py", "def hello():\n    return 'hello'\n")
    return buffer.getvalue()


@pytest.fixture
async def app_database(tmp_path, monkeypatch):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(database_url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    tables = [
        model.__table__
        for model in (
            User,
            RefreshToken,
            LoginLimit,
            StudentProfile,
            AnalysisTask,
            Resume,
            ResumeVersion,
            ResumeSection,
            Project,
            ProjectVersion,
            ProjectFile,
        )
    ]
    # The fixture only creates tables in this test's temporary database.
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(sync, tables=tables, checkfirst=False)
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_session] = session_override
    monkeypatch.setattr(portfolio_service, "async_session_factory", factory)
    monkeypatch.setattr(settings, "storage_base_dir", tmp_path / "storage")
    try:
        yield application
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()


async def register(client: AsyncClient, email: str, role: str = "student"):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "test-password-2026",
            "displayName": "测试学生",
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["user"]


@pytest.fixture
async def student(app_database):
    async with AsyncClient(
        transport=ASGITransport(app=app_database), base_url="http://test"
    ) as client:
        await register(client, "alice@example.com")
        yield client


async def test_history_survives_new_session_and_preserves_versions(student, app_database):
    resume_response = await student.post(
        "/api/v1/resumes",
        data={"title": "校招简历"},
        files={
            "file": ("resume.txt", "Python项目经历".encode(), "text/plain"),
        },
    )
    assert resume_response.status_code == 202, resume_response.text
    resume = resume_response.json()["data"]
    project = (
        await student.post(
            "/api/v1/projects",
            json={
                "name": "课程项目",
                "requestId": str(uuid4()),
            },
        )
    ).json()["data"]
    for _ in range(2):
        response = await student.post(
            f"/api/v1/projects/{project['id']}/versions",
            data={
                "requestId": str(uuid4()),
            },
            files={"file": ("source.zip", project_zip(), "application/zip")},
        )
        assert response.status_code == 202, response.text
    before = (await student.get("/api/v1/projects")).json()["data"]
    assert [v["versionNumber"] for v in before[0]["versions"]] == [2, 1]
    assert before[0]["versions"][0]["status"] == "completed"
    assert before[0]["versions"][0]["taskId"]
    assert before[0]["versions"][0]["originalFilename"] == "source.zip"
    assert (await student.post("/api/v1/auth/logout")).status_code == 200
    assert (await student.get("/api/v1/projects")).status_code == 401
    async with AsyncClient(
        transport=ASGITransport(app=app_database), base_url="http://test"
    ) as again:
        login = await again.post(
            "/api/v1/auth/login",
            json={
                "email": "alice@example.com",
                "password": "test-password-2026",
            },
        )
        assert login.status_code == 200
        assert (await again.get("/api/v1/projects")).json()["data"] == before
        resumes = (await again.get("/api/v1/resumes")).json()["data"]
        assert resumes[0]["id"] == resume["resumeId"]
        assert resumes[0]["versions"][0]["taskId"] == resume["taskId"]
        versions = (await again.get(f"/api/v1/resumes/{resume['resumeId']}/versions")).json()[
            "data"
        ]
        assert versions == resumes[0]["versions"]
        assert versions[0]["status"] == "completed"


async def test_materials_are_scoped_to_owner(student, app_database):
    project = (await student.post("/api/v1/projects", json={"name": "private"})).json()["data"]
    resume = (
        await student.post(
            "/api/v1/resumes",
            data={"title": "private"},
            files={
                "file": ("a.txt", b"private", "text/plain"),
            },
        )
    ).json()["data"]
    async with AsyncClient(
        transport=ASGITransport(app=app_database), base_url="http://test"
    ) as bob:
        await register(bob, "bob@example.com")
        for path in ("/resumes", "/projects"):
            assert (await bob.get(f"/api/v1{path}")).json()["data"] == []
        for path in (
            f"/projects/{project['id']}/versions",
            f"/resumes/{resume['resumeId']}/versions",
        ):
            assert (await bob.get(f"/api/v1{path}")).status_code == 404
        assert (
            await bob.post(
                f"/api/v1/projects/{project['id']}/versions",
                files={
                    "file": ("a.zip", project_zip(), "application/zip"),
                },
            )
        ).status_code == 404
    async with AsyncClient(transport=ASGITransport(app=app_database), base_url="http://test") as hr:
        await register(hr, "hr@example.com", "enterprise")
        assert (await hr.get("/api/v1/resumes")).status_code == 403
        assert (await hr.get("/api/v1/projects")).status_code == 403


async def test_project_creation_replays_and_rejects_different_payload(student):
    payload = {"name": "idempotent", "description": "same", "requestId": str(uuid4())}
    first = await student.post("/api/v1/projects", json=payload)
    second = await student.post("/api/v1/projects", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    conflict = await student.post("/api/v1/projects", json={**payload, "name": "changed"})
    assert conflict.status_code == 409
    assert len((await student.get("/api/v1/projects")).json()["data"]) == 1
    # Same names with a different logical request are valid distinct projects.
    other = await student.post("/api/v1/projects", json={**payload, "requestId": str(uuid4())})
    assert other.json()["data"]["id"] != first.json()["data"]["id"]


async def test_creation_key_is_scoped_per_student(student, app_database):
    payload = {"name": "same-key", "requestId": str(uuid4())}
    first = (await student.post("/api/v1/projects", json=payload)).json()["data"]
    async with AsyncClient(
        transport=ASGITransport(app=app_database), base_url="http://test"
    ) as bob:
        await register(bob, "bob@example.com")
        second = (await bob.post("/api/v1/projects", json=payload)).json()["data"]
        assert first["id"] != second["id"]


async def test_failed_upload_retry_keeps_project_and_replays_version(student, monkeypatch):
    calls = []
    original = portfolio_service.execute_project_scan_task

    async def scan(task_id, version_id):
        calls.append(version_id)
        await original(task_id, version_id)

    monkeypatch.setattr("app.api.v1.portfolio.execute_project_scan_task", scan)
    payload = {"name": "retry", "requestId": str(uuid4())}
    project = (await student.post("/api/v1/projects", json=payload)).json()["data"]
    path = f"/api/v1/projects/{project['id']}/versions"
    key = str(uuid4())
    failed = await student.post(
        path,
        data={"requestId": key},
        files={
            "file": ("not-supported.exe", b"invalid", "application/octet-stream"),
        },
    )
    assert failed.status_code == 415
    history = (await student.get("/api/v1/projects")).json()["data"]
    assert len(history) == 1 and history[0]["versions"] == []
    content = project_zip()
    first = await student.post(
        path,
        data={"requestId": key, "materialRole": "reference"},
        files={
            "file": ("source.zip", content, "application/zip"),
        },
    )
    assert first.status_code == 202, first.text
    # Simulate lost response: replay the exact request after it committed.
    second = await student.post(
        path,
        data={"requestId": key, "materialRole": "reference"},
        files={
            "file": ("source.zip", content, "application/zip"),
        },
    )
    assert second.status_code == 202, second.text
    assert first.json()["data"]["versionId"] == second.json()["data"]["versionId"]
    assert first.json()["data"]["taskId"] == second.json()["data"]["taskId"]
    assert len(calls) == 1
    versions = (await student.get(path)).json()["data"]
    assert len(versions) == 1
    assert versions[0]["materialRole"] == "reference"
    changed_role = await student.post(
        path,
        data={"requestId": key, "materialRole": "portfolio"},
        files={"file": ("source.zip", content, "application/zip")},
    )
    assert changed_role.status_code == 409
    conflict = await student.post(
        path,
        data={"requestId": key, "materialRole": "reference"},
        files={
            "file": ("source.zip", b"different", "application/zip"),
        },
    )
    assert conflict.status_code == 409


async def test_concurrent_create_has_one_project(student):
    payload = {"name": "concurrent", "requestId": str(uuid4())}
    responses = await asyncio.gather(
        *[student.post("/api/v1/projects", json=payload) for _ in range(3)]
    )
    assert all(response.status_code == 201 for response in responses)
    assert len({response.json()["data"]["id"] for response in responses}) == 1
    assert len((await student.get("/api/v1/projects")).json()["data"]) == 1


async def test_preview_and_document_projects_are_private(student, app_database):
    resume = (
        await student.post(
            "/api/v1/resumes",
            data={"title": "运营简历"},
            files={"file": ("resume.txt", "有用户调研和运营经验".encode(), "text/plain")},
        )
    ).json()["data"]
    preview_path = f"/api/v1/resume-versions/{resume['versionId']}/preview"
    preview = (await student.get(preview_path)).json()["data"]
    assert preview["status"] == "completed"
    assert "用户调研" in preview["sections"][0]["content"]
    project = (await student.post("/api/v1/projects", json={"name": "运营作品"})).json()["data"]
    version = (
        await student.post(
            f"/api/v1/projects/{project['id']}/versions",
            files={
                "file": ("campaign.txt", "活动策划方案\n目标：提升参与率".encode(), "text/plain")
            },
        )
    ).json()["data"]
    files_path = f"/api/v1/project-versions/{version['versionId']}/files"
    files = (await student.get(files_path)).json()["data"]
    assert len(files) == 1 and files[0]["language"] == "Document"
    content_path = f"/api/v1/project-files/{files[0]['id']}"
    content = (await student.get(content_path)).json()["data"]
    assert content["projectVersionId"] == version["versionId"]
    assert "活动策划" in content["content"]
    async with AsyncClient(
        transport=ASGITransport(app=app_database), base_url="http://test"
    ) as bob:
        await register(bob, "preview-bob@example.com")
        for path in (preview_path, files_path, content_path):
            assert (await bob.get(path)).status_code == 404


async def test_corrupt_document_fails_without_internal_paths(student):
    response = await student.post(
        "/api/v1/resumes",
        data={"title": "broken"},
        files={"file": ("broken.pdf", b"not a PDF", "application/pdf")},
    )
    assert response.status_code == 202
    version = (await student.get("/api/v1/resumes")).json()["data"][0]["versions"][0]
    assert version["status"] == "failed"
    assert "文件" in version["errorMessage"]
    assert "storage" not in version["errorMessage"]
