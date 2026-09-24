"""Resolve immutable material versions using the authenticated student's identity."""

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.enums import UserRole
from app.models.identity import StudentProfile, User
from app.models.portfolio import (
    Project,
    ProjectFile,
    ProjectVersion,
    Resume,
    ResumeSection,
    ResumeVersion,
)
from app.schemas.analysis import MaterialSelection
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import mask_resume_text, parse_resume
from app.tools.semantic_retrieval import (
    VERSION as SEMANTIC_VERSION,
)
from app.tools.semantic_retrieval import (
    has_document_windows,
    load_local_model,
    retrieve_semantic_candidates,
)
from app.tools.storage import LocalStorage


@dataclass
class MatchMaterials:
    resume_text: str
    files: list[dict]
    snapshots: list[dict]


async def resolve_materials(
    session: AsyncSession, request: MaterialSelection, user: User
) -> MatchMaterials:
    if user.role != UserRole.STUDENT:
        raise AppError("请使用学生账号分析自己的材料", code=4037, status_code=403)
    student = await session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not student:
        raise AppError("学生资料不存在", code=4044, status_code=404)
    row = (
        await session.execute(
            select(ResumeVersion, Resume)
            .join(Resume, Resume.id == ResumeVersion.resume_id)
            .where(ResumeVersion.id == request.resume_version_id, Resume.student_id == student.id)
        )
    ).first()
    if not row:
        raise AppError("简历版本不存在或无权访问", code=4045, status_code=404)
    version, resume = row
    if version.parse_status != "completed":
        raise AppError("请先完成简历解析", code=4095, status_code=409)
    sections = await session.scalars(
        select(ResumeSection)
        .where(ResumeSection.resume_version_id == version.id)
        .order_by(ResumeSection.page_number, ResumeSection.created_at)
    )
    resume_text = "\n".join(section.content for section in sections)
    if not resume_text.strip():
        raise AppError("简历未提取到文字，请上传文字版或先进行OCR", code=4095, status_code=409)
    snapshots = [
        {
            "kind": "resume",
            "id": str(version.id),
            "title": resume.title,
            "versionNumber": version.version_number,
            "contentHash": version.content_hash,
        }
    ]
    if len(set(request.project_version_ids)) != len(request.project_version_ids):
        raise AppError("请勿重复选择同一项目版本", code=4220, status_code=422)
    files = []
    for version_id in request.project_version_ids:
        row = (
            await session.execute(
                select(ProjectVersion, Project)
                .join(Project, Project.id == ProjectVersion.project_id)
                .where(ProjectVersion.id == version_id, Project.student_id == student.id)
            )
        ).first()
        if not row:
            raise AppError("项目版本不存在或无权访问", code=4043, status_code=404)
        project_version, project = row
        if project_version.analysis_status != "completed":
            raise AppError("所选项目尚未完成解析", code=4095, status_code=409)
        snapshots.append(
            {
                "kind": "project",
                "id": str(version_id),
                "title": project.name,
                "versionNumber": project_version.version_number,
                "contentHash": project_version.content_hash,
                "materialRole": project_version.material_role,
            }
        )
        records = await session.scalars(
            select(ProjectFile)
            .where(ProjectFile.project_version_id == version_id)
            .order_by(ProjectFile.relative_path)
        )
        for record in records:
            files.append(
                {
                    "id": str(record.id),
                    "versionId": str(version_id),
                    "versionNumber": project_version.version_number,
                    "materialRole": project_version.material_role,
                    "path": f"{version_id}/{record.relative_path}",
                    "storageKey": record.storage_key,
                    "hash": record.content_hash,
                    "size": record.size_bytes,
                }
            )
    if len(files) > 4000 or sum(file["size"] for file in files) > settings.max_extracted_bytes:
        raise AppError("选中材料过多，请减少项目数量后重试", code=4023, status_code=413)
    if len(resume_text) > settings.max_document_characters:
        raise AppError("简历文字过多，请精简后重新上传", code=4023, status_code=413)
    return MatchMaterials(resume_text, files, snapshots)


def analyze_materials(
    requirements: list[RequirementInput],
    materials: MatchMaterials,
    base: Path,
    enable_semantic: bool = True,
):
    """Runs trusted static analysis in the killable worker; never runs uploaded code."""
    storage = LocalStorage(base)
    snapshots = []
    version_by_path: dict[str, str] = {}
    declared_reference_versions = {
        str(file.get("versionId", ""))
        for file in materials.files
        if file.get("materialRole") == "reference"
    }
    for file in materials.files:
        content = storage.resolve(file["storageKey"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != file["hash"]:
            raise AppError("项目文件与上传版本不一致，请重新上传", code=4096)
        snapshots.append(
            ProjectFileSnapshot(file["path"], content.decode("utf-8", errors="replace"))
        )
        version_by_path[file["path"]] = str(file.get("versionId", ""))
    reference_versions = declared_reference_versions | {
        version_by_path[file.path]
        for file in snapshots
        if Path(file.path).name == "SOURCE.txt"
        and file.content.startswith("THIRD-PARTY PUBLIC SOURCE / SYNTHETIC TEST FIXTURE\n")
    }
    portfolio_snapshots = [
        file for file in snapshots if version_by_path[file.path] not in reference_versions
    ]
    reference_snapshots = [
        file for file in snapshots if version_by_path[file.path] in reference_versions
    ]
    claims = parse_resume(mask_resume_text(materials.resume_text))
    semantic = None
    semantic_step = None
    if (
        enable_semantic
        and settings.semantic_retrieval_enabled
        and has_document_windows(portfolio_snapshots)
    ):
        try:
            model = load_local_model(settings.semantic_model_cache_dir)
            semantic, window_count = retrieve_semantic_candidates(
                requirements, portfolio_snapshots, model
            )
            semantic_step = {
                "name": "本地语义文档检索",
                "engine": SEMANTIC_VERSION,
                "status": "active",
                "windowCount": window_count,
                "candidateCount": sum(len(hits) for hits in semantic.values()),
                "changesRuleScore": False,
                "semanticEmbedding": True,
            }
        except Exception:
            # Model installation or inference cannot prevent the rule report.
            semantic_step = {
                "name": "本地语义文档检索",
                "engine": SEMANTIC_VERSION,
                "status": "unavailable",
                "candidateCount": 0,
                "changesRuleScore": False,
                "semanticEmbedding": False,
            }
    result = match_candidate(
        requirements,
        claims,
        portfolio_snapshots,
        semantic_candidates=semantic,
        reference_files=reference_snapshots,
    )
    if reference_snapshots:
        result = replace(
            result,
            retrieval_steps=[
                *result.retrieval_steps,
                {
                    "name": "识别第三方参考材料",
                    "status": "excluded_from_personal_rating",
                    "referenceFileCount": len(reference_snapshots),
                    "changesRuleScore": True,
                },
            ],
        )
    if semantic_step is not None:
        result = replace(result, retrieval_steps=[*result.retrieval_steps, semantic_step])
    try:
        return enrich_evidence(result, snapshots)
    except Exception:
        # Preserve the deterministic report if optional AI context retrieval
        # fails. Do not send unverified or truncated source to the model.
        return replace(
            result,
            grounding_error=True,
            retrieval_steps=[
                {
                    "name": "补取并核对证据上下文",
                    "sourceExact": False,
                    "status": "failed",
                }
            ],
        )
