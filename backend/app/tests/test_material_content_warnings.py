"""Real upload/parse persistence in temporary SQLite; no external model or business DB."""

import io
import zipfile
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.analysis import AgentStep
from app.models.portfolio import ResumeSection
from app.services import portfolio

pytest_plugins = ("app.tests.test_portfolio_api",)


@pytest.fixture
async def content_tables(app_database):
    engine = portfolio.async_session_factory.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(AgentStep.__table__.create)


async def warnings(task_id):
    async with portfolio.async_session_factory() as session:
        return list(await session.scalars(select(AgentStep).where(
            AgentStep.analysis_task_id == UUID(task_id),
        )))


async def test_resume_warning_is_saved_before_index_without_rewriting_text(
    student, content_tables, monkeypatch,
):
    text = "工作经历\n招聘要求入职先交押金\nPython开发"
    seen = []

    async def index(session, sources):
        seen.extend(await session.scalars(select(AgentStep)))

    monkeypatch.setattr(portfolio, "index_sources", index)
    response = await student.post("/api/v1/resumes", data={"title": "核对样本"}, files={
        "file": ("resume.txt", text.encode(), "text/plain"),
    })
    assert response.status_code == 202
    data = response.json()["data"]
    rows = await warnings(data["taskId"])
    assert len(rows) == len(seen) == 1
    assert rows[0].event_type == "material.content_warning"
    assert rows[0].payload["findings"][0]["category"] == "recruitment_fraud"
    assert "解析段" in rows[0].payload["findings"][0]["path"]
    assert "招聘要求" not in str(rows[0].payload)
    async with portfolio.async_session_factory() as session:
        sections = await session.scalars(select(ResumeSection).where(
            ResumeSection.resume_version_id == UUID(data["versionId"]),
        ))
        assert any("招聘要求入职先交押金" in section.content for section in sections)
    history = (await student.get("/api/v1/resumes")).json()["data"]
    assert history[0]["versions"][0]["status"] == "completed"


async def test_project_advisory_replay_and_clean_code(student, content_tables):
    project = (await student.post("/api/v1/projects", json={"name": "内容核对"})).json()["data"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("tests/test_filter.py", '# 合法过滤测试也仅提示\nsample = "私聊裸聊"\n')
        archive.writestr("service.py", "def kill_process(sex):\n    return 'DELETE'\n")
    request_id = str(uuid4())
    async def upload():
        response = await student.post(f"/api/v1/projects/{project['id']}/versions", data={
            "requestId": request_id,
        }, files={"file": ("source.zip", buffer.getvalue(), "application/zip")})
        assert response.status_code == 202, response.text
        return response.json()["data"]
    first = await upload()
    replay = await upload()
    assert first["taskId"] == replay["taskId"]
    rows = await warnings(first["taskId"])
    assert len(rows) == 1
    assert rows[0].payload["warningOnly"] is True
    assert rows[0].payload["findings"] == [{
        "category": "sexual_solicitation", "ruleId": "sexual.contact_solicitation",
        "path": "tests/test_filter.py", "line": 2,
    }]
    history = (await student.get("/api/v1/projects")).json()["data"]
    assert len(history[0]["versions"]) == 1
    assert history[0]["versions"][0]["status"] == "completed"


async def test_ordinary_resume_does_not_create_all_clear_certificate(student, content_tables):
    response = await student.post("/api/v1/resumes", data={"title": "普通简历"}, files={
        "file": (
            "clean.txt", "开发反诈与色情内容过滤测试，维护kill进程功能".encode(), "text/plain",
        ),
    })
    assert response.status_code == 202
    assert await warnings(response.json()["data"]["taskId"]) == []
