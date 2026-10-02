from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1 import analysis


@pytest.mark.parametrize(
    "task_type", ["job_match", "resume_parse", "project_scan", "application_verification"]
)
async def test_task_events_releases_authorization_transaction_before_stream(
    monkeypatch, task_type
):
    class Session:
        committed = False

        async def commit(self):
            self.committed = True

    class Service:
        def __init__(self, session):
            self.session = session

        async def get_task(self, task_id, current_user):
            assert not self.session.committed
            return SimpleNamespace(task_type=task_type)

    monkeypatch.setattr(analysis, "AnalysisService", Service)
    session = Session()
    response = await analysis.task_events(uuid4(), SimpleNamespace(), session)
    assert session.committed
    assert response.media_type == "text/event-stream"
