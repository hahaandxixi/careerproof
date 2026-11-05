"""Review/consent revision contract on synthetic SQLite; not PG concurrency proof."""

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql

from app.models.analysis import EvidenceSource, MatchItem, MatchReport, SkillEvidence
from app.models.enums import ConfirmationStatus, VerificationStatus
from app.models.identity import User
from app.models.portfolio import ResumeSection, ResumeVersion
from app.models.recruitment import Application, ApplicationEvent, Skill
from app.schemas.analysis import EvidenceReviewUpdate, MatchReportView
from app.schemas.applications import ApplicationCreate
from app.services.analysis import AnalysisService
from app.tests.test_applications_api import close, setup
from app.tests.test_jobs_api import jobs_db as jobs_db
from app.tests.test_jobs_api import register


@pytest.fixture
async def consent_case(jobs_db, tmp_path, monkeypatch):  # noqa: F811 - imported fixture
    case = await setup(jobs_db, tmp_path, monkeypatch)
    hr, student, outsider, job, rid, resume_id, _, factory = case
    async with factory() as session:
        report = await session.get(MatchReport, rid)
        item = await session.scalar(select(MatchItem).where(MatchItem.report_id == rid))
        version = await session.scalar(
            select(ResumeVersion).where(ResumeVersion.resume_id == resume_id)
        )
        section = ResumeSection(
            resume_version_id=version.id, section_type="synthetic", content="Synthetic evidence"
        )
        skill = Skill(name=f"revision-fixture-{uuid4().hex}")
        session.add_all([section, skill])
        await session.flush()
        source = EvidenceSource(
            resume_section_id=section.id, content_hash="a" * 64, excerpt="Synthetic evidence"
        )
        session.add(source)
        await session.flush()
        evidence = SkillEvidence(
            analysis_task_id=report.analysis_task_id, skill_id=skill.id,
            evidence_source_id=source.id, confidence=1,
            verification_status=VerificationStatus.VERIFIED,
        )
        session.add(evidence)
        await session.flush()
        item.evidence_id = evidence.id
        requirement_id, evidence_id = item.requirement_id, evidence.id
        await session.commit()
    try:
        yield case, requirement_id, evidence_id
    finally:
        await close(hr, student, outsider)


def submission(rid, revision):
    return {"reportId": str(rid), "shareConsent": True, "expectedReviewRevision": revision}


@pytest.mark.parametrize("revision", [None, 0, -1, True, 1.5, "1"])
def test_schema_rejects_missing_or_non_positive_integer_revision(revision):
    payload = submission(uuid4(), revision)
    if revision is None:
        payload.pop("expectedReviewRevision")
    with pytest.raises(ValidationError):
        ApplicationCreate.model_validate(payload)


async def test_missing_revision_is_422_without_consent_write(consent_case):
    (hr, student, other, job, rid, _, _, factory), _, _ = consent_case
    response = await student.post(
        "/api/v1/applications", json={"reportId": str(rid), "shareConsent": True}
    )
    assert response.status_code == 422
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Application)) == 0
        assert await session.scalar(select(func.count()).select_from(ApplicationEvent)) == 0


async def test_legacy_snapshot_remains_readable_without_inventing_revision(consent_case):
    (hr, student, other, job, rid, _, _, factory), _, _ = consent_case
    current = (await student.get(f"/api/v1/match-reports/{rid}")).json()["data"]
    assert current["reviewRevision"] == 1
    legacy = deepcopy(current)
    legacy.pop("reviewRevision")
    original = deepcopy(legacy)
    restored = MatchReportView.model_validate(legacy)
    assert restored.review_revision is None
    assert legacy == original  # Reading a historical snapshot does not rewrite it.
    with pytest.raises(ValidationError):
        ApplicationCreate.model_validate(submission(rid, restored.review_revision))


async def test_review_revision_stale_conflict_and_fresh_snapshot(consent_case):
    (hr, student, other, job, rid, _, _, factory), req, _ = consent_case
    before = (await student.get(f"/api/v1/match-reports/{rid}")).json()["data"]
    assert before["reviewRevision"] == 1
    reviewed = await student.patch(f"/api/v1/match-reports/{rid}/items/{req}/review",
                                   json={"status": "rejected", "note": "Synthetic correction"})
    assert reviewed.status_code == 200, reviewed.text
    after = (await student.get(f"/api/v1/match-reports/{rid}")).json()["data"]
    assert after["reviewRevision"] == 2
    assert after["items"][0]["confirmationStatus"] == "rejected"
    for invalid_revision in (1, 3):
        stale = await student.post("/api/v1/applications", json=submission(rid, invalid_revision))
        assert stale.status_code == 409, stale.text
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Application)) == 0
        assert await session.scalar(select(func.count()).select_from(ApplicationEvent)) == 0
    created = await student.post("/api/v1/applications", json=submission(rid, 2))
    assert created.status_code == 201, created.text
    async with factory() as session:
        saved = await session.get(Application, UUID(created.json()["data"]["id"]))
        assert saved.report_snapshot["reviewRevision"] == 2
        assert saved.report_snapshot["items"][0]["confirmationStatus"] == "rejected"


async def test_authorized_retry_keeps_original_snapshot_after_review(
    consent_case, jobs_db,  # noqa: F811 - imported fixture
):
    (hr, student, other, job, rid, _, _, factory), req, _ = consent_case
    created = await student.post("/api/v1/applications", json=submission(rid, 1))
    assert created.status_code == 201, created.text
    aid = UUID(created.json()["data"]["id"])
    async with factory() as session:
        item = await session.get(Application, aid)
        snapshot = deepcopy(item.report_snapshot)
        version, consent_at = item.version, item.consent_at
    reviewed = await student.patch(f"/api/v1/match-reports/{rid}/items/{req}/review",
                                   json={"status": "corrected", "note": "Later review"})
    assert reviewed.status_code == 200
    for revision in (1, 2):
        repeated = await student.post("/api/v1/applications", json=submission(rid, revision))
        assert repeated.status_code == 201, repeated.text
        assert repeated.json()["data"]["id"] == str(aid)
    app, _ = jobs_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger:
        await register(stranger, "stranger-student@example.com", "student")
        denied = await stranger.post("/api/v1/applications", json=submission(rid, 1))
        assert denied.status_code == 404
    async with factory() as session:
        item = await session.get(Application, aid)
        assert item.report_snapshot == snapshot
        assert item.version == version and item.consent_at == consent_at
        assert await session.scalar(select(func.count()).select_from(Application)) == 1
        assert await session.scalar(select(func.count()).select_from(ApplicationEvent)) == 1


async def test_withdrawn_consent_requires_fresh_revision(consent_case):
    (hr, student, other, job, rid, _, _, factory), req, _ = consent_case
    response = await student.post("/api/v1/applications", json=submission(rid, 1))
    assert response.status_code == 201, response.text
    old_id = UUID(response.json()["data"]["id"])
    async with factory() as session:
        old_snapshot = deepcopy((await session.get(Application, old_id)).report_snapshot)
    assert (await student.post(f"/api/v1/applications/{old_id}/withdraw")).status_code == 200
    assert (await student.patch(f"/api/v1/match-reports/{rid}/items/{req}/review",
                               json={"status": "accepted"})).status_code == 200
    assert (await student.post("/api/v1/applications", json=submission(rid, 1))).status_code == 409
    fresh = await student.post("/api/v1/applications", json=submission(rid, 2))
    assert fresh.status_code == 201, fresh.text
    assert fresh.json()["data"]["id"] != str(old_id)
    async with factory() as session:
        old = await session.get(Application, old_id)
        assert old.status == "withdrawn" and old.report_snapshot == old_snapshot
        current = await session.get(Application, UUID(fresh.json()["data"]["id"]))
        assert current.report_snapshot["reviewRevision"] == 2
        assert current.report_snapshot["items"][0]["confirmationStatus"] == "accepted"


async def test_reused_session_refreshes_report_and_evidence_under_scoped_lock(consent_case):
    (hr, student, other, job, rid, _, _, factory), req, eid = consent_case
    async with factory() as reader:
        stale_report = await reader.get(MatchReport, rid)
        stale_evidence = await reader.get(SkillEvidence, eid)
        owner = await reader.scalar(select(User).where(User.email == "student@example.com"))
        await reader.commit()
        locks = []

        def capture(state):
            if state.is_select and state.statement._for_update_arg is not None:
                locks.append(str(state.statement.compile(dialect=postgresql.dialect())))

        async with factory() as writer:
            event.listen(writer.sync_session, "do_orm_execute", capture)
            await AnalysisService(writer).review_evidence(
                rid, req, EvidenceReviewUpdate(status=ConfirmationStatus.CORRECTED, note="New"),
                owner,
            )
        assert stale_report.version == 1
        assert stale_evidence.confirmation_status == ConfirmationStatus.PENDING
        event.listen(reader.sync_session, "do_orm_execute", capture)
        view = await AnalysisService(reader).get_report(rid, owner)
        assert view.review_revision == 2
        assert view.items[0].confirmation_status == ConfirmationStatus.CORRECTED
        assert view.items[0].reviewer_note == "New"
        assert reader.in_transaction()  # Lock retained for a caller's consent transaction.
        assert any("FOR UPDATE OF match_reports" in sql for sql in locks)
        assert any("FOR SHARE OF match_reports" in sql for sql in locks)
        assert all("OF match_reports" in sql for sql in locks)
