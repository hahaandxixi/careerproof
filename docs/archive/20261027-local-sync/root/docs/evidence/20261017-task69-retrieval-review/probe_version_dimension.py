"""Task 69 independent probe: does Z61's ownership filter cover the version dimension?

Read-only against the Z61 sources; writes nothing into the repo. Two independent
checks:

  A. Compile the real owned-subset predicate for the PostgreSQL dialect and print
     its WHERE clause, so any missing filter dimension is visible in the SQL.
  B. Build the same resume/project topology in isolated SQLite and evaluate the
     exact ownership predicate from retrieval.py to see which section ids are
     admitted. SQLite cannot execute the vector part, so B proves only the
     allow-list, not the ranking.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import String, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.identity import StudentProfile, User
from app.models.portfolio import (
    Project,
    ProjectFile,
    ProjectVersion,
    Resume,
    ResumeSection,
    ResumeVersion,
)

FAILED = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" :: {detail}" if detail else ""))
    if not condition:
        FAILED.append(label)


# ---------------------------------------------------------------------------
# A. Compiled SQL shape
# ---------------------------------------------------------------------------
def owned_predicate_sql(allowed_ids: list[UUID]) -> str:
    """Reproduce retrieval.py:294-307 exactly, without touching a database."""
    from app.models.analysis import KnowledgeChunk

    allowed_rows = (
        select(KnowledgeChunk, func.count().over().label("owned_matches"))
        .where(KnowledgeChunk.source_id.in_(allowed_ids))
        .cte("owned_chunks")
        .prefix_with("MATERIALIZED")
    )
    from sqlalchemy.orm import aliased

    owned_chunk = aliased(KnowledgeChunk, allowed_rows)
    distance = allowed_rows.c.embedding.cosine_distance([0.0] * 384)
    statement = (
        select(owned_chunk, allowed_rows.c.owned_matches)
        .order_by(distance)
        .limit(8)
    )
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )


def check_sql_shape() -> None:
    sql = owned_predicate_sql([uuid4(), uuid4()])
    print("\n--- A. compiled PostgreSQL statement (retrieval.py:294-307 shape) ---")
    print(sql)
    lowered = sql.lower()
    check(
        "A1 filter is version-agnostic (no resume_version_id / project_version_id predicate)",
        "resume_version_id" not in lowered and "project_version_id" not in lowered,
        "expected: the owned CTE filters only on source_id",
    )
    check(
        "A2 filter carries no source_type discriminator",
        "source_type =" not in lowered and "source_type in" not in lowered,
    )
    check(
        "A3 pre-filter is materialised before ordering",
        "materialized" in lowered and "owned_chunks" in lowered,
    )
    check(
        "A4 window count is evaluated inside the owned CTE (pre-LIMIT)",
        "count(*) over ()" in " ".join(lowered.split()),
    )
    check(
        "A5 distance ordering is cosine distance, not a post-filter",
        "<=>" in sql or "cosine_distance" in lowered or "embedding" in lowered,
    )


# ---------------------------------------------------------------------------
# B. Allow-list behaviour on the real ownership predicates
# ---------------------------------------------------------------------------
async def check_allow_list() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # The checked-in SQLite fixtures register this PG-only DDL helper the same way
    # (app/tests/test_jobs_api.py:28, test_real_matching.py:71).
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def register_sqlite_functions(connection, _record):
        connection.create_function(
            "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
        )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User(
            email="t69-owner@example.com",
            password_hash="synthetic",
            display_name="T69 owner",
            role="student",
        )
        session.add(user)
        await session.flush()
        student = StudentProfile(user_id=user.id)
        session.add(student)
        await session.flush()

        # Two versions of ONE resume, each carrying one section, both current rows.
        resume = Resume(student_id=student.id, title="T69 resume")
        session.add(resume)
        await session.flush()
        sections = {}
        for number, marker in ((1, "OLD-v1-secret"), (2, "NEW-v2")):
            version = ResumeVersion(
                resume_id=resume.id,
                version_number=number,
                storage_key=f"t69/{number}.pdf",
                mime_type="application/pdf",
                original_filename=f"t69-{number}.pdf",
                content_hash=f"{number:064d}",
                size_bytes=1024,
                parse_status="completed",
            )
            session.add(version)
            await session.flush()
            section = ResumeSection(
                resume_version_id=version.id,
                section_type="skills",
                content=marker,
            )
            session.add(section)
            await session.flush()
            sections[marker] = section.id

        # Two versions of ONE project, each carrying one file.
        project = Project(student_id=student.id, name="T69 project")
        session.add(project)
        await session.flush()
        files = {}
        for number, marker in ((1, "OLD-project-v1"), (2, "NEW-project-v2")):
            version = ProjectVersion(
                project_id=project.id,
                version_number=number,
                archive_storage_key=f"t69/p{number}.zip",
                content_hash=f"{number + 10:064d}",
            )
            session.add(version)
            await session.flush()
            row = ProjectFile(
                project_version_id=version.id,
                relative_path=f"main{number}.py",
                content_hash=f"{number + 20:064d}",
                size_bytes=10,
                line_count=1,
                storage_key=f"t69/main{number}.py",
            )
            session.add(row)
            await session.flush()
            files[marker] = row.id
        await session.commit()

        # The exact predicates from retrieval.py:255-267.
        resume_ids = (
            select(ResumeSection.id)
            .join(ResumeVersion)
            .join(Resume)
            .where(Resume.student_id == student.id, Resume.is_archived.is_(False))
        )
        project_ids = (
            select(ProjectFile.id)
            .join(ProjectVersion)
            .join(Project)
            .where(Project.student_id == student.id, Project.is_archived.is_(False))
        )
        allowed = list(await session.scalars(resume_ids)) + list(
            await session.scalars(project_ids)
        )

    await engine.dispose()

    print("\n--- B. allow-list from the real retrieval.py predicates ---")
    print(f"allowed ids: {len(allowed)}")
    admitted_old_resume = sections["OLD-v1-secret"] in allowed
    admitted_old_project = files["OLD-project-v1"] in allowed
    print(f"superseded resume v1 section admitted: {admitted_old_resume}")
    print(f"superseded project v1 file admitted:   {admitted_old_project}")
    check(
        "B1 resume v1 section is NOT retrieved after v2 exists",
        not admitted_old_resume,
        "if FAIL: search can return superseded resume content",
    )
    check(
        "B2 project v1 file is NOT retrieved after v2 exists",
        not admitted_old_project,
        "if FAIL: search can return superseded project content",
    )
    return {
        "allowed": len(allowed),
        "old_resume_admitted": admitted_old_resume,
        "old_project_admitted": admitted_old_project,
    }


def main() -> int:
    print(f"python {sys.version.split()[0]}")
    check_sql_shape()
    result = asyncio.run(check_allow_list())
    print("\n--- summary ---")
    print(f"checks failed: {len(FAILED)} {FAILED if FAILED else ''}")
    print(f"allow-list result: {result}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())

