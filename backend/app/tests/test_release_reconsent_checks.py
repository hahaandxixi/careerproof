"""Exercise the smoke assertions against real isolated APIs and bad-response mutations."""

from copy import deepcopy
from uuid import UUID

import pytest

from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus
from app.models.recruitment import Application
from app.tests.test_applications_api import close, setup
from app.tests.test_real_matching import matching_db as matching_db
from evals.release_smoke import verify_reconsent


@pytest.mark.parametrize('mutation', [None, 'stale_snapshot', 'wrong_report',
                                     'duplicate_id', 'withdrawn_board'])
async def test_reconsent_smoke_checks_reject_incomplete_chain(
    matching_db, tmp_path, monkeypatch, mutation,  # noqa: F811 - injected imported fixture
):
    hr, student, other, job, rid, _, _, factory = await setup(
        matching_db, tmp_path, monkeypatch,
    )
    try:
        original = (await student.post('/api/v1/applications', json={
            'reportId': str(rid), 'shareConsent': True,
        })).json()['data']
        old_id = original['id']
        frozen = (await hr.post(f'/api/v1/applications/{old_id}/view')).json()['data']['report']
        notices = (await hr.get('/api/v1/notifications')).json()['data']['items']
        assert (await student.post(f'/api/v1/applications/{old_id}/withdraw')).status_code == 200
        async with factory() as session:
            old = await session.get(MatchReport, rid)
            owner = (await session.get(AnalysisTask, old.analysis_task_id)).created_by
            task = AnalysisTask(created_by=owner, task_type='job_match',
                                status=TaskStatus.COMPLETED)
            session.add(task)
            await session.flush()
            new = MatchReport(analysis_task_id=task.id, job_id=old.job_id,
                              candidate_ref=old.candidate_ref,
                              job_snapshot=deepcopy(old.job_snapshot),
                              materials_snapshot=deepcopy(old.materials_snapshot),
                              summary='独立合成新版报告', overall_score=40)
            session.add(new)
            await session.commit()
            new_id = str(new.id)
        report = (await student.get(f'/api/v1/match-reports/{new_id}')).json()['data']
        submission_calls = 0

        async def data(client, method, endpoint, expected=200, **kwargs):
            nonlocal submission_calls
            response = await client.request(method, endpoint, **kwargs)
            assert response.status_code == expected, (method, endpoint, response.status_code)
            value = response.json().get('data')
            if expected != 200 and expected != 201:
                return value
            if method == 'POST' and endpoint == '/api/v1/applications':
                submission_calls += 1
                if mutation == 'wrong_report':
                    value['reportId'] = str(rid)
                if mutation == 'duplicate_id' and submission_calls > 1:
                    value['id'] = 'different-duplicate-id'
            if mutation == 'stale_snapshot' and endpoint.endswith('/view'):
                value['report'] = deepcopy(frozen)
            if mutation == 'withdrawn_board' and endpoint.endswith('/applications'):
                value['items'].append({'id': old_id})
            return value

        arguments = (data, student, hr, other, job['id'], old_id, report,
                     [notice['id'] for notice in notices])
        if mutation:
            with pytest.raises(AssertionError):
                await verify_reconsent(*arguments)
        else:
            result = await verify_reconsent(*arguments)
            assert result['report'] == report
            async with factory() as session:
                old = await session.get(Application, UUID(old_id))
                assert old.status == 'withdrawn' and old.report_snapshot == frozen
    finally:
        await close(hr, student, other)
