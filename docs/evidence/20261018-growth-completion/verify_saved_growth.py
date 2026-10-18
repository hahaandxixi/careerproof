"""Read only the named synthetic growth/report/application; emit IDs and digests."""
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.analysis import AnalysisTask, MatchItem, MatchReport
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.recruitment import Application


async def main():
    engine = create_async_engine(settings.database_url, hide_parameters=True,
                                 isolation_level="REPEATABLE READ")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            growth = await session.get(EvidenceGrowthTask, UUID("0c67132f-f355-4819-819f-29b8529afa9e"))
            task = await session.get(AnalysisTask, growth.analysis_task_id)
            report = await session.scalar(select(MatchReport).where(MatchReport.analysis_task_id == task.id))
            application = await session.get(Application, UUID("b756d9c2-f7e9-47d4-a12c-8e1bc61a54f3"))
            assert str(application.report_id) == "1b6c0425-848a-4229-8cc8-cc4d4447ba54"
            assert application.report_id == growth.base_report_id != report.id
            assert application.status == "replied"
            # GrowthService derives the public "compared" state from the finished
            # analysis/report. The stored row is allowed to remain "analyzing".
            assert growth.status in {"analyzing", "compared"}
            assert task.status.value == "completed"
            metadata = report.analysis_metadata
            # Saved report metadata deliberately uses null for the rules provider;
            # AgentStep payload uses the separate literal "rules".
            assert metadata.get("mode") == "rules"
            assert metadata.get("provider") is None
            assert metadata.get("skippedReason") == "consent_not_granted"
            consent = task.input_snapshot.get("externalAiConsent", task.input_snapshot.get("external_ai_consent"))
            assert consent is False, consent
            redis = await session.scalar(select(MatchItem).where(
                MatchItem.report_id == report.id,
                MatchItem.requirement_id == UUID("91064500-530c-4627-928b-b37a1778d54c")))
            result = {"growthId": str(growth.id), "storedStatus": growth.status,
                      "analysisStatus": task.status.value,
                      "baseReportId": str(growth.base_report_id), "newReportId": str(report.id),
                      "analysisTaskId": str(task.id), "externalAiConsent": consent,
                      "provider": metadata.get("provider"), "mode": metadata.get("mode"),
                      "applicationId": str(application.id), "applicationReportId": str(application.report_id),
                      "applicationStatus": application.status,
                      "applicationSnapshotSha256": hashlib.sha256(json.dumps(
                          application.report_snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                      "redisVerdict": redis.verdict, "redisExplanation": redis.explanation,
                      "savedMaterials": growth.materials}
            output = Path("../docs/evidence/20261018-growth-completion/saved-result.json")
            assert not output.exists()
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Named synthetic growth complete; old application still binds base report; no external consent.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
