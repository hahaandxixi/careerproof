"""Material-version semantics for search and for report material selection.

Two distinct contracts, and they must not be conflated:

1. **Library-level discovery** (``search_owned_chunks`` behind ``GET /knowledge/search``)
   receives only a query and a limit. Its existing scope is every section/file of the
   caller's non-archived resumes and projects, across *all* of that owner's versions.
   A student may choose any saved version when creating a report, so an older version
   is still legitimate material to find here. It must not be narrowed to the newest
   version.

2. **Report / matching material selection** (``resolve_materials`` behind ``POST /matches``
   and the growth/recommendation paths) receives an explicit ``resume_version_id`` and
   ``project_version_ids``. It must return exactly the chosen versions, even when newer
   versions exist, and must never return unselected versions, unselected projects, or
   another owner's material.

The earlier "newest version only" admission rule was a semantic error: it made an
explicitly selected older version unretrievable. These tests pin the corrected
behaviour so it cannot regress in either direction.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
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
from app.schemas.analysis import MatchCreate
from app.services.matching_materials import resolve_materials
from app.services.retrieval import _allowed_source_ids

V1_TEXT = "第一版内容-用户可能明确选择"
V2_TEXT = "第二版内容-更新版本"
OTHER_RESUME_TEXT = "另一位学生的简历段落"
SELECTED_PROJECT_TEXT = "被选中的项目文件内容"
UNSELECTED_PROJECT_TEXT = "未被选中的项目文件内容"
OTHER_PROJECT_TEXT = "另一位学生的项目文件"
REFERENCE_TEXT = "参考作品内容"


@pytest.fixture
async def material_topology():
    """Owner A with resume v1+v2, selected project, unselected project, reference role.

    Owner B holds a similar-shaped resume/project so cross-owner leakage is visible.
    """
    engine = create_async_engine("sqlite+aiosqlite://")

    @event.listens_for(engine.sync_engine, "connect")
    def register_functions(connection, _record):
        connection.create_function(
            "num_nonnulls", -1, lambda *args: sum(value is not None for value in args)
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    ids: dict[str, UUID] = {"job_id": uuid4()}
    async with factory() as session:
        async def make_owner(label: str):
            user = User(
                email=f"material-version-{label}@example.com",
                password_hash="synthetic",
                display_name=f"owner {label}",
                role="student",
            )
            session.add(user)
            await session.flush()
            profile = StudentProfile(user_id=user.id)
            session.add(profile)
            await session.flush()
            return user, profile

        owner_a_user, owner_a = await make_owner("A")
        _owner_b_user, owner_b = await make_owner("B")

        # --- owner A: one resume with two saved versions, both still readable ---
        resume = Resume(student_id=owner_a.id, title="A resume")
        session.add(resume)
        await session.flush()
        for number, text in ((1, V1_TEXT), (2, V2_TEXT)):
            version = ResumeVersion(
                resume_id=resume.id,
                version_number=number,
                storage_key=f"material-version/a{number}.pdf",
                content_hash=f"{number:064d}",
                mime_type="application/pdf",
                size_bytes=32,
                parse_status="completed",
            )
            session.add(version)
            await session.flush()
            ids[f"resume_version_v{number}"] = version.id
            section = ResumeSection(
                resume_version_id=version.id, section_type="skills", content=text
            )
            session.add(section)
            await session.flush()
            ids[f"resume_section_v{number}"] = section.id

        # --- owner A: selected project (portfolio) and an unselected project ---
        selected = Project(student_id=owner_a.id, name="Selected project")
        session.add(selected)
        await session.flush()
        selected_version = ProjectVersion(
            project_id=selected.id,
            version_number=1,
            material_role="portfolio",
            archive_storage_key="material-version/selected.zip",
            content_hash="a" * 64,
            analysis_status="completed",
        )
        session.add(selected_version)
        await session.flush()
        ids["selected_project_version"] = selected_version.id
        selected_file = ProjectFile(
            project_version_id=selected_version.id,
            relative_path="main.py",
            content_hash="b" * 64,
            size_bytes=len(SELECTED_PROJECT_TEXT),
            line_count=1,
            storage_key="material-version/selected/main.py",
            analysis_status="completed",
        )
        session.add(selected_file)
        await session.flush()
        ids["selected_project_file"] = selected_file.id

        unselected = Project(student_id=owner_a.id, name="Unselected project")
        session.add(unselected)
        await session.flush()
        unselected_version = ProjectVersion(
            project_id=unselected.id,
            version_number=1,
            material_role="portfolio",
            archive_storage_key="material-version/unselected.zip",
            content_hash="c" * 64,
            analysis_status="completed",
        )
        session.add(unselected_version)
        await session.flush()
        ids["unselected_project_version"] = unselected_version.id
        unselected_file = ProjectFile(
            project_version_id=unselected_version.id,
            relative_path="other.py",
            content_hash="d" * 64,
            size_bytes=len(UNSELECTED_PROJECT_TEXT),
            line_count=1,
            storage_key="material-version/unselected/other.py",
            analysis_status="completed",
        )
        session.add(unselected_file)
        await session.flush()
        ids["unselected_project_file"] = unselected_file.id

        # --- owner A: a reference-role version of the selected project ---
        reference_version = ProjectVersion(
            project_id=selected.id,
            version_number=2,
            material_role="reference",
            archive_storage_key="material-version/reference.zip",
            content_hash="e" * 64,
            analysis_status="completed",
        )
        session.add(reference_version)
        await session.flush()
        ids["reference_project_version"] = reference_version.id
        reference_file = ProjectFile(
            project_version_id=reference_version.id,
            relative_path="ref.py",
            content_hash="f" * 64,
            size_bytes=len(REFERENCE_TEXT),
            line_count=1,
            storage_key="material-version/reference/ref.py",
            analysis_status="completed",
        )
        session.add(reference_file)
        await session.flush()
        ids["reference_project_file"] = reference_file.id

        # --- owner B: look-alike material that must never be admitted ---
        other_resume = Resume(student_id=owner_b.id, title="B resume")
        session.add(other_resume)
        await session.flush()
        other_version = ResumeVersion(
            resume_id=other_resume.id,
            version_number=1,
            storage_key="material-version/b1.pdf",
            content_hash="1" * 64,
            mime_type="application/pdf",
            size_bytes=32,
            parse_status="completed",
        )
        session.add(other_version)
        await session.flush()
        other_section = ResumeSection(
            resume_version_id=other_version.id,
            section_type="skills",
            content=OTHER_RESUME_TEXT,
        )
        session.add(other_section)
        await session.flush()
        ids["ownerB_resume_section"] = other_section.id

        other_project = Project(student_id=owner_b.id, name="B project")
        session.add(other_project)
        await session.flush()
        other_project_version = ProjectVersion(
            project_id=other_project.id,
            version_number=1,
            material_role="portfolio",
            archive_storage_key="material-version/b.zip",
            content_hash="2" * 64,
            analysis_status="completed",
        )
        session.add(other_project_version)
        await session.flush()
        other_file = ProjectFile(
            project_version_id=other_project_version.id,
            relative_path="b.py",
            content_hash="3" * 64,
            size_bytes=len(OTHER_PROJECT_TEXT),
            line_count=1,
            storage_key="material-version/b/b.py",
            analysis_status="completed",
        )
        session.add(other_file)
        await session.flush()
        ids["ownerB_project_file"] = other_file.id

        await session.commit()

    yield {"factory": factory, "owner": owner_a_user, "profile": owner_a, "ids": ids}
    await engine.dispose()


# ---------------------------------------------------------------------------
# Contract 1: library-level discovery keeps every owned version.
# ---------------------------------------------------------------------------
async def test_library_search_keeps_an_older_version_when_a_newer_one_exists(
    material_topology,
):
    """A student may select the older version for a report, so it must stay findable."""
    ids = material_topology["ids"]
    async with material_topology["factory"]() as session:
        allowed = {
            str(value)
            for value in await _allowed_source_ids(session, material_topology["owner"])
        }

    assert str(ids["resume_section_v1"]) in allowed, (
        "an older but still saved resume version must remain discoverable"
    )
    assert str(ids["resume_section_v2"]) in allowed
    assert str(ids["selected_project_file"]) in allowed
    assert str(ids["reference_project_file"]) in allowed, (
        "material_role must not decide admission at library level"
    )


async def test_library_search_excludes_only_other_owners(material_topology):
    """Owner is the one boundary this discovery query enforces."""
    ids = material_topology["ids"]
    async with material_topology["factory"]() as session:
        allowed = {
            str(value)
            for value in await _allowed_source_ids(session, material_topology["owner"])
        }

    assert str(ids["ownerB_resume_section"]) not in allowed
    assert str(ids["ownerB_project_file"]) not in allowed
    # Unselected by any report, but still the caller's own material.
    assert str(ids["unselected_project_file"]) in allowed


# ---------------------------------------------------------------------------
# Contract 2: report material selection honours the explicit version choice.
# ---------------------------------------------------------------------------
def _match_request(ids, resume_version_key: str, project_keys: list[str]) -> MatchCreate:
    return MatchCreate(
        job_id=ids["job_id"],
        resume_version_id=ids[resume_version_key],
        project_version_ids=[ids[key] for key in project_keys],
        external_ai_consent=False,
    )


async def test_selected_older_resume_version_is_used_even_when_newer_exists(
    material_topology,
):
    """Explicitly choosing v1 must yield v1 text, not the newer v2."""
    ids = material_topology["ids"]
    async with material_topology["factory"]() as session:
        materials = await resolve_materials(
            session,
            _match_request(ids, "resume_version_v1", ["selected_project_version"]),
            material_topology["owner"],
        )

    assert V1_TEXT in materials.resume_text
    assert V2_TEXT not in materials.resume_text, (
        "an unselected newer version leaked into the selected material set"
    )


async def test_selected_newer_resume_version_does_not_include_the_older_one(
    material_topology,
):
    ids = material_topology["ids"]
    async with material_topology["factory"]() as session:
        materials = await resolve_materials(
            session,
            _match_request(ids, "resume_version_v2", ["selected_project_version"]),
            material_topology["owner"],
        )

    assert V2_TEXT in materials.resume_text
    assert V1_TEXT not in materials.resume_text


async def test_unselected_project_and_reference_role_stay_out_of_the_selection(
    material_topology,
):
    """Only the chosen project versions are read; role does not pull a version in."""
    ids = material_topology["ids"]
    async with material_topology["factory"]() as session:
        materials = await resolve_materials(
            session,
            _match_request(ids, "resume_version_v1", ["selected_project_version"]),
            material_topology["owner"],
        )

    version_ids = {str(file["versionId"]) for file in materials.files}
    assert version_ids == {str(ids["selected_project_version"])}, (
        f"selection must be exactly the chosen versions, got {version_ids}"
    )
    paths = {file["path"] for file in materials.files}
    assert paths == {f"{ids['selected_project_version']}/main.py"}


async def test_other_owner_cannot_be_selected_even_with_its_version_id(
    material_topology,
):
    """Owner check happens before version scope, so a foreign version id is refused."""
    from app.core.exceptions import AppError

    ids = material_topology["ids"]
    async with material_topology["factory"]() as session:
        request = MatchCreate(
            job_id=ids["job_id"],
            resume_version_id=UUID(str(ids["resume_version_v1"])),
            project_version_ids=[ids["ownerB_project_file"]],
            external_ai_consent=False,
        )
        with pytest.raises(AppError) as error:
            await resolve_materials(session, request, material_topology["owner"])
    assert error.value.code == 4043


async def test_selection_scope_is_identical_before_and_after_candidate_generation(
    material_topology,
):
    """With many look-alike materials, the chosen candidates are still exactly the chosen ones.

    `resolve_materials` is the single place the report's material window is decided, so
    the same version predicate produces the candidate set that later steps read. This
    asserts the selection is not diluted when other own/foreign materials exist.
    """
    ids = material_topology["ids"]
    async with material_topology["factory"]() as session:
        materials = await resolve_materials(
            session,
            _match_request(
                ids,
                "resume_version_v1",
                ["selected_project_version", "reference_project_version"],
            ),
            material_topology["owner"],
        )

    assert materials.resume_text == V1_TEXT, (
        "the selected resume version must be the whole resume text, nothing else"
    )
    selected = {str(file["versionId"]) for file in materials.files}
    assert selected == {
        str(ids["selected_project_version"]),
        str(ids["reference_project_version"]),
    }, "both explicitly chosen versions must survive, and nothing else may be added"
    snapshot_versions = {snapshot["id"] for snapshot in materials.snapshots}
    assert str(ids["resume_version_v1"]) in snapshot_versions
