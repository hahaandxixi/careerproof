from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel

JobCategory = Literal["software", "data_analysis", "operations", "design", "other"]
EmploymentType = Literal["internship", "campus", "full_time"]
JobStatus = Literal["draft", "published", "closed"]


class JobRequirementCreate(APIModel):
    raw_text: str = Field(min_length=1, max_length=2000)
    skill_name: str = Field(min_length=1, max_length=100)
    skill_id: UUID | None = None
    weight: int = Field(default=1, ge=1, le=5)
    is_required: bool = True
    source_quote: str | None = Field(default=None, min_length=3, max_length=1000)
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, gt=0)


class JobDraftRequest(APIModel):
    description: str = Field(min_length=20, max_length=6000)
    external_ai_consent: bool = False


class JobDraftRequirement(APIModel):
    raw_text: str = Field(min_length=1, max_length=2000)
    skill_name: str = Field(min_length=1, max_length=100)
    weight: int = Field(ge=1, le=5)
    is_required: bool
    source_quote: str = Field(min_length=3, max_length=1000)
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    evidence_request: str = Field(default="", max_length=300)
    verification_question: str = Field(default="", max_length=300)
    weight_reason: str = Field(default="", max_length=200)


class JobDraftResult(APIModel):
    requirements: list[JobDraftRequirement] = Field(min_length=1, max_length=12)
    model: str
    usage: dict | None = None
    confirmed: bool = False


class JobCreate(APIModel):
    title: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    enterprise_id: UUID | None = None
    status: JobStatus = "draft"
    category: JobCategory = "software"
    city: str = Field(default="不限", min_length=1, max_length=100)
    employment_type: EmploymentType = "campus"
    requirements: list[JobRequirementCreate] = Field(default_factory=list, max_length=50)


class JobUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    status: JobStatus | None = None
    category: JobCategory | None = None
    city: str | None = Field(default=None, min_length=1, max_length=100)
    employment_type: EmploymentType | None = None
    requirements: list[JobRequirementCreate] | None = Field(default=None, max_length=50)

    model_config = {"extra": "forbid"}


class JobOption(APIModel):
    value: str
    label: str


class RecommendedSkill(APIModel):
    name: str
    category: JobCategory


class JobOptions(APIModel):
    categories: list[JobOption]
    employment_types: list[JobOption]
    skills: list[RecommendedSkill]


class JobRequirementView(APIModel):
    id: UUID
    raw_text: str
    skill_name: str
    skill_id: UUID | None
    weight: int
    is_required: bool
    normalized_status: str
    source_quote: str | None = None
    source_start: int | None = None
    source_end: int | None = None


class JobView(APIModel):
    id: UUID
    enterprise_id: UUID | None
    created_by: UUID
    title: str
    company_name: str
    description: str
    status: str
    category: JobCategory
    city: str
    employment_type: EmploymentType
    created_at: datetime
    requirements: list[JobRequirementView]
    is_demo: bool = False
    discovery_visible: bool = True


class JobSummary(APIModel):
    id: UUID
    title: str
    company_name: str
    description: str
    status: str
    category: JobCategory
    city: str
    employment_type: EmploymentType
    requirement_count: int
    created_at: datetime
    is_demo: bool = False
    discovery_visible: bool = True
    application_count: int | None = None
    pending_application_count: int | None = None
    career_direction: str | None = None
    technical_tags: list[str] = Field(default_factory=list)
