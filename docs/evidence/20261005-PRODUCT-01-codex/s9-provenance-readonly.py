"""Independent DB proof for the dedicated synthetic reference-report fixture."""
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.analysis import AnalysisTask, MatchReport
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.identity import User
from app.models.portfolio import ProjectVersion
from app.services.analysis import AnalysisService
from app.services.growth_answer import GrowthAnswerService


async def main():
    url = make_url(os.environ["CAREERPROOF_CLOSURE_DATABASE_URL"])
    assert (url.host, url.port, url.database) == ("127.0.0.1", 5432, "cp_e2e_closure-20261005")
    root = Path(__file__).resolve().parents[3]
    fixture = json.loads((root / "backend/.tmp/e2e/closure-20261005.json").read_text(encoding="utf-8-sig"))
    assert fixture["runId"] == "closure-20261005"
    state = json.loads((root / "docs/evidence/20261007-PRODUCT-01-pages/s9-state.json").read_text(encoding="utf-8-sig"))
    owner = UUID(fixture["accounts"]["student"]["userId"])
    output = {"readOnly": True, "reportId": state["s9ReportId"], "taskId": state["s9TaskId"]}
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            assert await session.scalar(text("SHOW transaction_read_only")) == "on"
            user = await session.get(User, owner)
            report = await session.get(MatchReport, UUID(state["s9ReportId"]))
            assert report is not None and report.candidate_ref == str(owner)
            analysis = await session.get(AnalysisTask, report.analysis_task_id)
            assert analysis.created_by == owner and analysis.status == "completed"
            task = await session.get(EvidenceGrowthTask, UUID(state["s9TaskId"]))
            assert task.created_by == owner and task.base_report_id == report.id
            view = await AnalysisService(session).get_report(report.id, user)
            reference_materials = [material for material in view.materials if material.kind == "project" and material.material_role == "reference"]
            assert reference_materials
            for material in reference_materials:
                version = await session.get(ProjectVersion, material.id)
                assert version is not None and version.material_role == "reference"
                assert version.content_hash == material.content_hash
            item = next(item for item in view.items if item.requirement_id == task.requirement_id)
            references = [entry for entry in item.evidence_list if entry.provenance == "reference"]
            assert references and all(entry.provenance == "reference" for entry in item.evidence_list)
            # Reference-only sources receive no personal practice level.
            # A resume claim may retain claimed_only; it must not turn the
            # reference implementation into a numeric personal rating.
            assert item.verdict == "claimed_only" and item.evidence_level is None
            assert "参考" in item.evidence_level_label
            draft = await GrowthAnswerService(session).get(task.id, user)
            assert draft and draft["references"]
            reference_ids = {entry.citation_id for entry in references}
            assert all(entry["provenance"] == "reference" and entry["available"] and entry["citationId"] in reference_ids and entry["reportId"] == str(report.id) and entry["requirementId"] == str(task.requirement_id) for entry in draft["references"])
            output.update({"analysisStatus": str(analysis.status), "ownerMatches": True, "referenceMaterialCount": len(reference_materials), "referenceEvidenceCount": len(references), "verdict": item.verdict, "evidenceLevel": item.evidence_level, "evidenceLevelLabel": item.evidence_level_label, "savedDraftReferenceCount": len(draft["references"]), "draftReferencesMatchReportAndOriginalRequirement": True, "referenceDidNotPromotePersonalPractice": True})
            await session.rollback()
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
