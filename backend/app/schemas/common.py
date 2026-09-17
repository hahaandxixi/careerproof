from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.request_context import get_request_id


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        str_strip_whitespace=True,
    )


class ApiResponse[T](APIModel):
    code: int = 0
    message: str = "success"
    data: T
    request_id: str = Field(default_factory=get_request_id)


class PaginatedData[T](APIModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class HealthData(APIModel):
    status: str
    service: str
    timestamp: datetime


def success[T](data: T, *, message: str = "success") -> ApiResponse[T]:
    return ApiResponse(data=data, message=message)
