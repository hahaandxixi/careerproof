"""Debug the admission query stage by stage on the same synthetic topology."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from probe_version_leak_real_path import build  # noqa: E402

from sqlalchemy import event, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.models.identity import StudentProfile  # noqa: E402
from app.models.portfolio import (  # noqa: E402
    Project,
    ProjectFile,
    ProjectVersion,
    Resume,
    ResumeSection,
    ResumeVersion,
)


async def main() -> int:
    engine = create_async_engine("sqlite+aiosqlite://")

    @event.listens_for(engine.sync_engine, "connect")
    def _register(connection, _record):
        connection.create_function(
            "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    owner_a, ids = await build(factory)

    async with factory() as session:
        student_id = await session.scalar(
            select(StudentProfile.id).where(StudentProfile.user_id == owner_a.user_id)
        )
        print(f"student_id={student_id}")

        print("\n--- raw table contents ---")
        for label, model in (
            ("resumes", Resume),
            ("resume_versions", ResumeVersion),
            ("resume_sections", ResumeSection),
            ("projects", Project),
            ("project_versions", ProjectVersion),
            ("project_files", ProjectFile),
        ):
            count = await session.scalar(select(func.count()).select_from(model))
            print(f"  {label}: {count}")

        print("\n--- resumes rows ---")
        for row in await session.scalars(select(Resume)):
            print(f"  id={row.id} student={row.student_id} archived={row.is_archived}")
        print("--- resume_versions rows ---")
        for row in await session.scalars(select(ResumeVersion)):
            print(f"  id={row.id} resume={row.resume_id} v={row.version_number}")
        print("--- project_versions rows ---")
        for row in await session.scalars(select(ProjectVersion)):
            print(
                f"  id={row.id} project={row.project_id} v={row.version_number} "
                f"role={row.material_role}"
            )

        print("\n--- stage 1: newest_resume derived table ---")
        newest_resume = (
            select(
                ResumeVersion.resume_id.label("resume_id"),
                func.max(ResumeVersion.version_number).label("version_number"),
            )
            .group_by(ResumeVersion.resume_id)
            .subquery()
        )
        rows = (await session.execute(select(newest_resume))).all()
        print(f"  rows={rows}")

        print("\n--- stage 2: resume_versions joined to newest_resume ---")
        stmt = (
            select(ResumeVersion.id)
            .join(Resume, Resume.id == ResumeVersion.resume_id)
            .join(
                newest_resume,
                (newest_resume.c.resume_id == ResumeVersion.resume_id)
                & (newest_resume.c.version_number == ResumeVersion.version_number),
            )
            .where(Resume.student_id == student_id, Resume.is_archived.is_(False))
        )
        print(f"  ids={list(await session.scalars(stmt))}")

        print("\n--- stage 3: newest_project derived table ---")
        newest_project = (
            select(
                ProjectVersion.project_id.label("project_id"),
                ProjectVersion.material_role.label("material_role"),
                func.max(ProjectVersion.version_number).label("version_number"),
            )
            .group_by(ProjectVersion.project_id, ProjectVersion.material_role)
            .subquery()
        )
        rows = (await session.execute(select(newest_project))).all()
        print(f"  rows={rows}")

        print("\n--- stage 4: project_versions joined to newest_project ---")
        stmt = (
            select(ProjectVersion.id)
            .join(Project, Project.id == ProjectVersion.project_id)
            .join(
                newest_project,
                (newest_project.c.project_id == ProjectVersion.project_id)
                & (newest_project.c.material_role == ProjectVersion.material_role)
                & (newest_project.c.version_number == ProjectVersion.version_number),
            )
            .where(Project.student_id == student_id, Project.is_archived.is_(False))
        )
        print(f"  ids={list(await session.scalars(stmt))}")

        print("\n--- stage 5: project_files via those versions ---")
        stmt = select(ProjectFile.id).where(ProjectFile.project_version_id.in_(stmt))
        print(f"  ids={list(await session.scalars(stmt))}")

        print("\n--- compiled SQL of the project_file stage ---")
        from sqlalchemy.dialects import sqlite

        print(stmt.compile(dialect=sqlite.dialect()))

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
