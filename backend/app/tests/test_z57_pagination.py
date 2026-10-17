"""Z57 paginated-list contract regressions on isolated SQLite; never calls a model.

Every assertion here is about the backend paging contract defined for
/applications/mine, /jobs/{job_id}/applications, /match-reports and
/growth-tasks: a {items,total,page,pageSize} envelope, page clamping, stable
created_at DESC / id DESC ordering and unchanged ownership predicates.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.analysis import AnalysisTask, MatchReport
from app.models.enums import TaskStatus, UserRole
from app.models.evidence_growth import EvidenceGrowthTask
from app.models.identity import StudentProfile, User
from app.models.recruitment import Application, Job
from app.tests.test_applications_api import close, setup
from app.tests.test_evidence_growth import plan
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import create_job, match_report, upload_materials

# Fixtures come from the modules that own them; importing the fixture functions
# directly would shadow the same-named test parameters (F811).
pytest_plugins = ["app.tests.test_jobs_api", "app.tests.test_real_matching"]

API = "/api/v1"


async def fetch_page(client, path, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = await client.get(f"{API}{path}" + (f"?{query}" if query else ""))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert isinstance(data, dict), (
        f"{path} must return an items/total/page/pageSize envelope, "
        f"got {type(data).__name__}"
    )
    for key in ("items", "total", "page", "pageSize"):
        assert key in data, f"{path} envelope is missing {key}: {sorted(data)}"
    return data


async def source_scope(factory, job_id, report_id):
    """Resolve the ownership facts a seeded row needs, without HTTP writes."""
    async with factory() as session:
        job = await session.get(Job, UUID(job_id))
        report = await session.get(MatchReport, UUID(report_id))
        student_id = UUID(report.candidate_ref)
        user_id = await session.scalar(
            select(User.id)
            .join(StudentProfile, StudentProfile.user_id == User.id)
            .where(StudentProfile.id == student_id)
        )
        return {
            "student_id": student_id,
            "report_id": UUID(report_id),
            "enterprise_id": job.enterprise_id,
            "created_by": job.created_by,
            "company_name": job.company_name,
            "user_id": user_id,
        }


async def seed_owned_applications(factory, scope, *, count, statuses=None, created=None):
    """One published job + one application per index; returns rows in creation order."""
    statuses = statuses or ["submitted"] * count
    rows = []
    async with factory() as session:
        for index in range(count):
            job = Job(
                enterprise_id=scope["enterprise_id"],
                created_by=scope["created_by"],
                title=f"Z57 分页岗位 {index}",
                company_name=scope["company_name"],
                status="published",
            )
            session.add(job)
            await session.flush()
            application = Application(
                job_id=job.id,
                student_id=scope["student_id"],
                report_id=scope["report_id"],
                report_snapshot={"items": [], "summary": f"Z57 分页记录 {index}"},
                status=statuses[index],
                consent_at=datetime.now(UTC),
                consent_version="application-report-v1",
                created_at=created[index] if created else datetime.now(UTC),
            )
            session.add(application)
            await session.flush()
            rows.append({"application_id": str(application.id), "job_id": str(job.id)})
        await session.commit()
    return rows


def ascending(base, count, step_minutes=1):
    return [base + timedelta(minutes=index * step_minutes) for index in range(count)]


async def test_owned_applications_page_reaches_past_the_first_hundred(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        scope = await source_scope(factory, job["id"], str(rid))
        seeded = await seed_owned_applications(
            factory, scope, count=105, created=ascending(datetime(2026, 1, 1, tzinfo=UTC), 105)
        )
        first = await fetch_page(student, "/applications/mine")
        assert first["total"] == 105 and first["page"] == 1 and first["pageSize"] == 20
        assert len(first["items"]) == 20
        assert [row["id"] for row in first["items"]] == [
            row["application_id"] for row in reversed(seeded)
        ][:20]
        # The 101st owned record only exists on the last page; the old fixed 100-row
        # list could never return it.
        last = await fetch_page(student, "/applications/mine", page=6)
        assert last["page"] == 6 and len(last["items"]) == 5 and last["total"] == 105
        assert last["items"][0]["id"] == seeded[4]["application_id"]
        assert (await fetch_page(student, "/applications/mine", page=99))["page"] == 6
    finally:
        await close(hr, student, other)


async def test_equal_timestamps_order_stably_without_duplicates(jobs_db, tmp_path, monkeypatch):
    hr, student, other, job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        scope = await source_scope(factory, job["id"], str(rid))
        same = datetime(2026, 2, 1, tzinfo=UTC)
        seeded = await seed_owned_applications(factory, scope, count=45, created=[same] * 45)
        seen = []
        for page in (1, 2, 3):
            data = await fetch_page(student, "/applications/mine", page=page)
            assert data["total"] == 45
            seen.extend(row["id"] for row in data["items"])
        # created_at ties must fall back to id DESC, so pages partition the rows exactly.
        assert len(seen) == 45 and len(set(seen)) == 45
        assert set(seen) == {row["application_id"] for row in seeded}
    finally:
        await close(hr, student, other)


async def test_exact_last_page_clamping_empty_and_query_bounds(jobs_db, tmp_path, monkeypatch):
    hr, student, other, job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    empty = AsyncClient(transport=ASGITransport(app=jobs_db[0]), base_url="http://test")
    try:
        scope = await source_scope(factory, job["id"], str(rid))
        await seed_owned_applications(
            factory, scope, count=40, created=ascending(datetime(2026, 3, 1, tzinfo=UTC), 40)
        )
        exact = await fetch_page(student, "/applications/mine", page=2)
        assert exact["page"] == 2 and len(exact["items"]) == 20 and exact["total"] == 40
        clamped = await fetch_page(student, "/applications/mine", page=3)
        assert clamped["page"] == 2 and len(clamped["items"]) == 20
        # An empty owned dataset still reports page 1, never page 0 or a missing page.
        await register(empty, "z57-empty@example.com", "student")
        none = await fetch_page(empty, "/applications/mine", page=7)
        assert none == {"items": [], "total": 0, "page": 1, "pageSize": 20}
        for bad in ("page=0", "pageSize=0", "pageSize=101"):
            response = await student.get(f"{API}/applications/mine?{bad}")
            assert response.status_code == 422, f"{bad} -> {response.status_code}"
    finally:
        await empty.aclose()
        await close(hr, student, other)


async def test_job_filter_applies_before_count_and_stays_owner_scoped(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, other, job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    outsider = AsyncClient(transport=ASGITransport(app=jobs_db[0]), base_url="http://test")
    try:
        scope = await source_scope(factory, job["id"], str(rid))
        seeded = await seed_owned_applications(
            factory, scope, count=105, created=ascending(datetime(2026, 4, 1, tzinfo=UTC), 105)
        )
        oldest = seeded[0]
        filtered = await fetch_page(student, "/applications/mine", jobId=oldest["job_id"])
        assert filtered["total"] == 1 and filtered["page"] == 1
        assert [row["id"] for row in filtered["items"]] == [oldest["application_id"]]
        await register(outsider, "z57-outsider@example.com", "student")
        assert (await fetch_page(outsider, "/applications/mine", jobId=oldest["job_id"]))[
            "total"
        ] == 0
        assert (await fetch_page(outsider, "/applications/mine"))["total"] == 0
        assert (
            await student.get(f"{API}/applications/mine?jobId=not-a-uuid")
        ).status_code == 422
    finally:
        await outsider.aclose()
        await close(hr, student, other)


async def test_job_candidates_page_excludes_withdrawn_and_denies_non_managers(
    jobs_db, tmp_path, monkeypatch
):
    hr, student, outsider, job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        scope = await source_scope(factory, job["id"], str(rid))
        candidate_ids = []
        async with factory() as session:
            for index in range(23):
                user = User(
                    email=f"z57-candidate-{index}@example.com",
                    password_hash="synthetic",
                    display_name=f"候选人 {index}",
                    role=UserRole.STUDENT,
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(user_id=user.id)
                session.add(profile)
                await session.flush()
                candidate_ids.append(profile.id)
            await session.commit()
        statuses = ["submitted"] * 20 + ["withdrawn"] * 3
        async with factory() as session:
            for index, (candidate_id, status) in enumerate(
                zip(candidate_ids, statuses, strict=True)
            ):
                session.add(
                    Application(
                        job_id=UUID(job["id"]),
                        student_id=candidate_id,
                        report_id=scope["report_id"],
                        report_snapshot={"items": [], "summary": f"Z57 应聘 {index}"},
                        status=status,
                        consent_at=datetime.now(UTC),
                        consent_version="application-report-v1",
                        created_at=datetime(2026, 5, 1, tzinfo=UTC) - timedelta(minutes=index),
                    )
                )
            await session.commit()
        default_view = await fetch_page(hr, f"/jobs/{job['id']}/applications")
        assert default_view["total"] == 20 and default_view["pageSize"] == 20
        assert len(default_view["items"]) == 20
        assert all(row["status"] != "withdrawn" for row in default_view["items"])
        sized = await fetch_page(hr, f"/jobs/{job['id']}/applications", pageSize=7, page=3)
        assert sized["page"] == 3 and sized["total"] == 20 and len(sized["items"]) == 6
        clamped = await fetch_page(hr, f"/jobs/{job['id']}/applications", pageSize=7, page=9)
        assert clamped["page"] == 3
        assert (
            await outsider.get(f"{API}/jobs/{job['id']}/applications")
        ).status_code == 404
    finally:
        await close(hr, student, outsider)


async def test_match_report_history_pages_with_default_twenty(jobs_db, tmp_path, monkeypatch):
    hr, student, other, job, rid, _resume, _raw, factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        scope = await source_scope(factory, job["id"], str(rid))
        base = datetime(2026, 6, 1, tzinfo=UTC)
        seeded = []
        async with factory() as session:
            for index in range(25):
                task = AnalysisTask(
                    created_by=scope["user_id"],
                    task_type="job_match",
                    status=TaskStatus.COMPLETED,
                )
                session.add(task)
                await session.flush()
                report = MatchReport(
                    analysis_task_id=task.id,
                    job_id=UUID(job["id"]),
                    candidate_ref=str(scope["student_id"]),
                    candidate_name="测试用户",
                    summary=f"Z57 分页报告 {index}",
                    overall_score=50,
                    job_snapshot={"title": "分页岗位", "category": "software"},
                    materials_snapshot=[],
                    created_at=base + timedelta(minutes=index),
                )
                session.add(report)
                await session.flush()
                seeded.append(str(report.id))
            await session.commit()
        first = await fetch_page(student, "/match-reports")
        assert first["total"] == 26 and first["page"] == 1 and first["pageSize"] == 20
        assert len(first["items"]) == 20
        second = await fetch_page(student, "/match-reports", page=2)
        assert second["page"] == 2 and len(second["items"]) == 6
        # The fixture's own report is newest; seeded reports follow created_at DESC.
        assert [row["id"] for row in first["items"] + second["items"]] == [
            str(rid),
            *reversed(seeded),
        ]
        assert (await fetch_page(student, "/match-reports", page=99))["page"] == 2
        assert (await fetch_page(other, "/match-reports"))["total"] == 0
    finally:
        await close(hr, student, other)


async def test_growth_page_counts_rows_it_could_not_read_without_widening_catches(
    matching_db,
):
    app, factory = matching_db
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as hr,
        AsyncClient(transport=transport, base_url="http://test") as student,
    ):
        await register(hr, "z57-growth-hr@example.com")
        job = await create_job(hr)
        await register(student, "z57-growth-owner@example.com", "student")
        resume, project, version = await upload_materials(student)
        base = await match_report(student, job, resume, version)
        healthy = (
            await student.post(
                f"{API}/match-reports/{base['id']}/growth-tasks", json=plan(base)
            )
        ).json()["data"]
        base_time = datetime(2026, 7, 1, tzinfo=UTC)
        async with factory() as session:
            owner_id = await session.scalar(
                select(User.id).where(User.email == "z57-growth-owner@example.com")
            )
            healthy_row = await session.get(EvidenceGrowthTask, UUID(healthy["id"]))
            snapshot = deepcopy(healthy_row.base_snapshot)
        seeded = []
        async with factory() as session:
            for index in range(23):
                drifted = deepcopy(snapshot)
                requirement_id = str(uuid4())
                extra_item = deepcopy(drifted["report"]["items"][0])
                extra_item["requirementId"] = requirement_id
                drifted["report"]["items"].append(extra_item)
                row = EvidenceGrowthTask(
                    created_by=owner_id,
                    base_report_id=UUID(base["id"]),
                    requirement_id=UUID(requirement_id),
                    base_snapshot=drifted,
                    plan=plan(base),
                    materials=[],
                    status="planned",
                    created_at=base_time + timedelta(minutes=index),
                )
                session.add(row)
                await session.flush()
                seeded.append(str(row.id))
            corrupted = deepcopy(snapshot)
            corrupted["report"]["items"][0]["requirementId"] = "not-a-uuid"
            broken = EvidenceGrowthTask(
                created_by=owner_id,
                base_report_id=UUID(base["id"]),
                requirement_id=uuid4(),
                base_snapshot=corrupted,
                plan=plan(base),
                materials=[],
                status="planned",
                created_at=base_time + timedelta(minutes=60),
            )
            session.add(broken)
            await session.flush()
            broken_id = str(broken.id)
            await session.commit()
        first = await fetch_page(student, "/growth-tasks")
        assert first["total"] == 25 and first["pageSize"] == 20
        # One owned row on this page drifted out of a readable shape: it is counted,
        # never silently replaced by scanning deeper history.
        assert first["unavailableCount"] == 1 and len(first["items"]) == 19
        second = await fetch_page(student, "/growth-tasks", page=2)
        assert second["unavailableCount"] == 0 and len(second["items"]) == 5
        seen = {row["id"] for row in first["items"]} | {row["id"] for row in second["items"]}
        assert seen == {healthy["id"], *seeded}
        assert broken_id not in seen


async def test_notification_page_size_aliases_and_conflict(jobs_db, tmp_path, monkeypatch):
    hr, student, other, job, rid, _resume, _raw, _factory = await setup(
        jobs_db, tmp_path, monkeypatch
    )
    try:
        created = await student.post(
            f"{API}/applications", json={"reportId": str(rid), "shareConsent": True}
        )
        assert created.status_code == 201, created.text
        aid = created.json()["data"]["id"]
        assert (await hr.post(f"{API}/applications/{aid}/view")).status_code == 200
        default_view = await fetch_page(student, "/notifications")
        assert default_view["pageSize"] == 20 and default_view["total"] == 2
        canonical = await fetch_page(student, "/notifications", pageSize=1, page=2)
        assert canonical["pageSize"] == 1 and len(canonical["items"]) == 1
        legacy = await fetch_page(student, "/notifications", page_size=1)
        assert legacy["pageSize"] == 1 and len(legacy["items"]) == 1
        assert (await fetch_page(student, "/notifications", pageSize=2, page_size=2))[
            "pageSize"
        ] == 2
        conflict = await student.get(f"{API}/notifications?pageSize=1&page_size=2")
        assert conflict.status_code == 422, conflict.text
        assert (await student.get(f"{API}/notifications?pageSize=51")).status_code == 422
        assert (await student.get(f"{API}/notifications?page_size=51")).status_code == 422
    finally:
        await close(hr, student, other)
