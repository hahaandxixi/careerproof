from __future__ import annotations

from app.schemas.common import PaginatedData


class GrowthTaskPage(PaginatedData[dict]):
    """One page of owned growth tasks plus rows on it that could not be rendered.

    ``unavailable_count`` counts only the records inside the returned page window
    that the existing narrow drift handling skipped. ``total`` still counts every
    owned saved record, so navigation never under-reports what the student owns
    and omitted records are never presented as "no tasks".
    """

    unavailable_count: int = 0
