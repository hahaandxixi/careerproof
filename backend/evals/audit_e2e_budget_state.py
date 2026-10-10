"""Read-only, run-bound ledger/snapshot audit for synthetic E2E acceptance."""
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.ai_budget import AiBudgetReservation
from app.models.ai_request_attempt import AiRequestAttempt
from app.models.analysis import AnalysisTask
from app.models.recruitment import Application
from evals.e2e_verification import validate_environment


async def audit(run):
    target = make_url(settings.database_url).set(database=f'cp_e2e_{run}')
    storage = Path(__file__).resolve().parents[1] / '.tmp' / 'e2e-storage' / run
    validate_environment(run, target.render_as_string(hide_password=False), storage, False, 'mock')
    fixture = json.loads((storage.parents[1] / 'e2e' / f'{run}.json').read_text(encoding='utf-8'))
    assert fixture['runId'] == run
    expected = {row['id']: row['snapshotSha256'] for row in fixture['applications'].values()}
    engine = create_async_engine(target, hide_parameters=True)
    try:
        async with async_sessionmaker(engine)() as session:
            await session.execute(text('SET TRANSACTION READ ONLY'))
            snapshots = {}
            for row in (await session.scalars(select(Application))).all():
                snapshots[str(row.id)] = hashlib.sha256(json.dumps(
                    row.report_snapshot, sort_keys=True, ensure_ascii=False,
                    separators=(',', ':'),
                ).encode()).hexdigest()
            attempts = (await session.scalars(select(AiRequestAttempt))).all()
            reservations = (await session.scalars(select(AiBudgetReservation))).all()
            tasks = (await session.scalars(select(AnalysisTask).where(
                AnalysisTask.task_type == 'application_verification',
            ))).all()
            return {
                'run': run, 'readOnlyTransaction': True,
                'snapshotHashes': snapshots, 'allSeededSnapshotsUnchanged': snapshots == expected,
                'attempts': [{
                    'id': str(row.id), 'taskId': str(row.analysis_task_id),
                    'state': row.state, 'reason': row.reason,
                    'input': row.usage_input_tokens, 'output': row.usage_output_tokens,
                } for row in attempts],
                'reservations': [{
                    'attemptId': str(row.attempt_id), 'state': row.state,
                    'inputBound': row.input_bound, 'outputBound': row.output_bound,
                    'actualInput': row.actual_input_tokens,
                    'actualOutput': row.actual_output_tokens,
                } for row in reservations],
                'verificationTasks': [
                    {'id': str(row.id), 'status': row.status.value} for row in tasks
                ],
            }
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    result = asyncio.run(audit(args.run))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['allSeededSnapshotsUnchanged'] else 1)
