"""Real HTTP/repository queries; temporary SQLite, or an explicitly owned PostgreSQL DB."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.main import create_app
from app.models.recruitment import Job
from app.tests.test_jobs_api import job_payload, organization, register
from app.tools.technical_careers import classify_title


@pytest.fixture
async def technical_db(tmp_path):
    url = os.environ.get("CP_HOME_TEST_DATABASE_URL")
    if url:
        target = urlsplit(url)
        assert (target.hostname, target.port) == ("127.0.0.1", 55447) and target.path in {
            "/cp_home_discovery_test_20261027",
            "/cp_home_discovery_regression_20261027",
        }, "Refuse any database not explicitly owned by this task"
    engine = create_async_engine(url or f"sqlite+aiosqlite:///{tmp_path / 'discovery.db'}")
    if not url:

        @event.listens_for(engine.sync_engine, "connect")
        def configure(connection, _):
            connection.create_function("num_nonnulls", -1, lambda *a: sum(x is not None for x in a))
            connection.execute("PRAGMA foreign_keys=ON")

    tables = [t for t in Base.metadata.sorted_tables if t.name != "knowledge_chunks"]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    try:
        yield app, factory
    finally:
        app.dependency_overrides.clear()
        if url:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.drop_all(sync, tables=tables))
        await engine.dispose()


async def posting(client, org, title, skills, **values):
    payload = {
        "title": title,
        "category": "software",
        "city": "深圳",
        "employmentType": "internship",
        "requirements": [{"skillName": s, "rawText": f"需要提供{s}的直接材料"} for s in skills],
        **values,
    }
    response = await client.post("/api/v1/jobs", json=job_payload(org, **payload))
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def test_all_seven_directions_are_server_filtered_without_inventing_unknown_jobs(
    technical_db,
):
    app, _ = technical_db
    examples = [
        ("backend", "Python 后端实习", ["Python", "FastAPI"]),
        ("frontend", "React 前端开发", ["React", "TypeScript"]),
        ("testing", "Java 自动化测试开发", ["Java", "pytest"]),
        ("data", "数据开发实习", ["SQL"]),
        ("ai", "大模型应用工程师", ["Python"]),
        ("cloud", "DevOps 运维开发", ["Docker"]),
        ("product", "AI产品经理", ["需求分析"]),
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "directions@example.com")
        org = await organization(client, "分类测试企业（合成）")
        ids = {key: await posting(client, org, title, skills) for key, title, skills in examples}
        unknown = await posting(
            client, org, "综合实习生", ["沟通表达"], description="接触后端、算法等团队"
        )
        ambiguous = await posting(client, org, "软件工程师", ["React", "FastAPI"])
        for key, _, _ in examples:
            result = (
                await client.get("/api/v1/jobs", params={"direction": key, "pageSize": 1})
            ).json()["data"]
            assert result["total"] == 1
            assert result["items"][0]["id"] == ids[key]
            assert result["items"][0]["careerDirection"] == key
        all_rows = (await client.get("/api/v1/jobs")).json()["data"]["items"]
        assert {unknown, ambiguous} <= {x["id"] for x in all_rows if x["careerDirection"] is None}
        backend = next(x for x in all_rows if x["id"] == ids["backend"])
        assert backend["technicalTags"] == ["FastAPI", "Python"]
        assert classify_title("Java 自动化测试开发", "software", ["Java"]) == "testing"


async def test_combined_filters_count_and_pagination_share_predicates(technical_db):
    app, factory = technical_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "combinations@example.com")
        org = await organization(client)
        first = await posting(
            client, org, "Python 后端 A", ["Python", "FastAPI"], description="ledger FastAPI"
        )
        second = await posting(
            client, org, "Python 后端 B", ["Python", "FastAPI"], description="ledger FastAPI"
        )
        await posting(client, org, "Python 后端校招", ["Python"], employmentType="campus")
        await posting(client, org, "Python 后端异地", ["Python"], city="广州")
        await posting(client, org, "JavaScript 后端", ["JavaScript"])
        java = await posting(client, org, "Java 后端", ["Java"])
        hidden = await posting(client, org, "Python 后端隐藏", ["Python"], description="ledger")
        await posting(client, org, "Python 后端草稿", ["Python"], status="draft")
        async with factory() as session:
            job = await session.get(Job, UUID(hidden))
            job.discovery_visible = False
            await session.commit()
        filters = {
            "direction": "backend",
            "specialty": "python",
            "language": "python",
            "city": "深圳",
            "employmentType": "internship",
            "q": "FastAPI",
            "pageSize": 1,
        }
        page1 = (await client.get("/api/v1/jobs", params=filters)).json()["data"]
        page2 = (await client.get("/api/v1/jobs", params={**filters, "page": 2})).json()["data"]
        assert page1["total"] == page2["total"] == 2
        assert {page1["items"][0]["id"], page2["items"][0]["id"]} == {first, second}
        requirement_only = (
            await client.get("/api/v1/jobs", params={**filters, "q": "需要提供FastAPI"})
        ).json()["data"]
        # Search is now a role/skill/company lookup, not a full-text material search.
        assert requirement_only["total"] == 0
        description_only = (
            await client.get("/api/v1/jobs", params={**filters, "q": "ledger"})
        ).json()["data"]
        assert description_only["total"] == 0
        last = (await client.get("/api/v1/jobs", params={**filters, "page": 99})).json()["data"]
        assert last["page"] == 2 and last["total"] == 2
        empty = (
            await client.get("/api/v1/jobs", params={**filters, "city": "不存在的城市", "page": 99})
        ).json()["data"]
        assert empty == {"items": [], "total": 0, "page": 1, "pageSize": 1}
        java_rows = (
            await client.get("/api/v1/jobs", params={"direction": "backend", "specialty": "java"})
        ).json()["data"]
        assert [x["id"] for x in java_rows["items"]] == [java], "JavaScript is not Java"


async def test_keyword_search_uses_role_identity_not_collaboration_prose(technical_db):
    app, _ = technical_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await register(client, "search-scope@example.com")
        org = await organization(client, "星河合成技术企业")
        backend = await posting(client, org, "Python 后端开发", ["Python", "FastAPI"])
        frontend = await posting(
            client, org, "React 前端开发", ["React", "JavaScript"],
            description="与后端协作，和算法、运维、测试、数据开发团队联调",
            requirements=[{"skillName": "React", "rawText": "与后端协作，提供接口测试反馈"}],
        )
        java = await posting(client, org, "Java 后端开发", ["Java", "Spring Boot"])
        examples = [("测试", "接口测试开发", ["pytest"]),
                    ("数据开发", "数据开发工程师", ["SQL"]),
                    ("算法", "算法工程师", ["Python"]),
                    ("运维", "DevOps 运维工程师", ["Docker"])]
        expected = {term: {await posting(client, org, title, skills)}
                    for term, title, skills in examples}
        expected.update({"后端": {backend, java}, "前端": {frontend},
                         "FastAPI": {backend}, "React": {frontend}, "Java": {java}})
        for term, ids in expected.items():
            result = (await client.get("/api/v1/jobs", params={"q": term})).json()["data"]
            assert {item["id"] for item in result["items"]} == ids, term
            assert result["total"] == len(ids)
        company = (await client.get("/api/v1/jobs", params={"q": "星河"})).json()["data"]
        assert company["total"] == 7
        conflict = (await client.get("/api/v1/jobs", params={
            "q": "后端", "direction": "frontend", "page": 99,
        })).json()["data"]
        assert conflict == {"items": [], "total": 0, "page": 1, "pageSize": 20}


async def test_legacy_unknown_filters_and_management_permissions_survive(technical_db):
    app, _ = technical_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other,
    ):
        await register(owner, "legacy-owner@example.com")
        org = await organization(owner)
        old = await posting(owner, org, "待分类的旧岗位", ["沟通表达"])
        draft = await posting(owner, org, "我的后端草稿", ["Python"], status="draft")
        await register(other, "other-company@example.com")
        other_org = await organization(other)
        foreign = await posting(other, other_org, "他人的后端草稿", ["Python"], status="draft")
        result = (
            await owner.get(
                "/api/v1/jobs",
                params={
                    "direction": "invalid",
                    "specialty": "python",
                    "language": "invalid",
                    "category": "software",
                    "q": "待分类",
                },
            )
        ).json()["data"]
        assert result["total"] == 1 and result["items"][0]["id"] == old
        assert result["items"][0]["careerDirection"] is None
        mine = (await owner.get("/api/v1/jobs/mine")).json()["data"]
        assert {x["id"] for x in mine["items"]} == {old, draft} and foreign not in str(mine)
        assert (await other.get(f"/api/v1/jobs/{draft}")).status_code == 404
        assert (await owner.get(f"/api/v1/jobs/{old}")).status_code == 200


def test_generated_frontend_taxonomy_matches_the_authored_source():
    root = Path(__file__).resolve().parents[3]
    authored = json.loads(
        (root / "backend/app/data/technical-careers.json").read_text(encoding="utf8")
    )
    generated = json.loads(
        (root / "jianli/src/lib/technical-careers.json").read_text(encoding="utf8")
    )
    assert authored == generated
