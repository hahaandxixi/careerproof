"""PostgreSQL-only acceptance for ownership-filtered vector recall.

The endpoint behind GET /api/v1/knowledge/search must rank inside the
student's allowed subset: with owned hits present it returns exactly
``min(limit, owned_hit_count)`` rows, and those rows are the true nearest
among the owned set (verified against brute force computed in this test),
regardless of which plan PostgreSQL picks for the distance ordering.

Runs against the explicitly configured integration database
(CAREERPROOF_TEST_DATABASE_URL) with an isolated per-test schema; all data is
synthetic and the HNSW planner behaviour is exercised through the public
``search_owned_chunks`` service only.
"""

from __future__ import annotations

import logging
import math
import os
import random
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.models.analysis import KnowledgeChunk
from app.models.enums import UserRole
from app.models.identity import StudentProfile, User
from app.models.portfolio import Resume, ResumeSection, ResumeVersion
from app.services.retrieval import HASH_ENGINE, local_embedding, search_owned_chunks

REQUIRED_TABLES = {
    "users",
    "analysis_tasks",
    "student_profiles",
    "resumes",
    "resume_versions",
    "resume_sections",
    "projects",
    "project_versions",
    "project_files",
    "knowledge_chunks",
}

QUERY_TEXT = "kubernetes prometheus observability alerting fleet"
CORPUS_TEXT = QUERY_TEXT  # corpus chunks equal the query tokens: nearest globally
OWNED_TOKENS = ["pastry", "chocolat", "mousse", "latte", "butter", "cocoa"]
DISTANCE_TOLERANCE = 1e-9


@pytest.fixture
async def recall_db(monkeypatch):
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
            assert await connection.scalar(sql_text("SELECT current_schema()")) == schema_name
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


def settings_storage_base_dir():
    from app.core.config import settings

    return settings


async def _create_student(factory, display_name: str) -> UUID:
    """One student owning ``section_count`` resume sections; returns user id."""
    async with factory() as session:
        user = User(
            email=f"z61-{display_name}-{uuid4().hex}@example.test",
            password_hash="synthetic-not-a-real-hash",
            display_name=display_name,
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        profile = StudentProfile(user_id=user.id, school="合成学校", major="软件工程")
        session.add(profile)
        await session.commit()
        return user.id


async def _add_owned_section(factory, user_id: UUID, section_index: int, content: str) -> UUID:
    async with factory() as session:
        profile_id = await session.scalar(
            select(StudentProfile.id).where(StudentProfile.user_id == user_id)
        )
        resume = Resume(
            student_id=profile_id, title=f"Z61 简历 {section_index}", is_archived=False
        )
        session.add(resume)
        await session.flush()
        version = ResumeVersion(
            resume_id=resume.id,
            version_number=section_index + 1,
            storage_key=f"synthetic/z61-{uuid4().hex}.txt",
            content_hash="c" * 64,
            mime_type="text/plain",
            size_bytes=len(content.encode("utf-8")),
            parse_status="completed",
        )
        session.add(version)
        await session.flush()
        section = ResumeSection(
            resume_version_id=version.id, section_type="skills", content=content
        )
        session.add(section)
        await session.commit()
        return section.id


async def _add_chunks(
    factory,
    source_id: UUID,
    contents: list[str],
    *,
    base_time: datetime,
    offset: int = 0,
    engine_tag: str = HASH_ENGINE,
) -> None:
    async with factory() as session:
        for position, content in enumerate(contents):
            session.add(
                KnowledgeChunk(
                    source_type="resume_section",
                    source_id=source_id,
                    content=content,
                    chunk_metadata={
                        "chunkIndex": offset + position,
                        "lineStart": 1,
                        "lineEnd": 1,
                        "embeddingEngine": engine_tag,
                    },
                    embedding=local_embedding(content),
                    created_at=base_time + timedelta(seconds=offset + position),
                )
            )
        await session.commit()


async def _add_corpus(factory, count: int, rng: random.Random, base_time: datetime) -> None:
    async with factory() as session:
        for position in range(count):
            session.add(
                KnowledgeChunk(
                    source_type="resume_section",
                    source_id=uuid4(),
                    content=CORPUS_TEXT,
                    chunk_metadata={
                        "chunkIndex": position,
                        "lineStart": 1,
                        "lineEnd": 1,
                        "embeddingEngine": HASH_ENGINE,
                    },
                    embedding=local_embedding(CORPUS_TEXT),
                    created_at=base_time + timedelta(seconds=position),
                )
            )
        await session.commit()


async def _owned_distances(
    session, user: User
) -> tuple[dict[UUID, float], set[UUID]]:
    """Brute-force reference: cosine distance from the query to every owned
    chunk, keyed by chunk id, plus the set of owned source ids."""
    profile_id = await session.scalar(
        select(StudentProfile.id).where(StudentProfile.user_id == user.id)
    )
    owned_source_ids = set(
        await session.scalars(
            select(ResumeSection.id)
            .join(ResumeVersion)
            .join(Resume)
            .where(Resume.student_id == profile_id)
        )
    )
    rows = await session.execute(
        select(KnowledgeChunk.id, KnowledgeChunk.source_id, KnowledgeChunk.embedding).where(
            KnowledgeChunk.source_id.in_(owned_source_ids)
        )
    )
    query_vector = local_embedding(QUERY_TEXT)
    scored: dict[UUID, float] = {}
    for chunk_id, _source_id, embedding in rows:
        scored[chunk_id] = cosine_distance(query_vector, list(embedding))
    return scored, owned_source_ids


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def _assert_true_nearest(
    delivered_ids: list[UUID], owned: dict[UUID, float], limit: int
) -> None:
    """delivered must be the true top-k of the owned set, ties broken freely.

    Equal-distance ties are legitimate (distinct tokens can hash to positions
    that leave the query overlap unchanged), so ordering inside a tie group is
    plan-dependent and never asserted; what must hold is: the k delivered
    distances are the k smallest, and the delivered order is non-decreasing.
    """
    expected_k = min(limit, len(owned))
    assert len(delivered_ids) == expected_k
    delivered_distances = [owned[chunk_id] for chunk_id in delivered_ids]
    assert all(
        delivered_distances[i] <= delivered_distances[i + 1] + DISTANCE_TOLERANCE
        for i in range(len(delivered_distances) - 1)
    )
    sorted_distances = sorted(owned.values())
    cutoff = sorted_distances[expected_k - 1]
    assert max(delivered_distances) <= cutoff + DISTANCE_TOLERANCE
    # every distance strictly smaller than the cutoff must have been delivered
    must_deliver = {
        chunk for chunk, distance in owned.items() if distance < cutoff - DISTANCE_TOLERANCE
    }
    assert must_deliver.issubset(set(delivered_ids))


async def _seed_adversarial(
    factory, *, sections: int, chunks_per_section: int, corpus: int
) -> tuple[UUID, int]:
    """Student owns few far-from-query chunks inside a large near-query corpus."""
    user_id = await _create_student(factory, "Z61 召回学生")
    rng = random.Random(42)
    base_time = datetime.now(UTC) - timedelta(hours=2)
    owned_total = 0
    for section_index in range(sections):
        contents = [
            " ".join(OWNED_TOKENS + [f"t{section_index:04d}-{chunk:04d}"])
            for chunk in range(chunks_per_section)
        ]
        section_id = await _add_owned_section(
            factory, user_id, section_index, " ".join(contents)
        )
        await _add_chunks(
            factory,
            section_id,
            contents,
            base_time=base_time,
            offset=owned_total,
        )
        owned_total += len(contents)
    await _add_corpus(factory, corpus, rng, base_time - timedelta(minutes=1))
    return user_id, owned_total


async def test_selective_filter_returns_exact_topk(recall_db):
    user_id, owned_total = await _seed_adversarial(
        recall_db, sections=3, chunks_per_section=8, corpus=3000
    )
    assert owned_total == 24
    async with recall_db() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        results = await search_owned_chunks(session, user, QUERY_TEXT, 10)
        # the poisoned corpus is globally nearer; only exact pre-filtered
        # ranking can still deliver the full min(limit, owned) window
        assert len(results) == min(10, owned_total) == 10
        owned, owned_sources = await _owned_distances(session, user)
        assert len(owned) == owned_total
        _assert_true_nearest([result["id"] for result in results], owned, 10)
        assert all(result["sourceId"] in owned_sources for result in results)
        assert all(
            set(result) == {"id", "sourceType", "sourceId", "content", "metadata"}
            for result in results
        )
        for result in results:
            metadata = result["metadata"]
            assert metadata["requested"] == 10
            assert metadata["delivered"] == 10
            assert metadata["ownedMatches"] == owned_total
            assert metadata["shortfall"] is False
            assert metadata["queryEngine"] == HASH_ENGINE
            assert metadata["mixedEngines"] is False


async def test_single_owned_source_partial_window(recall_db):
    user_id, owned_total = await _seed_adversarial(
        recall_db, sections=1, chunks_per_section=3, corpus=3000
    )
    assert owned_total == 3
    async with recall_db() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        results = await search_owned_chunks(session, user, QUERY_TEXT, 5)
        # owned corpus smaller than the limit: delivered == owned, and a small
        # corpus is not a shortfall
        assert len(results) == min(5, owned_total) == 3
        owned, _owned_sources = await _owned_distances(session, user)
        _assert_true_nearest([result["id"] for result in results], owned, 5)
        for result in results:
            metadata = result["metadata"]
            assert metadata["requested"] == 5
            assert metadata["delivered"] == 3
            assert metadata["ownedMatches"] == 3
            assert metadata["shortfall"] is False


async def test_large_allowed_ids_list(recall_db):
    # 250 owned sections make the source_id IN (...) list large while most
    # sections carry no chunks at all
    user_id, owned_total = await _seed_adversarial(
        recall_db, sections=250, chunks_per_section=2, corpus=3000
    )
    assert owned_total == 500
    async with recall_db() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        allowed = await session.scalar(
            select(func.count()).select_from(ResumeSection)
        )
        assert allowed == 250
        results = await search_owned_chunks(session, user, QUERY_TEXT, 8)
        assert len(results) == min(8, owned_total) == 8
        owned, _owned_sources = await _owned_distances(session, user)
        _assert_true_nearest([result["id"] for result in results], owned, 8)
        assert all(result["metadata"]["shortfall"] is False for result in results)


async def test_empty_index_distinct_from_shortfall(recall_db, caplog):
    user_id = await _create_student(recall_db, "Z61 空表学生")
    await _add_owned_section(recall_db, user_id, 0, " ".join(OWNED_TOKENS))
    async with recall_db() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        with caplog.at_level(logging.INFO, logger="app.services.retrieval"):
            results = await search_owned_chunks(session, user, QUERY_TEXT, 8)
        assert results == []
        empty_lines = [
            record.getMessage()
            for record in caplog.records
            if '"outcome": "no-indexed-chunks"' in record.getMessage()
        ]
        assert empty_lines, "empty index must be observable as its own outcome"
        assert '"delivered": 0' in empty_lines[-1]
        assert '"requested": 8' in empty_lines[-1]

    # contrast: with owned hits the same query logs a normal outcome with
    # nonzero ownedMatches, so "index never populated" and "ranked search" are
    # distinguishable to the caller's logs
    rng = random.Random(42)
    base_time = datetime.now(UTC) - timedelta(hours=1)
    async with recall_db() as session:
        profile_id = await session.scalar(
            select(StudentProfile.id).where(StudentProfile.user_id == user_id)
        )
        section_id = await session.scalar(
            select(ResumeSection.id)
            .join(ResumeVersion)
            .join(Resume)
            .where(Resume.student_id == profile_id)
        )
    await _add_chunks(
        recall_db,
        section_id,
        [" ".join(OWNED_TOKENS + ["t-empty-0001"])],
        base_time=base_time,
    )
    await _add_corpus(recall_db, 3000, rng, base_time - timedelta(minutes=1))
    caplog.clear()
    async with recall_db() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        with caplog.at_level(logging.INFO, logger="app.services.retrieval"):
            results = await search_owned_chunks(session, user, QUERY_TEXT, 8)
        assert len(results) == 1
        ranked_lines = [
            record.getMessage()
            for record in caplog.records
            if '"outcome": "ok"' in record.getMessage()
        ]
        assert ranked_lines, "ranked search must log its counters"
        assert '"ownedMatches": 1' in ranked_lines[-1]
        assert '"delivered": 1' in ranked_lines[-1]
