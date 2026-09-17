"""Local, deterministic retrieval index that does not call an external model."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
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

EMBEDDING_DIMENSIONS = 1024
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
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in TOKEN_PATTERN.findall(content.lower()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


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
    created = 0
    for source in sources:
        for index, chunk in enumerate(chunk_text(source.content)):
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
                        "embeddingEngine": "local-hash-v1",
                    },
                    embedding=local_embedding(chunk.content),
                )
            )
            created += 1
    return created


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
        .where(Resume.student_id == student_id)
    )
    project_ids = (
        select(ProjectFile.id)
        .join(ProjectVersion)
        .join(Project)
        .where(Project.student_id == student_id)
    )
    allowed_ids = list(await session.scalars(resume_ids)) + list(await session.scalars(project_ids))
    if not allowed_ids:
        return []
    distance = KnowledgeChunk.embedding.cosine_distance(local_embedding(query))
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
            "metadata": row.chunk_metadata,
        }
        for row in rows
    ]
