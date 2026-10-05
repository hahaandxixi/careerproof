"""Read-only independent checks of the authorized closure synthetic run."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.analysis import AnalysisTask, MatchItem, MatchReport
from app.models.identity import StudentProfile
from app.models.recruitment import Application


def material_key(report):
    return sorted((m["kind"], m["id"]) for m in report.materials_snapshot)


async def main(require_complete):
    run = "closure-20261005"
    url = make_url(os.environ["CAREERPROOF_CLOSURE_DATABASE_URL"])
    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "127.0.0.1" and url.port == 5432
    assert url.database == f"cp_e2e_{run}"
    root = Path(__file__).resolve().parents[3]
    fixture = json.loads((root / "backend/.tmp/e2e" / f"{run}.json").read_text(encoding="utf-8-sig"))
    state = json.loads((root / "docs/evidence/20261005-E2E-student/state.json").read_text(encoding="utf-8-sig"))
    assert fixture["runId"] == run
    student_id = UUID(fixture["accounts"]["student"]["userId"])
    results = {"runId": run, "readOnly": True, "applications": {}, "reports": {}, "changes": {}}
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            assert await session.scalar(text("SELECT current_database()")) == f"cp_e2e_{run}"
            assert await session.scalar(text("SHOW transaction_read_only")) == "on"
            for slot, initial in fixture["applications"].items():
                app = await session.get(Application, UUID(initial["id"]))
                assert app is not None and app.status != "withdrawn"
                digest = hashlib.sha256(json.dumps(app.report_snapshot, sort_keys=True, ensure_ascii=False,
                                                   separators=(",", ":")).encode("utf-8")).hexdigest()
                assert digest == initial["snapshotSha256"], f"Fixed snapshot changed: {slot}"
                profile = await session.get(StudentProfile, app.student_id)
                expected_student = "studentA2" if slot == "A2" else "student"
                assert profile.user_id == UUID(fixture["accounts"][expected_student]["userId"])
                results["applications"][slot] = {"id": str(app.id), "status": app.status,
                                                  "snapshotSha256": digest, "matchesOriginal": True}
            reports = {}
            requirement_ids = {}
            for label, key in (("baseline", "baseReportId"), ("R1", "reportR1"), ("R2", "reportR2"), ("R3", "reportR3")):
                if not state.get(key):
                    assert not require_complete, f"Missing final report: {label}"
                    results["reports"][label] = {"status": "pending"}
                    continue
                report = await session.get(MatchReport, UUID(state[key]))
                assert report is not None and report.candidate_ref == str(student_id)
                task = await session.get(AnalysisTask, report.analysis_task_id)
                assert task.created_by == student_id and task.status == "completed"
                reports[label] = report
                requirement_ids[label] = set(await session.scalars(
                    select(MatchItem.requirement_id).where(MatchItem.report_id == report.id)
                ))
                assert requirement_ids[label], f"Report has no requirement items: {label}"
                results["reports"][label] = {"id": str(report.id), "jobId": str(report.job_id),
                                             "candidateMatchesOwner": True, "taskStatus": task.status,
                                             "materials": material_key(report),
                                             "requirementIds": sorted(str(i) for i in requirement_ids[label])}
            for before, after, material_change, job_change in (("baseline", "R1", True, False),
                                                               ("R1", "R2", False, True),
                                                               ("R2", "R3", True, True)):
                if before not in reports or after not in reports:
                    continue
                a, b = reports[before], reports[after]
                assert a.id != b.id
                assert (material_key(a) != material_key(b)) == material_change
                assert (a.job_id != b.job_id) == job_change
                if not job_change:
                    assert requirement_ids[before] == requirement_ids[after]
                else:
                    assert requirement_ids[before].isdisjoint(requirement_ids[after])
                results["changes"][f"{before}->{after}"] = {"materialsChanged": material_change,
                                                               "jobChanged": job_change}
            if "R2" in reports:
                assert reports["R2"].job_id == UUID(state["jobIdC"])
            if "R3" in reports:
                assert reports["R3"].job_id == reports["baseline"].job_id
            await session.rollback()
        results["writes"] = 0
        results["completeReportChain"] = len(reports) == 4
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-complete", action="store_true")
    asyncio.run(main(parser.parse_args().require_complete))
