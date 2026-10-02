"""A narrow contract for questions about a consented application snapshot."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.common import APIModel

Text = Annotated[str, StringConstraints(min_length=1, max_length=600)]


class ApplicationVerificationRequest(APIModel):
    model_config = ConfigDict(extra="forbid")
    external_ai_consent: Literal[True]

    @field_validator("external_ai_consent", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("External AI consent must be explicitly true")
        return value


class VerificationItem(APIModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str = Field(min_length=1, max_length=100)
    visible_support: Text | None
    information_gap: Text
    verification_questions: list[Text] = Field(min_length=1, max_length=3)
    next_step: Literal["review_materials", "request_evidence", "discuss_implementation"] | None = (
        None
    )
    next_step_reason: Text | None = None
    citation_ids: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def paired_next_step(self):
        if (self.next_step is None) != (self.next_step_reason is None):
            raise ValueError("nextStep and nextStepReason must be supplied together")
        return self


class VerificationAnalysis(APIModel):
    model_config = ConfigDict(extra="forbid")
    items: list[VerificationItem] = Field(min_length=1, max_length=50)
