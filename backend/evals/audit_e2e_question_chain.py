"""Read-only proof of a synthetic linked-question growth chain."""
import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.analysis import AnalysisTask, MatchReport
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.recruitment import Application, JobRequirement
from app.services.applications import reply_context_for_requirement
from evals.audit_e2e_budget_state import audit as audit_budget
from evals.e2e_verification import validate_environment


async def audit(run, evidence_subdir):
    assert re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', evidence_subdir)
    root = Path(__file__).resolve().parents[2]
    state = json.loads((root / 'docs/evidence' / evidence_subdir / 'state.json').read_text(
        encoding='utf-8',
    ))
    storage = root / 'backend/.tmp/e2e-storage' / run
    url = make_url(settings.database_url).set(database=f'cp_e2e_{run}')
    validate_environment(run, url.render_as_string(hide_password=False), storage, False, 'mock')
    fixture = json.loads((root / f'backend/.tmp/e2e/{run}.json').read_text(encoding='utf-8-sig'))
    owner = fixture['accounts']['student']['userId']
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with async_sessionmaker(engine)() as session:
            await session.execute(text('SET TRANSACTION READ ONLY'))
            growth = await session.get(EvidenceGrowthTask, UUID(state['replyTaskId']))
            base = await session.get(MatchReport, growth.base_report_id)
            target = await session.get(MatchReport, UUID(state['replyReportId']))
            application = await session.get(Application, UUID(fixture['applications']['B']['id']))
            assert str(growth.created_by) == base.candidate_ref == target.candidate_ref == owner
            assert base.id == application.report_id
            assert growth.analysis_task_id == target.analysis_task_id
            assert base.job_id == target.job_id
            assert base.job_snapshot['requirements'] == target.job_snapshot['requirements']
            assert base.id != target.id
            analysis = await session.get(AnalysisTask, target.analysis_task_id)
            assert analysis.status.value == 'completed'
            for report_id in fixture['reports'].values():
                original = await session.get(MatchReport, UUID(report_id))
                requirements = (await session.scalars(select(JobRequirement).where(
                    JobRequirement.job_id == original.job_id,
                ).order_by(JobRequirement.created_at))).all()
                assert original.job_snapshot['requirements'] == [{
                    'id': str(row.id), 'title': row.raw_text, 'skill': row.skill_name,
                    'weight': row.weight,
                } for row in requirements]
            assert growth.materials and growth.base_snapshot['job'] == base.job_snapshot
            reply = reply_context_for_requirement(application, growth.requirement_id)
            assert reply and '请说明本人负责的部分' in reply['text']
            return {
                'run': run, 'readOnlyTransaction': True, 'sameOwnerAndJob': True,
                'sameFrozenRequirements': True, 'originalDeliveryReportRetained': True,
                'baseReportId': str(base.id), 'newReportId': str(target.id),
                'growthTaskId': str(growth.id), 'storedGrowthStatus': growth.status,
                'targetAnalysisStatus': analysis.status.value,
                'allSeededJobRequirementsStillMatch': True,
                'linkedQuestionRequirementId': str(growth.requirement_id),
                'linkedQuestionApplicationId': reply['applicationId'],
                'savedNewMaterialVersions': [row['id'] for row in growth.materials],
                'replySha256': hashlib.sha256(application.reply_text.encode()).hexdigest(),
                'replyReferences': application.reply_references,
                'ledgerAndSnapshots': await audit_budget(run),
            }
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--evidence-subdir', required=True)
    args = parser.parse_args()
    result = asyncio.run(audit(args.run, args.evidence_subdir))
    assert result['ledgerAndSnapshots']['allSeededSnapshotsUnchanged']
    print(json.dumps(result, ensure_ascii=False, indent=2))
