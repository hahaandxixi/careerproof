from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StrictBool, StringConstraints

from app.schemas.analysis import MaterialSelection
from app.schemas.common import APIModel

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class GrowthCreate(APIModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: UUID
    gap_kind: Literal["implementation", "execution", "contribution", "review"]
    deliverable: ShortText
    steps: list[ShortText] = Field(min_length=1, max_length=5)
    acceptance_checks: list[ShortText] = Field(min_length=1, max_length=5)


class GrowthMaterials(MaterialSelection):
    model_config = ConfigDict(extra="forbid")
    target_job_id: UUID | None = None


class GrowthAnalyze(APIModel):
    model_config = ConfigDict(extra="forbid")
    external_ai_consent: StrictBool = False
