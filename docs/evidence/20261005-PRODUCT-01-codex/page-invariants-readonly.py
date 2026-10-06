"""Capture synthetic closure invariants; no credentials or row contents emitted."""
import asyncio
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    url = make_url(os.environ["CAREERPROOF_CLOSURE_DATABASE_URL"])
    assert (url.host, url.port, url.database) == (
        "127.0.0.1", 5432, "cp_e2e_closure-20261005"
    )
    root = Path(__file__).resolve().parents[3]
    state = json.loads((root / "docs/evidence/20261005-E2E-student/state.json").read_text(encoding="utf-8-sig"))
    fixture = json.loads((root / "backend/.tmp/e2e/closure-20261005.json").read_text(encoding="utf-8-sig"))
    assert fixture["runId"] == "closure-20261005"
    engine = create_async_engine(url)
    output = {"database": url.database, "readOnly": True, "tables": {}, "fixedGrowth": {}, "fixedReports": {}}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            assert await connection.scalar(text("SHOW transaction_read_only")) == "on"
            output["migration"] = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            for table in ("applications", "application_events", "notifications", "ai_usage_logs", "analysis_tasks", "match_reports"):
                rows = list(await connection.scalars(text(f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY id')))
                canonical = json.dumps([json.loads(row) for row in rows], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                output["tables"][table] = {"rows": len(rows), "sha256": hashlib.sha256(canonical.encode()).hexdigest()}
            for key in ("variantMaterialsTaskId", "variantJobTaskId", "variantBothTaskId"):
                assert key in state
                row = await connection.scalar(text("SELECT row_to_json(t)::text FROM evidence_growth_tasks t WHERE id=CAST(:id AS uuid)"), {"id": state[key]})
                assert row is not None
                canonical = json.dumps(json.loads(row), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                output["fixedGrowth"][key] = {"sha256": hashlib.sha256(canonical.encode()).hexdigest()}
            # S9 may legally create a new Mock report. Preserve a separate
            # digest of each pre-existing report, its items and analysis task;
            # new rows must not make old-row immutability unverifiable.
            for key in ("baseReportId", "reportR1", "reportR2", "reportR3"):
                report = await connection.scalar(text("SELECT row_to_json(t)::text FROM match_reports t WHERE id=CAST(:id AS uuid)"), {"id": state[key]})
                assert report is not None
                parsed_report = json.loads(report)
                analysis = await connection.scalar(text("SELECT row_to_json(t)::text FROM analysis_tasks t WHERE id=CAST(:id AS uuid)"), {"id": parsed_report["analysis_task_id"]})
                assert analysis is not None
                items = list(await connection.scalars(text("SELECT row_to_json(t)::text FROM match_items t WHERE report_id=CAST(:id AS uuid) ORDER BY id"), {"id": state[key]}))
                assert items
                output["fixedReports"][key] = {}
                for label, rows in (("report", [parsed_report]), ("analysis", [json.loads(analysis)]), ("items", [json.loads(row) for row in items])):
                    canonical = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                    output["fixedReports"][key][label] = {"rows": len(rows), "sha256": hashlib.sha256(canonical.encode()).hexdigest()}
            await connection.rollback()
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
