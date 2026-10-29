"""Project removal uses the existing archive API; all data is temporary."""
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.models.portfolio import ProjectFile, ProjectVersion
from app.tests.test_jobs_api import register
from app.tests.test_real_matching import (
    create_job,
    match_report,
    source_archive,
    upload_materials,
)

pytest_plugins = ["app.tests.test_real_matching"]


async def test_project_removal_hides_all_versions_but_preserves_authorized_history(matching_db):
    app, factory = matching_db
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as hr,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as student,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other,
    ):
        await register(hr, "hr@example.com")
        await register(student, "owner@example.com", "student")
        await register(other, "other@example.com", "student")
        job = await create_job(hr)
        resume, project, first = await upload_materials(student)
        report = await match_report(student, job, resume, first)
        rid = report["id"]
        created = await student.post(
            "/api/v1/applications", json={"reportId": rid, "shareConsent": True}
        )
        assert created.status_code == 201, created.text
        aid = created.json()["data"]["id"]
        before_snapshot = (await hr.get(f"/api/v1/applications/{aid}")).json()["data"]
        second = await student.post(
            f"/api/v1/projects/{project['id']}/versions",
            data={"requestId": str(uuid4())},
            files={"file": ("second.zip", source_archive(extra="# version two\n"),
                            "application/zip")},
        )
        assert second.status_code == 202, second.text
        version_ids = [first["versionId"], second.json()["data"]["versionId"]]
        previews = {}
        for vid in version_ids:
            files = await student.get(f"/api/v1/project-versions/{vid}/files")
            assert files.status_code == 200, files.text
            assert files.json()["data"]
            for file in files.json()["data"]:
                response = await student.get(f"/api/v1/project-files/{file['id']}")
                assert response.status_code == 200
                previews[file["id"]] = response.json()["data"]
        async with factory() as session:
            versions = list(await session.scalars(select(ProjectVersion).where(
                ProjectVersion.project_id == UUID(project["id"])
            )))
            files = list(await session.scalars(select(ProjectFile).where(
                ProjectFile.project_version_id.in_([UUID(v) for v in version_ids])
            )))
            keys = [v.archive_storage_key for v in versions] + [f.storage_key for f in files]
            stored = {key: (settings.storage_base_dir / key).read_bytes() for key in keys}

        path = f"/api/v1/materials/project/{project['id']}/archive"
        assert (await other.patch(path, json={"archived": True})).status_code == 404
        assert len((await student.get("/api/v1/projects")).json()["data"]) == 1
        assert (await hr.patch(path, json={"archived": True})).status_code == 403
        for _ in range(2):
            response = await student.patch(path, json={"archived": True})
            assert response.status_code == 200, response.text
        assert (await student.get("/api/v1/projects")).json()["data"] == []
        archived = (await student.get("/api/v1/projects?includeArchived=true")).json()["data"]
        assert len(archived) == 1 and archived[0]["isArchived"]
        assert {v["id"] for v in archived[0]["versions"]} == set(version_ids)
        old_report = await student.get(f"/api/v1/match-reports/{rid}")
        assert old_report.status_code == 200
        assert old_report.json()["data"] == report
        snapshot = await hr.get(f"/api/v1/applications/{aid}")
        assert snapshot.status_code == 200
        assert snapshot.json()["data"] == before_snapshot
        for fid, preview in previews.items():
            response = await student.get(f"/api/v1/project-files/{fid}")
            assert response.status_code == 200
            assert response.json()["data"] == preview
            assert (await other.get(f"/api/v1/project-files/{fid}")).status_code == 404
        for key, raw in stored.items():
            assert (settings.storage_base_dir / key).read_bytes() == raw
        assert (await student.get("/api/v1/users/me")).status_code == 200
        assert (await student.patch(path, json={"archived": False})).status_code == 200
        restored = (await student.get("/api/v1/projects")).json()["data"]
        assert len(restored) == 1 and len(restored[0]["versions"]) == 2
