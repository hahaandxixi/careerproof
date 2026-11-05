"""Diagnostic boundary-test provenance, not curated technical experience data.

Source: output/review-workspace-20261105/matrix-states-{fixture.py,data.json}
Only the contradictory matrix-states job is excluded from product discovery/history.
The three coherent experience scenarios remain visible with their existing disclosure.
This is a read policy only. No historical snapshot or persistent metadata is changed.
"""
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.models.recruitment import Job

FIXTURE_JOB_OWNERS = {
    UUID("1233f1e2-169f-4ea5-a5a0-542fa940e897"): UUID("568df462-33af-4824-9ebd-11a9b2760e0a"),
}


def fixture_job_predicate():
    return or_(*(and_(Job.id == job_id, Job.created_by == owner_id)
                 for job_id, owner_id in FIXTURE_JOB_OWNERS.items()))


def fixture_job_ids():
    return select(Job.id).where(fixture_job_predicate())
