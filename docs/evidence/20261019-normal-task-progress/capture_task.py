"""Read only the known synthetic task; never alter runtime state."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

TASK = "ec7c7076-4db4-4163-83d1-58c32a6f3b97"


async def main():
    engine = create_async_engine(
        settings.database_url, hide_parameters=True, isolation_level="REPEATABLE READ"
    )
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            task = (await connection.execute(text("""
                SELECT a.id, a.status, a.progress, a.current_step, a.started_at,
                       a.completed_at, a.total_cost_rmb, a.input_snapshot,
                       u.display_name
                FROM analysis_tasks a JOIN users u ON u.id = a.created_by
                WHERE a.id = :id
            """), {"id": TASK})).mappings().one()
            assert task["display_name"] == "演示学生"
            snapshot = task["input_snapshot"]
            rows = (await connection.execute(text("""
                SELECT step_number, event_type, name, detail, payload
                FROM agent_steps WHERE analysis_task_id = :id ORDER BY step_number
            """), {"id": TASK})).mappings().all()
            result = {
                key: task[key] for key in (
                    "id", "status", "progress", "current_step", "started_at",
                    "completed_at", "total_cost_rmb"
                )
            }
            result["selectedInput"] = {
                key: snapshot[key] for key in (
                    "jobId", "resumeVersionId", "projectVersionIds",
                    "externalAiConsent", "usePreviousReport"
                ) if key in snapshot
            }
            result["steps"] = [
                {**{key: row[key] for key in (
                    "step_number", "event_type", "name", "detail"
                )}, "payload": {
                    key: row["payload"][key] for key in (
                        "provider", "fallbackUsed", "skippedReason", "reportId"
                    ) if key in row["payload"]
                }} for row in rows
            ]
            output = Path(__file__).with_name("task-record.json")
            with output.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, default=str)
            print("Read-only synthetic task recorded; steps:", len(rows))
    finally:
        await engine.dispose()


asyncio.run(main())
