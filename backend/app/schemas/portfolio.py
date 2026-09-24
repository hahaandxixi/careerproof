from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.enums import TaskStatus
from app.schemas.common import APIModel


class KnowledgeSearchResult(APIModel):
    id: UUID
    source_type: str
    source_id: UUID
    content: str
    metadata: dict


class ResumeUploadData(APIModel):
    resume_id: UUID
    version_id: UUID
    task_id: UUID
    status: TaskStatus


class ProjectCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    request_id: UUID | None = None


class ProjectView(APIModel):
    id: UUID
    name: str
    description: str
    version: int


class ProjectVersionUploadData(APIModel):
    project_id: UUID
    version_id: UUID
    task_id: UUID
    status: TaskStatus


class MaterialVersionView(APIModel):
    id: UUID
    version_number: int
    material_role: Literal["portfolio", "reference"] | None = None
    original_filename: str | None
    size_bytes: int | None
    created_at: datetime
    status: str
    task_id: UUID | None
    progress: int | None
    current_step: str | None
    error_message: str | None


class ResumeHistoryView(APIModel):
    id: UUID
    title: str
    created_at: datetime
    versions: list[MaterialVersionView] = Field(default_factory=list)


class ProjectHistoryView(ProjectView):
    created_at: datetime
    versions: list[MaterialVersionView] = Field(default_factory=list)


class ResumeSectionView(APIModel):
    id: UUID
    section_type: str
    content: str
    page_number: int | None


class ResumePreview(APIModel):
    id: UUID
    status: str
    sections: list[ResumeSectionView]


class ProjectFileView(APIModel):
    id: UUID
    relative_path: str
    language: str | None
    size_bytes: int
    line_count: int


class ProjectFilePreview(APIModel):
    id: UUID
    relative_path: str
    content: str
    project_version_id: UUID
