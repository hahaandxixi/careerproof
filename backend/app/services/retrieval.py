"""Local knowledge-chunk embedding and ownership-scoped vector search.

Indexing prefers the pinned local MiniLM ONNX model (real semantic vectors,
384 dimensions) and falls back to a deterministic hash projection when the
model is unavailable. The engine that produced each chunk is stored in
``chunk_metadata.embeddingEngine``; queries resolve the owner's index engine
before embedding the query, because vectors from different engines are not
comparable. ``select_query_engine`` is the pure decision core.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import KnowledgeChunk
from app.models.identity import StudentProfile, User
from app.models.portfolio import (
    Project,
    ProjectFile,
    ProjectVersion,
    Resume,
    ResumeSection,
    ResumeVersion,
)

EMBEDDING_DIMENSIONS = 384
HASH_ENGINE = "local-hash-v1-384"
SEMANTIC_ENGINE = "minilm-l12-v2-onnx"
QUERY_ENGINE_SAMPLE = 50
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.+#-]*|[\u4e00-\u9fff]")


@dataclass(frozen=True)
class ChunkSource:
    source_type: str
    source_id: UUID
    content: str
    metadata: dict


@dataclass(frozen=True)
class TextChunk:
    content: str
    line_start: int
    line_end: int


def chunk_text(content: str, *, max_chars: int = 1400, overlap_lines: int = 2) -> list[TextChunk]:
    lines = content.splitlines() or [content]
    chunks: list[TextChunk] = []
    start = 0
    while start < len(lines) and len(chunks) < 64:
        end = start
        size = 0
        while end < len(lines):
            addition = len(lines[end]) + 1
            if end > start and size + addition > max_chars:
                break
            size += addition
            end += 1
        text = "\n".join(lines[start:end]).strip()
        if text:
            chunks.append(TextChunk(text, start + 1, end))
        if end >= len(lines):
            break
        start = max(start + 1, end - overlap_lines)
    return chunks


def local_embedding(content: str) -> list[float]:
    """Deterministic hash projection of tokens; the fallback, not a semantic model."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in TOKEN_PATTERN.findall(content.lower()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def load_semantic_embedder():
    """Return the pinned local MiniLM embedder, or None when it is unavailable."""
    from app.core.config import settings
    from app.tools.semantic_retrieval import model_available

    if not settings.semantic_retrieval_enabled:
        return None
    if not model_available(settings.semantic_model_cache_dir):
        return None
    try:
        return _cached_embedder(str(settings.semantic_model_cache_dir))
    except (FileNotFoundError, ValueError, OSError):
        return None


@lru_cache(maxsize=1)
def _cached_embedder(cache_dir: str):
    from app.tools.semantic_retrieval import load_local_model

    return load_local_model(Path(cache_dir))


def _valid_vector(vector) -> bool:
    return (
        len(vector) == EMBEDDING_DIMENSIONS
        and all(math.isfinite(float(value)) for value in vector)
    )


def _batch_embeddings(texts: list[str]) -> tuple[list[list[float]], str]:
    """Embed a whole index run with one engine; partial failures fall back wholly."""
    embedder = load_semantic_embedder()
    if embedder is not None:
        try:
            vectors: list[list[float]] = []
            for start in range(0, len(texts), 32):
                vectors.extend(
                    [float(value) for value in vector]
                    for vector in embedder.embed(texts[start : start + 32])
                )
            if len(vectors) == len(texts) and all(_valid_vector(vector) for vector in vectors):
                return vectors, SEMANTIC_ENGINE
        except (OSError, ValueError, RuntimeError):
            pass
    return [local_embedding(text) for text in texts], HASH_ENGINE


def embed_for_index(content: str) -> tuple[list[float], str]:
    vector, engine = _batch_embeddings([content])
    return vector[0], engine


def select_query_engine(
    chunk_engines: list[str], *, semantic_available: bool
) -> tuple[str | None, bool]:
    """Decide the query embedding engine from the owner's indexed chunks.

    ``chunk_engines`` is newest-first. Mixed engines cannot be compared, so the
    newest chunk decides and the caller must surface ``mixed_engines``. When the
    index is semantic but the model is unavailable at query time, vector search
    is skipped (None) rather than answered with incompatible hash vectors.
    """
    if not chunk_engines:
        return None, False
    newest = chunk_engines[0]
    mixed = len(set(chunk_engines)) > 1
    if newest == SEMANTIC_ENGINE and not semantic_available:
        return None, mixed
    if newest not in (SEMANTIC_ENGINE, HASH_ENGINE):
        return None, mixed
    return newest, mixed


async def delete_source_chunks(
    session: AsyncSession, source_type: str, source_ids: list[UUID]
) -> None:
    if source_ids and session.bind.dialect.name == "postgresql":
        await session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.source_type == source_type,
                KnowledgeChunk.source_id.in_(source_ids),
            )
        )


async def index_sources(session: AsyncSession, sources: list[ChunkSource]) -> int:
    if session.bind.dialect.name != "postgresql":
        return 0
    prepared: list[tuple[ChunkSource, int, TextChunk]] = []
    texts: list[str] = []
    for source in sources:
        for index, chunk in enumerate(chunk_text(source.content)):
            prepared.append((source, index, chunk))
            texts.append(chunk.content)
    if not prepared:
        return 0
    embeddings, engine = await asyncio.to_thread(_batch_embeddings, texts)
    for (source, index, chunk), vector in zip(prepared, embeddings, strict=True):
        session.add(
            KnowledgeChunk(
                source_type=source.source_type,
                source_id=source.source_id,
                content=chunk.content,
                chunk_metadata={
                    **source.metadata,
                    "chunkIndex": index,
                    "lineStart": chunk.line_start,
                    "lineEnd": chunk.line_end,
                    "embeddingEngine": engine,
                },
                embedding=vector,
            )
        )
    return len(prepared)


async def _owner_chunk_engines(session: AsyncSession, allowed_ids: list[UUID]) -> list[str]:
    if session.bind.dialect.name != "postgresql":
        return []
    rows = await session.execute(
        select(KnowledgeChunk.chunk_metadata)
        .where(KnowledgeChunk.source_id.in_(allowed_ids))
        .order_by(KnowledgeChunk.created_at.desc())
        .limit(QUERY_ENGINE_SAMPLE)
    )
    engines = []
    for (metadata,) in rows:
        engine = (metadata or {}).get("embeddingEngine")
        if engine:
            engines.append(str(engine))
    return engines


async def search_owned_chunks(
    session: AsyncSession, user: User, query: str, limit: int
) -> list[dict]:
    student_id = await session.scalar(
        select(StudentProfile.id).where(StudentProfile.user_id == user.id)
    )
    if not student_id:
        return []
    resume_ids = (
        select(ResumeSection.id)
        .join(ResumeVersion)
        .join(Resume)
        .where(Resume.student_id == student_id, Resume.is_archived.is_(False))
    )
    project_ids = (
        select(ProjectFile.id)
        .join(ProjectVersion)
        .join(Project)
        .where(Project.student_id == student_id, Project.is_archived.is_(False))
    )
    allowed_ids = list(await session.scalars(resume_ids)) + list(await session.scalars(project_ids))
    if not allowed_ids:
        return []
    engines = await _owner_chunk_engines(session, allowed_ids)
    engine, mixed = select_query_engine(
        engines, semantic_available=load_semantic_embedder() is not None
    )
    if engine is None:
        return []
    if engine == SEMANTIC_ENGINE:
        embedder = load_semantic_embedder()
        if embedder is None:
            return []
        query_vector = await asyncio.to_thread(
            lambda: [float(value) for value in next(iter(embedder.embed([query])))]
        )
        if not _valid_vector(query_vector):
            return []
    else:
        query_vector = local_embedding(query)
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
    rows = list(
        await session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.source_id.in_(allowed_ids))
            .order_by(distance)
            .limit(limit)
        )
    )
    return [
        {
            "id": row.id,
            "sourceType": row.source_type,
            "sourceId": row.source_id,
            "content": row.content,
            "metadata": {
                **row.chunk_metadata,
                "queryEngine": engine,
                "mixedEngines": mixed,
            },
        }
        for row in rows
    ]
