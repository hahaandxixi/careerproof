"""PostgreSQL-only verification of semantic knowledge indexing and search.

Runs against the explicitly configured integration database
(CAREERPROOF_TEST_DATABASE_URL) with an isolated per-test schema. The embedder
is replaced with a deterministic fake so no model download is required; the
test proves engine routing, metadata propagation, mixed-engine surfacing and
the honest skip when the model is unavailable at query time.
"""

from __future__ import annotations

import os
import re
from datetime import UTC
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.models.analysis import KnowledgeChunk
from app.models.enums import UserRole
from app.models.identity import StudentProfile, User
from app.models.portfolio import Resume, ResumeSection, ResumeVersion
from app.services import retrieval
from app.services.retrieval import (
    HASH_ENGINE,
    SEMANTIC_ENGINE,
    ChunkSource,
    index_sources,
    search_owned_chunks,
)

REQUIRED_TABLES = {
    "users",
    "student_profiles",
    "resumes",
    "resume_versions",
    "resume_sections",
    "projects",
    "project_versions",
    "project_files",
    "knowledge_chunks",
}


@pytest.fixture
async def knowledge_db(monkeypatch):
    database_url = os.environ.get("CAREERPROOF_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Requires an explicitly configured isolated PostgreSQL schema")
    assert database_url.startswith("postgresql+asyncpg://")
    schema_name = f"cp_test_{uuid4().hex}"
    assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema_name)
    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": f"{schema_name},public"}},
    )
    created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(sql_text(f'CREATE SCHEMA "{schema_name}"'))
        created = True
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[
                        table
                        for table in Base.metadata.sorted_tables
                        if table.name in REQUIRED_TABLES
                    ],
                    checkfirst=False,
                )
            )
        monkeypatch.setattr(settings, "storage_base_dir", None)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        if created:
            assert re.fullmatch(r"cp_test_[0-9a-f]{32}", schema_name)
            async with engine.begin() as connection:
                await connection.execute(sql_text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await engine.dispose()


class FakeSemanticEmbedder:
    """Deterministic stand-in reusing the hash projection; engine tags differ."""

    def embed(self, documents: list[str]):
        for document in documents:
            yield retrieval.local_embedding(document)


async def _seed_resume(factory, *, suffix: str, content: str, content_hash: str):
    async with factory() as session:
        user = User(
            email=f"student-{uuid4().hex}@example.test",
            password_hash="synthetic-not-a-real-hash",
            display_name="检索测试学生",
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        profile = StudentProfile(user_id=user.id, school="合成学校", major="软件工程")
        session.add(profile)
        await session.flush()
        resume = Resume(student_id=profile.id, title=f"检索测试简历{suffix}", is_archived=False)
        session.add(resume)
        await session.flush()
        version = ResumeVersion(
            resume_id=resume.id,
            version_number=1,
            storage_key=f"synthetic/{suffix}.txt",
            content_hash=content_hash,
            mime_type="text/plain",
            size_bytes=len(content.encode("utf-8")),
            parse_status="completed",
        )
        session.add(version)
        await session.flush()
        section = ResumeSection(
            resume_version_id=version.id,
            section_type="skills",
            content=content,
        )
        session.add(section)
        await session.commit()
        return user.id, section.id, version.id


async def _index_section(factory, section_id: UUID, version_id: UUID, content: str) -> int:
    async with factory() as session:
        count = await index_sources(
            session,
            [
                ChunkSource(
                    "resume_section",
                    section_id,
                    content,
                    {"resumeVersionId": str(version_id), "sectionType": "skills"},
                )
            ],
        )
        await session.commit()
        return count


async def test_semantic_index_and_search_flow(knowledge_db, monkeypatch):
    monkeypatch.setattr(retrieval, "load_semantic_embedder", lambda: FakeSemanticEmbedder())
    content = "熟练掌握 FastAPI 后端开发与 PostgreSQL 数据库设计，做过订单服务的查询优化。"
    user_id, section_id, version_id = await _seed_resume(
        knowledge_db, suffix="one", content=content, content_hash="a" * 64
    )
    assert await _index_section(knowledge_db, section_id, version_id, content) >= 1

    async with knowledge_db() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        results = await search_owned_chunks(session, user, "FastAPI 数据库开发", 5)
        assert results, "semantic index should return owned chunks"
        assert all(result["metadata"]["embeddingEngine"] == SEMANTIC_ENGINE for result in results)
        assert all(result["metadata"]["queryEngine"] == SEMANTIC_ENGINE for result in results)
        assert all(result["metadata"]["mixedEngines"] is False for result in results)
        assert all(
            "FastAPI" in result["content"] or "PostgreSQL" in result["content"]
            for result in results
        )


async def test_mixed_engines_and_unavailable_model_skip(knowledge_db, monkeypatch):
    monkeypatch.setattr(retrieval, "load_semantic_embedder", lambda: FakeSemanticEmbedder())
    # 两段各约 900 字的内容保证产生 >=2 个 chunk，才能构造真实的混合引擎索引。
    content = "\n".join(
        [
            ("参与数据可视化平台的性能优化与缓存改造，负责图表渲染链路与数据聚合接口。") * 30,
            ("维护 PostgreSQL 数据库的索引设计与慢查询治理，编写自动化巡检脚本。") * 30,
        ]
    )
    user_id, section_id, version_id = await _seed_resume(
        knowledge_db, suffix="two", content=content, content_hash="b" * 64
    )
    assert await _index_section(knowledge_db, section_id, version_id, content) >= 2

    async with knowledge_db() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        results = await search_owned_chunks(session, user, "数据可视化 性能优化", 10)
        assert results

        # 显式构造混合状态：最新块哈希引擎、其余语义引擎；时间戳手动错开保证确定性。
        from datetime import datetime, timedelta

        chunks = list(
            await session.scalars(
                select(KnowledgeChunk).order_by(KnowledgeChunk.created_at.asc())
            )
        )
        assert len(chunks) >= 2
        base = datetime.now(UTC) - timedelta(hours=1)
        for offset, chunk in enumerate(chunks):
            chunk.created_at = base + timedelta(seconds=offset)
            chunk.updated_at = chunk.created_at
            chunk.chunk_metadata = {
                **chunk.chunk_metadata,
                "embeddingEngine": HASH_ENGINE if offset == len(chunks) - 1 else SEMANTIC_ENGINE,
            }
        await session.commit()

        mixed_results = await search_owned_chunks(session, user, "数据可视化 性能优化", 10)
        assert mixed_results
        assert all(result["metadata"]["queryEngine"] == HASH_ENGINE for result in mixed_results)
        assert all(result["metadata"]["mixedEngines"] for result in mixed_results)

        # 把全部块恢复为语义引擎后，查询时模型不可用必须整体跳过向量检索，
        # 而不是用不可比的哈希向量冒充语义查询结果。
        for chunk in chunks:
            chunk.chunk_metadata = {
                **chunk.chunk_metadata,
                "embeddingEngine": SEMANTIC_ENGINE,
            }
        await session.commit()
        monkeypatch.setattr(retrieval, "load_semantic_embedder", lambda: None)
        assert await search_owned_chunks(session, user, "数据可视化 性能优化", 10) == []
