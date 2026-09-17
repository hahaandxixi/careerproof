from __future__ import annotations

import asyncio

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.analysis import KnowledgeChunk
from app.models.portfolio import ProjectFile, ResumeSection
from app.services.retrieval import ChunkSource, index_sources
from app.tools.storage import LocalStorage


async def rebuild() -> int:
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
        return count


if __name__ == "__main__":
    print(f"indexed_chunks={asyncio.run(rebuild())}")
