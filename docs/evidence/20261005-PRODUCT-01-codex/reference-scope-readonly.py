"""Independently verify original-requirement reference scope in the closure DB."""
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.analysis import MatchItem, MatchReport
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.identity import User
from app.services.growth_answer import GrowthAnswerService


async def main():
    url = make_url(os.environ["CAREERPROOF_CLOSURE_DATABASE_URL"])
    assert (url.host, url.port, url.database) == ("127.0.0.1", 5432, "cp_e2e_closure-20261005")
    root = Path(__file__).resolve().parents[3]
    state = json.loads((root / "docs/evidence/20261005-E2E-student/state.json").read_text(encoding="utf-8-sig"))
    fixture = json.loads((root / "backend/.tmp/e2e/closure-20261005.json").read_text(encoding="utf-8-sig"))
    assert fixture["runId"] == "closure-20261005"
    owner = UUID(fixture["accounts"]["student"]["userId"])
    output = {"readOnly": True, "database": url.database, "cases": {}}
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            assert await session.scalar(text("SHOW transaction_read_only")) == "on"
            user = await session.get(User, owner)
            for label, key, expected_same_job in (("sameJob", "variantMaterialsTaskId", True), ("crossJob", "variantBothTaskId", False)):
                task = await session.get(EvidenceGrowthTask, UUID(state[key]))
                assert task is not None and task.created_by == owner
                base = await session.get(MatchReport, task.base_report_id)
                target = await session.scalar(select(MatchReport).where(MatchReport.analysis_task_id == task.analysis_task_id))
                assert base is not None and target is not None
                assert (base.job_id == target.job_id) == expected_same_job
                target_requirements = set(await session.scalars(select(MatchItem.requirement_id).where(MatchItem.report_id == target.id)))
                options = await GrowthAnswerService(session).selectable_references(task.id, user)
                assert options and all(option["requirementId"] == str(task.requirement_id) for option in options)
                base_options = [option for option in options if option["reportKind"] == "base"]
                target_options = [option for option in options if option["reportKind"] == "target"]
                assert base_options and all(option["reportId"] == str(base.id) for option in base_options)
                if expected_same_job:
                    assert task.requirement_id in target_requirements and target_options
                    assert all(option["reportId"] == str(target.id) for option in target_options)
                else:
                    assert task.requirement_id not in target_requirements and not target_options
                output["cases"][label] = {
                    "taskId": str(task.id), "originalRequirementId": str(task.requirement_id),
                    "baseJobId": str(base.job_id), "targetJobId": str(target.job_id),
                    "targetHasOriginalRequirement": task.requirement_id in target_requirements,
                    "baseOptionCount": len(base_options), "targetOptionCount": len(target_options),
                    "allOptionsUseOriginalRequirement": True,
                }
            await session.rollback()
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
