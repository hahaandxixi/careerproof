"""Z61 reproduction: post-filtered HNSW recall on GET /api/v1/knowledge/search.

Synthetic, offline, disposable-PostgreSQL only (CAREERPROOF_TEST_DATABASE_URL
must point at a throwaway instance; the business database is never touched).
Phase A seeds one student with a small owned chunk set inside a large corpus
whose chunks are all nearer to the query than every owned chunk, records
EXPLAIN (ANALYZE, BUFFERS) for the current query shape plus a no-index-scan
control, and reports the row counts delivered by search_owned_chunks.
Phase B repeats the endpoint path against an empty knowledge_chunks table.

Labelled synthetic throughout; no latency or quality claims are made.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from math import sqrt

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
CORPUS_TEXT = QUERY_TEXT  # every corpus chunk equals the query tokens: distance ~0
OWNED_TOKENS = ["pastry", "chocolat", "mousse", "latte", "butter", "cocoa"]

CORPUS_CHUNKS = 3000
OWNED_SECTIONS = 3
OWNED_CHUNKS_PER_SECTION = 8  # owned total = 24
LIMIT = 10

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def owned_content(index: int) -> str:
    # Unique trailing token per chunk keeps every owned vector distinct so the
    # expected nearest-neighbour order is deterministic.
    return " ".join(OWNED_TOKENS + [f"t{index:04d}"])


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


def make_engine(database_url: str, schema_name: str | None = None):
    server_settings = {"search_path": f'"{schema_name}",public'} if schema_name else {}
    return create_async_engine(
        database_url,
        connect_args={"server_settings": server_settings},
    )


async def create_tables(engine, schema_name: str) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[t for t in Base.metadata.sorted_tables if t.name in REQUIRED_TABLES],
                checkfirst=False,
            )
        )


async def seed(engine, schema_name: str) -> dict:
    rng = random.Random(42)
    corpus_vector = local_embedding(CORPUS_TEXT)
    owned_vectors = [
        local_embedding(owned_content(i))
        for i in range(OWNED_SECTIONS * OWNED_CHUNKS_PER_SECTION)
    ]
    base_time = datetime.now(UTC) - timedelta(hours=2)
    summary: dict = {}
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        user = User(
            email=f"z61-student-{uuid.uuid4().hex}@example.test",
            password_hash="synthetic-not-a-real-hash",
            display_name="Z61 合成学生",
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        profile = StudentProfile(user_id=user.id, school="合成学校", major="软件工程")
        session.add(profile)
        await session.flush()
        section_ids: list = []
        for section_index in range(OWNED_SECTIONS):
            resume = Resume(student_id=profile.id, title=f"Z61 简历 {section_index}", is_archived=False)
            session.add(resume)
            await session.flush()
            version = ResumeVersion(
                resume_id=resume.id,
                version_number=1,
                storage_key=f"synthetic/z61-{section_index}.txt",
                content_hash="c" * 64,
                mime_type="text/plain",
                size_bytes=128,
                parse_status="completed",
            )
            session.add(version)
            await session.flush()
            section = ResumeSection(
                resume_version_id=version.id,
                section_type="skills",
                content=" ".join(
                    owned_content(section_index * OWNED_CHUNKS_PER_SECTION + i)
                    for i in range(OWNED_CHUNKS_PER_SECTION)
                ),
            )
            session.add(section)
            await session.flush()
            section_ids.append(section.id)

        rows = []
        for section_index, section_id in enumerate(section_ids):
            for offset in range(OWNED_CHUNKS_PER_SECTION):
                index = section_index * OWNED_CHUNKS_PER_SECTION + offset
                rows.append((section_id, owned_content(index), owned_vectors[index]))
        for _ in range(CORPUS_CHUNKS):
            corpus_id = uuid.UUID(int=rng.getrandbits(128), version=4)
            rows.append((corpus_id, CORPUS_TEXT, corpus_vector))
        # deterministic created_at ordering with a hash-engine newest chunk
        for position, (source_id, content, vector) in enumerate(rows):
            session.add(
                KnowledgeChunk(
                    source_type="resume_section",
                    source_id=source_id,
                    content=content,
                    chunk_metadata={
                        "chunkIndex": position,
                        "lineStart": 1,
                        "lineEnd": 1,
                        "embeddingEngine": HASH_ENGINE,
                    },
                    embedding=vector,
                    created_at=base_time + timedelta(seconds=position),
                )
            )
        await session.commit()
        summary["total_chunks"] = await session.scalar(
            select(func.count()).select_from(KnowledgeChunk)
        )
        summary["owned_chunks"] = OWNED_SECTIONS * OWNED_CHUNKS_PER_SECTION
        summary["allowed_ids"] = len(section_ids)
    return summary



async def collect_plans(database_url: str, schema_name: str) -> None:
    """EXPLAIN runs on a dedicated engine+connection so SET state can never
    leak into pooled connections used by the delivery-count or search steps."""
    query_vector = vector_literal(local_embedding(QUERY_TEXT))
    engine = make_engine(database_url, schema_name)
    try:
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            # pgvector registers its GUCs when the library first loads in a backend
            await session.execute(text("LOAD 'vector'"))
            print("hnsw.ef_search =", (await session.execute(text("SHOW hnsw.ef_search"))).scalar())
            print(
                "hnsw.iterative_scan =",
                (await session.execute(text("SHOW hnsw.iterative_scan"))).scalar(),
            )
            indexes = await session.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname=:s AND tablename='knowledge_chunks'"
                ),
                {"s": schema_name},
            )
            for name, definition in indexes:
                print("index:", name, "::", definition)
            allowed_ids = list(await session.scalars(select(ResumeSection.id)))
            print(f"allowed_ids in filter: {len(allowed_ids)}")

        plans: dict[str, list[str]] = {}
        shapes: dict[str, str] = {
            "flat": (
                "SELECT knowledge_chunks.id FROM knowledge_chunks "
                "WHERE knowledge_chunks.source_id = ANY(:ids) "
                "ORDER BY knowledge_chunks.embedding <=> (:q)::vector LIMIT :lim"
            ),
            # a plain subquery can be inlined back into the post-filtered plan
            "subquery": (
                "SELECT t.id FROM (SELECT k.id, k.embedding FROM knowledge_chunks k "
                "WHERE k.source_id = ANY(:ids)) t "
                "ORDER BY t.embedding <=> (:q)::vector LIMIT :lim"
            ),
            # MATERIALIZED forces the filter to complete before ranking
            "materialized-cte": (
                "WITH allowed AS MATERIALIZED (SELECT k.id, k.embedding FROM knowledge_chunks k "
                "WHERE k.source_id = ANY(:ids)) "
                "SELECT a.id FROM allowed a ORDER BY a.embedding <=> (:q)::vector LIMIT :lim"
            ),
        }
        for label, disable in (("default", False), ("no-indexscan", True)):
            async with engine.connect() as connection:
                if disable:
                    await connection.execute(text("SET enable_indexscan = off"))
                    await connection.execute(text("SET enable_bitmapscan = off"))
                await connection.commit()
                plan_rows = await connection.execute(
                    text("EXPLAIN (ANALYZE, BUFFERS) " + shapes["flat"]),
                    {"ids": allowed_ids, "q": query_vector, "lim": LIMIT},
                )
                plans[label] = [row[0] for row in plan_rows]
                delivered = await connection.execute(
                    text(shapes["flat"]),
                    {"ids": allowed_ids, "q": query_vector, "lim": LIMIT},
                )
                raw_ids = [str(row[0]) for row in delivered]
                await connection.commit()
            print(f"--- control '{label}': raw statement delivered {len(raw_ids)} rows: {raw_ids} ---")
            for line in plans[label]:
                print(line)
        for label in ("subquery", "materialized-cte"):
            async with engine.connect() as connection:
                plan_rows = await connection.execute(
                    text("EXPLAIN (ANALYZE, BUFFERS) " + shapes[label]),
                    {"ids": allowed_ids, "q": query_vector, "lim": LIMIT},
                )
                plans[label] = [row[0] for row in plan_rows]
                delivered = await connection.execute(
                    text(shapes[label]),
                    {"ids": allowed_ids, "q": query_vector, "lim": LIMIT},
                )
                raw_ids = [str(row[0]) for row in delivered]
            print(f"--- fix-shape '{label}': delivered {len(raw_ids)} rows ---")
            for line in plans[label]:
                print(line)
    finally:
        await engine.dispose()
    for label, lines in plans.items():
        with open(os.path.join(OUT_DIR, f"plan-A-{label}.txt"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


async def brute_force_top_owned(engine) -> list[str]:
    query_vector = local_embedding(QUERY_TEXT)

    def cosine_distance(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sqrt(sum(x * x for x in a))
        nb = sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 1.0
        return 1.0 - dot / (na * nb)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        rows = await session.execute(
            select(KnowledgeChunk.id, KnowledgeChunk.embedding).where(
                KnowledgeChunk.source_id.in_(select(ResumeSection.id))
            )
        )
        scored = [(str(row[0]), cosine_distance(query_vector, list(row[1]))) for row in rows]
    scored.sort(key=lambda item: item[1])
    return [item[0] for item in scored[:LIMIT]]


async def run_seeded_phase(database_url: str, schema_name: str) -> None:
    print(f"=== PHASE A: seeded corpus, schema {schema_name} (synthetic) ===")
    engine = make_engine(database_url, schema_name)
    try:
        await create_tables(engine, schema_name)
        summary = await seed(engine, schema_name)
        print("dataset:", summary)
        await collect_plans(database_url, schema_name)
        expected = await brute_force_top_owned(engine)
        print(f"brute-force expected top-{LIMIT} owned ids: {expected}")
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            user = await session.scalar(select(User).where(User.display_name == "Z61 合成学生"))
            results = await search_owned_chunks(session, user, QUERY_TEXT, LIMIT)
            delivered_ids = [str(r["id"]) for r in results]
            print(f"search_owned_chunks delivered: {len(results)}")
            print("search ids:", delivered_ids)
            owned_total = summary["owned_chunks"]
            expected_count = min(LIMIT, owned_total)
            print(
                f"acceptance target: count==min(limit={LIMIT}, owned_hit_count={owned_total})"
                f"=={expected_count}; exact brute-force order match: {delivered_ids == expected}"
            )
    finally:
        await engine.dispose()


async def run_empty_phase(database_url: str) -> None:
    schema_name = f"cp_test_z61_empty_{uuid.uuid4().hex}"
    bootstrap = make_engine(database_url)
    try:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    finally:
        await bootstrap.dispose()
    engine = make_engine(database_url, schema_name)
    try:
        print(f"=== PHASE B: empty knowledge_chunks, schema {schema_name} (synthetic) ===")
        await create_tables(engine, schema_name)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            user = User(
                email=f"z61-empty-{uuid.uuid4().hex}@example.test",
                password_hash="synthetic-not-a-real-hash",
                display_name="Z61 空表学生",
                role=UserRole.STUDENT,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            profile = StudentProfile(user_id=user.id, school="合成学校", major="软件工程")
            session.add(profile)
            await session.flush()
            resume = Resume(student_id=profile.id, title="Z61 空表", is_archived=False)
            session.add(resume)
            await session.flush()
            version = ResumeVersion(
                resume_id=resume.id,
                version_number=1,
                storage_key="synthetic/z61-empty.txt",
                content_hash="d" * 64,
                mime_type="text/plain",
                size_bytes=16,
                parse_status="completed",
            )
            session.add(version)
            await session.flush()
            session.add(
                ResumeSection(
                    resume_version_id=version.id, section_type="skills", content="pastry chocolat"
                )
            )
            await session.commit()
            total = await session.scalar(select(func.count()).select_from(KnowledgeChunk))
            results = await search_owned_chunks(session, user, QUERY_TEXT, LIMIT)
            print(
                f"knowledge_chunks rows={total}; allowed sources exist; "
                f"search_owned_chunks delivered={len(results)}"
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await engine.dispose()



async def main() -> int:
    database_url = os.environ.get("CAREERPROOF_TEST_DATABASE_URL")
    if not database_url:
        print("CAREERPROOF_TEST_DATABASE_URL must point at a disposable PostgreSQL", file=sys.stderr)
        return 2
    if not re.match(r"postgresql\+asyncpg://", database_url):
        print("refusing non-asyncpg PostgreSQL URL", file=sys.stderr)
        return 2
    schema_name = f"cp_test_z61_repro_{uuid.uuid4().hex}"
    engine = make_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    finally:
        await engine.dispose()
    try:
        await run_seeded_phase(database_url, schema_name)
    finally:
        engine = make_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        finally:
            await engine.dispose()
    await run_empty_phase(database_url)
    print("=== reproduction complete (synthetic data, disposable instance) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
