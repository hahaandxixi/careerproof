from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import APIModel


class ApplicationCreate(APIModel):
    report_id: UUID
    share_consent: Literal[True]


class ReplyReference(APIModel):
    requirement_id: UUID
    citation_ids: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def distinct_citations(self):
        if len(self.citation_ids) != len(set(self.citation_ids)):
            raise ValueError("Duplicate citation IDs")
        return self


class ApplicationReply(APIModel):
    kind: Literal["interview", "continue", "declined"]
    text: str = Field(min_length=1, max_length=2000)
    references: list[ReplyReference] = Field(default_factory=list, max_length=50)
