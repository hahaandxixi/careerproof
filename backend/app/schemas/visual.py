"""Image observations are unverified descriptions, never practice grades."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import APIModel


class VisualObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=300)
    visible_text: str = Field(default="", max_length=200)
    # Normalized estimated region; this does not certify object detection accuracy.
    region: list[float] = Field(min_length=4, max_length=4)
    needs_verification: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def ordered_region(self):
        x1, y1, x2, y2 = self.region
        if not all(0 <= v <= 1 for v in self.region) or x1 >= x2 or y1 >= y2:
            raise ValueError("Image region must be an ordered normalized rectangle")
        return self


class VisualResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_kind: Literal["architecture", "runtime", "monitoring", "document", "other"]
    observations: list[VisualObservation] = Field(min_length=1, max_length=6)


class VisualReviewRequest(APIModel):
    external_image_consent: bool = False


class VisualReviewUpdate(APIModel):
    status: Literal["pending", "accepted", "rejected"]
    note: str = Field(default="", max_length=500)


class VisualReviewView(APIModel):
    id: UUID
    project_version_id: UUID
    source_hash: str
    status: Literal["completed", "unavailable"]
    failure_kind: str | None = None
    model: str | None = None
    prompt_version: str
    observations: VisualResponse | None = None
    usage: dict | None = None
    review_status: Literal["pending", "accepted", "rejected"] = "pending"
    reviewer_note: str = ""
    reviewed_at: datetime | None = None
    created_at: datetime
    boundary: str = "图片描述不参与评级，不能证明真实部署、持续运行或本人贡献；需对照原图核对。"
