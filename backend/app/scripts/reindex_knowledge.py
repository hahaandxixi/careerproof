from __future__ import annotations

import asyncio

from sqlalchemy import delete, select
from sqlalchemy import text as sql_text

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.analysis import KnowledgeChunk
from app.models.portfolio import ProjectFile, ResumeSection
from app.services.retrieval import ChunkSource, index_sources
from app.tools.storage import LocalStorage


async def rebuild() -> tuple[int, dict[str, int]]:
    storage = LocalStorage(settings.storage_base_dir)
    async with async_session_factory() as session:
        sections = list(await session.scalars(select(ResumeSection)))
        files = list(await session.scalars(select(ProjectFile)))
        contents = await asyncio.gather(
            *[
                asyncio.to_thread(
                    storage.resolve(file.storage_key).read_text,
                    encoding="utf-8",
                    errors="replace",
                )
                for file in files
            ]
        )
        sources = [
            ChunkSource(
                "resume_section",
                section.id,
                section.content,
                {
                    "resumeVersionId": str(section.resume_version_id),
                    "sectionType": section.section_type,
                    "pageNumber": section.page_number,
                },
            )
            for section in sections
        ]
        sources.extend(
            ChunkSource(
                "project_file",
                file.id,
                content,
                {
                    "projectVersionId": str(file.project_version_id),
                    "path": file.relative_path,
                    "contentHash": file.content_hash,
                    "language": file.language,
                },
            )
            for file, content in zip(files, contents, strict=True)
        )
        await session.execute(delete(KnowledgeChunk))
        count = await index_sources(session, sources)
        await session.commit()
        engines = await session.execute(
            sql_text(
                "SELECT chunk_metadata->>'embeddingEngine' AS engine, COUNT(*) "
                "FROM knowledge_chunks GROUP BY 1"
            )
        )
        return count, {engine: number for engine, number in engines}


if __name__ == "__main__":
    count, engines = asyncio.run(rebuild())
    print(f"indexed_chunks={count} engines={engines}")
