"""Read-only, named synthetic application snapshots; no credentials or material text."""

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

OLD_APPLICATION = "97b6128d-a7c4-4b8b-8789-13201b07e272"
REPORT = "f0e36d67-d028-4bcb-ba3f-64f71a52b1c6"


async def capture():
    engine = create_async_engine(settings.database_url, hide_parameters=True,
                                 isolation_level="REPEATABLE READ")
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            owner = (await connection.execute(text("""
                SELECT a.student_id::text, a.job_id::text, u.display_name, j.title
                FROM applications a JOIN student_profiles s ON s.id=a.student_id
                JOIN users u ON u.id=s.user_id JOIN jobs j ON j.id=a.job_id
                WHERE a.id=CAST(:id AS uuid)
            """), {"id": OLD_APPLICATION})).one()
            assert owner.display_name == "演示学生" and "合成演示" in owner.title
            rows = (await connection.execute(text("""
                SELECT id::text, job_id::text, report_id::text, status,
                       md5(row_to_json(a)::text) AS row_hash,
                       md5(report_snapshot::text) AS snapshot_hash,
                       consent_at IS NOT NULL AS has_consent, consent_version
                FROM applications a WHERE student_id=CAST(:student AS uuid)
                ORDER BY id
            """), {"student": owner.student_id})).mappings().all()
            report = (await connection.execute(text("""
                SELECT id::text, job_id::text, md5(row_to_json(r)::text) AS row_hash
                FROM match_reports r WHERE id=CAST(:id AS uuid)
            """), {"id": REPORT})).mappings().one()
            assert report["job_id"] == owner.job_id
            return {
                "report": dict(report), "studentId": owner.student_id,
                "targetJobId": owner.job_id, "applications": [dict(row) for row in rows],
                "targetActiveCount": sum(row["job_id"] == owner.job_id
                                         and row["status"] != "withdrawn" for row in rows),
            }
    finally:
        await engine.dispose()


if __name__ == "__main__":
    data = asyncio.run(capture())
    with Path(sys.argv[1]).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    print("Read-only synthetic state recorded; target active count:", data["targetActiveCount"])
