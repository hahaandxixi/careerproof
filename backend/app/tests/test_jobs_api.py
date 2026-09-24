"""HTTP permissions, classification and immutable requirement tests on temporary SQLite."""

import json
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.provider import DeepSeekProvider
from app.core.database import Base, get_session
from app.main import create_app
from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import MembershipRole, TaskStatus
from app.models.identity import EnterpriseMembership
from app.services.job_drafting import validate_draft


@pytest.fixture
async def jobs_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection, _record):
        connection.create_function(
            "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
        )
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[t for t in Base.metadata.sorted_tables if t.name != "knowledge_chunks"],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = session_override
    try:
        yield app, factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def register(client, email, role="enterprise"):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "jobs-test-password",
            "displayName": "测试用户",
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["user"]


async def organization(client, name="真实组织"):
    response = await client.post("/api/v1/enterprises", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_ai_job_draft_requires_confirmation_and_preserves_exact_source(jobs_db, monkeypatch):
    from app.services import job_drafting

    description = "岗位要求：熟练使用 Python 编写数据处理脚本；熟悉 SQL 数据查询优先。"

    async def handler(request):
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert description in body["messages"][1]["content"]
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps({"requirements": [{
                "raw_text": "使用 Python 编写数据处理脚本",
                "skill_name": "Python", "weight": 5, "is_required": True,
                "source_quote": "熟练使用 Python 编写数据处理脚本",
            }]}, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 20},
        })

    monkeypatch.setattr(job_drafting, "get_ai_provider", lambda: DeepSeekProvider(
        api_key="synthetic-key", base_url="https://api.deepseek.com",
        model="deepseek-flash", timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ))
    app, _factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner:
        await register(owner, "draft-owner@example.com")
        org = await organization(owner)
        denied = await owner.post("/api/v1/jobs/ai-draft", json={
            "description": description, "externalAiConsent": False,
        })
        assert denied.status_code == 422
        response = await owner.post("/api/v1/jobs/ai-draft", json={
            "description": description, "externalAiConsent": True,
        })
        assert response.status_code == 200, response.text
        draft = response.json()["data"]
        assert draft["confirmed"] is False
        assert draft["requirements"][0]["sourceQuote"] == description[
            draft["requirements"][0]["sourceStart"]:draft["requirements"][0]["sourceEnd"]
        ]
        assert (await owner.get("/api/v1/jobs/mine")).json()["data"]["total"] == 0
        requirement = draft["requirements"][0]
        invalid = await owner.post("/api/v1/jobs", json=job_payload(
            org, description=description,
            requirements=[{**requirement, "sourceStart": requirement["sourceStart"] + 1}],
        ))
        assert invalid.status_code == 422
        created = await owner.post("/api/v1/jobs", json=job_payload(
            org, status="draft", description=description, requirements=[requirement],
        ))
        assert created.status_code == 201, created.text
        job = created.json()["data"]
        assert job["status"] == "draft"
        assert job["requirements"][0]["sourceQuote"] == requirement["sourceQuote"]
        assert (await owner.patch(f"/api/v1/jobs/{job['id']}", json={
            "description": "全新岗位描述",
        })).status_code == 422
        published = await owner.patch(f"/api/v1/jobs/{job['id']}", json={
            "status": "published",
        })
        assert published.status_code == 200, published.text
        published_source = published.json()["data"]["requirements"][0]["sourceQuote"]
        assert published_source == requirement["sourceQuote"]


def test_ai_job_draft_rejects_invented_source_quote():
    with pytest.raises(ValueError, match="absent from the original"):
        validate_draft({"requirements": [{
            "raw_text": "需要五年经验", "skill_name": "Python",
            "weight": 5, "is_required": True,
            "source_quote": "五年经验",
        }]}, "岗位描述只提到 Python 开发", "synthetic", None)


def job_payload(enterprise, **values):
    return {
        "enterpriseId": enterprise["id"],
        "title": "数据分析实习生",
        "companyName": "伪造公司名",
        "description": "用户调研与数据复盘",
        "status": "published",
        "category": "data_analysis",
        "city": "南京",
        "employmentType": "internship",
        "requirements": [{"rawText": "能够使用Excel分析数据", "skillName": "Excel"}],
        **values,
    }


async def test_owner_creation_public_filters_and_private_drafts(jobs_db):
    app, _factory = jobs_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as owner:
        await register(owner, "owner@example.com")
        org = await organization(owner)
        assert org["role"] == "owner" and org["isVerified"] is False
        assert (await owner.get("/api/v1/enterprises/me")).json()["data"] == [org]
        published = await owner.post("/api/v1/jobs", json=job_payload(org))
        assert published.status_code == 201, published.text
        assert published.json()["data"]["companyName"] == org["name"]
        draft = (await owner.post("/api/v1/jobs", json=job_payload(org, status="draft"))).json()[
            "data"
        ]
        assert (await owner.get(f"/api/v1/jobs/{draft['id']}")).status_code == 200
        assert (await owner.get("/api/v1/jobs/mine")).json()["data"]["total"] == 2
        async with AsyncClient(transport=transport, base_url="http://test") as visitor:
            response = await visitor.get(
                "/api/v1/jobs",
                params={
                    "q": "数据",
                    "category": "data_analysis",
                    "city": "南京",
                    "employmentType": "internship",
                    "pageSize": 1,
                },
            )
            data = response.json()["data"]
            assert data["total"] == 1 and len(data["items"]) == 1
            assert data["items"][0]["requirementCount"] == 1
            assert data["items"][0]["employmentType"] == "internship"
            assert (await visitor.get("/api/v1/jobs", params={"q": "%"})).json()["data"][
                "total"
            ] == 0
            assert (await visitor.get("/api/v1/jobs", params={"city": "北京"})).json()["data"][
                "total"
            ] == 0
            assert (await visitor.get(f"/api/v1/jobs/{draft['id']}")).status_code == 404
            assert (await visitor.post("/api/v1/jobs", json=job_payload(org))).status_code == 401
            assert (await visitor.get("/api/v1/jobs/mine")).status_code == 401
            options = (await visitor.get("/api/v1/jobs/options")).json()["data"]
            assert "operations" in {c["value"] for c in options["categories"]}
            assert "活动策划" in {s["name"] for s in options["skills"]}


async def test_cross_enterprise_student_reviewer_and_inactive_are_denied(jobs_db):
    app, factory = jobs_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as owner:
        await register(owner, "owner@example.com")
        org = await organization(owner)
        draft = (await owner.post("/api/v1/jobs", json=job_payload(org, status="draft"))).json()[
            "data"
        ]
        async with AsyncClient(transport=transport, base_url="http://test") as outsider:
            user = await register(outsider, "outsider@example.com")
            assert (await outsider.post("/api/v1/jobs", json=job_payload(org))).status_code == 403
            assert (await outsider.get(f"/api/v1/jobs/{draft['id']}")).status_code == 404
            assert (
                await outsider.patch(f"/api/v1/jobs/{draft['id']}", json={"status": "published"})
            ).status_code == 404
            assert (await outsider.get("/api/v1/jobs/mine")).json()["data"]["total"] == 0
            async with factory() as session:
                membership = EnterpriseMembership(
                    enterprise_id=UUID(org["id"]),
                    user_id=UUID(user["id"]),
                    role=MembershipRole.REVIEWER,
                    is_active=True,
                )
                session.add(membership)
                await session.commit()
                membership_id = membership.id
            assert (await outsider.post("/api/v1/jobs", json=job_payload(org))).status_code == 403
            async with factory() as session:
                membership = await session.get(EnterpriseMembership, membership_id)
                membership.role = MembershipRole.HR
                membership.is_active = False
                await session.commit()
            assert (await outsider.post("/api/v1/jobs", json=job_payload(org))).status_code == 403
            async with factory() as session:
                membership = await session.get(EnterpriseMembership, membership_id)
                membership.is_active = True
                await session.commit()
            assert (await outsider.post("/api/v1/jobs", json=job_payload(org))).status_code == 201
            assert (
                await outsider.patch(f"/api/v1/jobs/{draft['id']}", json={"status": "published"})
            ).status_code == 200
        async with AsyncClient(transport=transport, base_url="http://test") as student:
            await register(student, "student@example.com", "student")
            assert (
                await student.post("/api/v1/enterprises", json={"name": "拒绝"})
            ).status_code == 403
            assert (await student.post("/api/v1/jobs", json=job_payload(org))).status_code == 403
            assert (await student.get("/api/v1/jobs/mine")).status_code == 403


async def test_updates_lock_requirements_with_match_history(jobs_db):
    app, factory = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner:
        user = await register(owner, "owner@example.com")
        org = await organization(owner)
        job = (await owner.post("/api/v1/jobs", json=job_payload(org))).json()["data"]
        path = f"/api/v1/jobs/{job['id']}"
        new_requirements = [{"rawText": "能够制定活动目标和预算", "skillName": "活动策划"}]
        changed = await owner.patch(
            path, json={"requirements": new_requirements, "category": "operations"}
        )
        assert changed.status_code == 200, changed.text
        requirement_id = changed.json()["data"]["requirements"][0]["id"]
        assert requirement_id != job["requirements"][0]["id"]
        assert (await owner.patch(path, json={"enterpriseId": str(uuid4())})).status_code == 422
        assert (await owner.patch(path, json={"title": None})).status_code == 422
        assert (await owner.patch(path, json={"status": "invalid"})).status_code == 422
        async with factory() as session:
            task = AnalysisTask(
                created_by=UUID(user["id"]),
                task_type="job_match",
                status=TaskStatus.PENDING,
                input_snapshot={"jobId": job["id"]},
            )
            session.add(task)
            await session.commit()
            task_id = task.id
        conflict = await owner.patch(path, json={"requirements": []})
        assert conflict.status_code == 409, conflict.text
        assert (await owner.patch(path, json={"requirements": new_requirements})).status_code == 200
        assert (
            await owner.patch(path, json={"status": "closed", "title": "已关闭岗位"})
        ).status_code == 200
        assert (await owner.get("/api/v1/jobs")).json()["data"]["total"] == 0
        async with factory() as session:
            task = await session.get(AnalysisTask, task_id)
            task.input_snapshot = {}
            task.status = TaskStatus.COMPLETED
            session.add(
                MatchReport(
                    analysis_task_id=task_id,
                    job_id=UUID(job["id"]),
                    candidate_ref="test",
                    overall_score=30,
                    summary="historical report",
                )
            )
            await session.commit()
        assert (await owner.patch(path, json={"requirements": []})).status_code == 409
        async with factory() as session:
            assert await session.scalar(select(MatchReport.id))
