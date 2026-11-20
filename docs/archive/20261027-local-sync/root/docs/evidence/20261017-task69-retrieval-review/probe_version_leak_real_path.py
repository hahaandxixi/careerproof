"""task69 FIX P0 — red proof that superseded material versions reach real search results.

Not a SQL-text argument. This drives the actual admission step used by
`search_owned_chunks` (`_allowed_source_ids`, the helper the fix introduces) and, because
PostgreSQL is unavailable here, replays the identical downstream pipeline (distance
ordering over the admitted chunk set, truncated at `limit`) so the ranking consequence
is shown on the real admitted ids.

Topology (all synthetic):
  owner A: resume v1 [STALE-RESUME-V1, exact query match], resume v2 [current]
           project portfolio v1 [stale], portfolio v2 [current], reference v3 [current]
  owner B: resume v1 [other owner]
  owner C: project v1 [other owner]
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from uuid import UUID

SCRATCH = Path(os.environ.get("T69FIX_SCRATCH", Path(__file__).resolve().parent / "scratch"))
SCRATCH.mkdir(parents=True, exist_ok=True)

from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.models.analysis import KnowledgeChunk  # noqa: E402
from app.models.identity import StudentProfile, User  # noqa: E402
from app.models.portfolio import (  # noqa: E402
    Project,
    ProjectFile,
    ProjectVersion,
    Resume,
    ResumeSection,
    ResumeVersion,
)

DIM = 384
QUERY = "参数校验 失败分支 运行记录"
STALE_RESUME = "STALE-RESUME-V1-已作废的旧版简历内容"
CURRENT_RESUME = "RESUME-V2-当前版本内容"
STALE_PROJECT = "A-PROJECT-V1-旧版项目文件"
CURRENT_PROJECT = "A-PROJECT-V2-当前项目文件"
REFERENCE_V3 = "A-REFERENCE-V3-参考作品-应保留"
OTHER_OWNER_RESUME = "other-owner-secret-不应被A看到"
OTHER_OWNER_PROJECT = "mixed-owner-project-不应被A看到"

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((ok, label, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))


def vec(text: str) -> list[float]:
    """Deterministic 384-dim hash embedding; identical text -> identical vector."""
    out: list[float] = []
    counter = 0
    while len(out) < DIM:
        digest = hashlib.sha256(f"{text}|{counter}".encode()).digest()
        out.extend(byte / 255.0 for byte in digest)
        counter += 1
    return out[:DIM]


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return 1.0 - (dot / (na * nb) if na and nb else 0.0)


async def build(factory):
    async with factory() as session:
        owners = {}
        for label in ("A", "B", "C"):
            user = User(
                email=f"t69fix-{label}@example.com",
                password_hash="synthetic",
                display_name=f"owner {label}",
                role="student",
            )
            session.add(user)
            await session.flush()
            profile = StudentProfile(user_id=user.id)
            session.add(profile)
            await session.flush()
            owners[label] = profile

        ids: dict[str, str] = {}

        # owner A: resume v1 (stale) and v2 (current) under ONE resume row
        resume = Resume(student_id=owners["A"].id, title="A resume")
        session.add(resume)
        await session.flush()
        for number, marker in ((1, STALE_RESUME), (2, CURRENT_RESUME)):
            version = ResumeVersion(
                resume_id=resume.id,
                version_number=number,
                storage_key=f"t69fix/r{number}.pdf",
                content_hash=f"{number:064d}",
                mime_type="application/pdf",
                size_bytes=1024,
                parse_status="completed",
            )
            session.add(version)
            await session.flush()
            section = ResumeSection(
                resume_version_id=version.id, section_type="skills", content=marker
            )
            session.add(section)
            await session.flush()
            ids[f"resume_v{number}"] = str(section.id)

        # owner A: project portfolio v1 (stale), portfolio v2 (current), reference v3
        project = Project(student_id=owners["A"].id, name="A project")
        session.add(project)
        await session.flush()
        for number, role, marker in (
            (1, "portfolio", STALE_PROJECT),
            (2, "portfolio", CURRENT_PROJECT),
            (3, "reference", REFERENCE_V3),
        ):
            version = ProjectVersion(
                project_id=project.id,
                version_number=number,
                material_role=role,
                archive_storage_key=f"t69fix/p{number}{role}.zip",
                content_hash=hashlib.sha256(f"{number}{role}".encode()).hexdigest(),
            )
            session.add(version)
            await session.flush()
            row = ProjectFile(
                project_version_id=version.id,
                relative_path=f"main-{number}-{role}.py",
                content_hash=hashlib.sha256(marker.encode()).hexdigest(),
                size_bytes=10,
                line_count=1,
                storage_key=f"t69fix/main-{number}-{role}.py",
            )
            session.add(row)
            await session.flush()
            ids[f"project_{role}_v{number}"] = str(row.id)

        # owner B: own resume
        other_resume = Resume(student_id=owners["B"].id, title="B resume")
        session.add(other_resume)
        await session.flush()
        other_version = ResumeVersion(
            resume_id=other_resume.id,
            version_number=1,
            storage_key="t69fix/b1.pdf",
            content_hash="b" * 64,
            mime_type="application/pdf",
            size_bytes=1024,
            parse_status="completed",
        )
        session.add(other_version)
        await session.flush()
        other_section = ResumeSection(
            resume_version_id=other_version.id,
            section_type="skills",
            content=OTHER_OWNER_RESUME,
        )
        session.add(other_section)
        await session.flush()
        ids["ownerB_resume"] = str(other_section.id)

        # owner C: project
        mixed_project = Project(student_id=owners["C"].id, name="C project")
        session.add(mixed_project)
        await session.flush()
        mixed_version = ProjectVersion(
            project_id=mixed_project.id,
            version_number=1,
            material_role="portfolio",
            archive_storage_key="t69fix/c1.zip",
            content_hash="c" * 64,
        )
        session.add(mixed_version)
        await session.flush()
        mixed_file = ProjectFile(
            project_version_id=mixed_version.id,
            relative_path="c.py",
            content_hash=hashlib.sha256(OTHER_OWNER_PROJECT.encode()).hexdigest(),
            size_bytes=10,
            line_count=1,
            storage_key="t69fix/c.py",
        )
        session.add(mixed_file)
        await session.flush()
        ids["ownerC_project"] = str(mixed_file.id)

        # chunks: the stale resume section is an exact query match
        for marker, source_id, source_type in (
            (STALE_RESUME, ids["resume_v1"], "resume_section"),
            (CURRENT_RESUME, ids["resume_v2"], "resume_section"),
            (OTHER_OWNER_RESUME, ids["ownerB_resume"], "resume_section"),
            (STALE_PROJECT, ids["project_portfolio_v1"], "project_file"),
            (CURRENT_PROJECT, ids["project_portfolio_v2"], "project_file"),
            (REFERENCE_V3, ids["project_reference_v3"], "project_file"),
            (OTHER_OWNER_PROJECT, ids["ownerC_project"], "project_file"),
        ):
            session.add(
                KnowledgeChunk(
                    source_type=source_type,
                    source_id=UUID(source_id),
                    content=marker,
                    chunk_metadata={"embeddingEngine": "hash"},
                    embedding=vec(QUERY if marker == STALE_RESUME else marker),
                )
            )

        await session.commit()
        return owners["A"], ids


async def main() -> int:
    engine = create_async_engine("sqlite+aiosqlite://")

    @event.listens_for(engine.sync_engine, "connect")
    def register(connection, _record):
        connection.create_function(
            "num_nonnulls", -1, lambda *args: sum(a is not None for a in args)
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    owner_a, ids = await build(factory)

    from app.services import retrieval as retrieval_module

    # search_owned_chunks receives a User; load the User the profile belongs to.
    async with factory() as preload:
        owner_user = await preload.get(User, owner_a.user_id)

    admit = getattr(retrieval_module, "_allowed_source_ids", None)
    async with factory() as session:
        if admit is None:
            # Pre-fix fallback: reproduce the inline predicates verbatim.
            from sqlalchemy import select as sa_select

            student_id = await session.scalar(
                sa_select(StudentProfile.id).where(
                    StudentProfile.user_id == owner_a.user_id
                )
            )
            resume_ids = (
                sa_select(ResumeSection.id)
                .join(ResumeVersion)
                .join(Resume)
                .where(Resume.student_id == student_id, Resume.is_archived.is_(False))
            )
            project_ids = (
                sa_select(ProjectFile.id)
                .join(ProjectVersion)
                .join(Project)
                .where(Project.student_id == student_id, Project.is_archived.is_(False))
            )
            allowed = list(await session.scalars(resume_ids)) + list(
                await session.scalars(project_ids)
            )
            mode = "inline predicates (pre-fix code shape)"
        else:
            allowed = await admit(session, owner_user)
            mode = "retrieval._allowed_source_ids (post-fix helper)"

        print(f"\nadmission path used: {mode}")
        allowed_set = {str(value) for value in allowed}
        print(f"admitted ids: {len(allowed_set)}")

        check(
            ids["resume_v1"] not in allowed_set,
            "D1 superseded resume v1 section excluded from admitted set",
            f"admitted={ids['resume_v1'] in allowed_set}",
        )
        check(ids["resume_v2"] in allowed_set, "D2 current resume v2 section retained")
        check(
            ids["project_portfolio_v1"] not in allowed_set,
            "D3 superseded project portfolio v1 file excluded",
            f"admitted={ids['project_portfolio_v1'] in allowed_set}",
        )
        check(
            ids["project_portfolio_v2"] in allowed_set,
            "D4 current project portfolio v2 file retained",
        )
        check(
            ids["project_reference_v3"] in allowed_set,
            "D5 current reference-role work at v3 retained (legitimate recall kept)",
        )
        check(ids["ownerB_resume"] not in allowed_set, "D6 other owner's resume excluded")
        check(ids["ownerC_project"] not in allowed_set, "D7 other owner's project file excluded")

        # ranking consequence on the REAL admitted ids
        rows = []
        if allowed_set:
            result = await session.execute(
                KnowledgeChunk.__table__.select().where(
                    KnowledgeChunk.source_id.in_([UUID(str(value)) for value in allowed_set])
                )
            )
            rows = list(result)
        ranked = sorted(
            (
                (cosine_distance(vec(QUERY), list(row.embedding)), row.content, str(row.source_id))
                for row in rows
            ),
            key=lambda item: item[0],
        )
        limit = 2
        top = ranked[:limit]
        print(f"\nreplayed ranking (limit={limit}) over {len(ranked)} admitted chunks:")
        for distance, content, source_id in top:
            print(f"   distance={distance:.6f} source_id={source_id} content={content!r}")
        stale_in_top = any(sid == ids["resume_v1"] for _d, _c, sid in top)
        check(
            not stale_in_top,
            "D8 superseded v1 section does not occupy a result slot",
            f"stale_in_top={stale_in_top}",
        )
        if stale_in_top:
            print(
                "   -> RED: the stale section is an exact query match and wins a slot, "
                "displacing current-version material."
            )

    await engine.dispose()
    failed = [row for row in RESULTS if not row[0]]
    print(f"\n--- summary: {len(RESULTS)} checks, {len(failed)} failed ---")
    for _ok, label, _detail in failed:
        print(f"FAILED: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
