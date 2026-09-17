from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AgentStep, AnalysisTask, MatchItem, MatchReport


class AnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_task(self, task: AnalysisTask) -> None:
        self.session.add(task)

    async def get_task(self, task_id: UUID) -> AnalysisTask | None:
        return await self.session.get(AnalysisTask, task_id)

    async def steps(self, task_id: UUID) -> list[AgentStep]:
        result = await self.session.execute(
            select(AgentStep)
            .where(AgentStep.analysis_task_id == task_id)
            .order_by(AgentStep.step_number)
        )
        return list(result.scalars().all())

    async def report_by_task(self, task_id: UUID) -> MatchReport | None:
        result = await self.session.execute(
            select(MatchReport).where(MatchReport.analysis_task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_report(self, report_id: UUID) -> MatchReport | None:
        return await self.session.get(MatchReport, report_id)

    async def report_items(self, report_id: UUID) -> list[MatchItem]:
        result = await self.session.execute(
            select(MatchItem).where(MatchItem.report_id == report_id).order_by(MatchItem.created_at)
        )
        return list(result.scalars().all())

    def add_steps(self, steps: list[AgentStep]) -> None:
        self.session.add_all(steps)

    def add_report(self, report: MatchReport, items: list[MatchItem]) -> None:
        self.session.add(report)
        self.session.add_all(items)
