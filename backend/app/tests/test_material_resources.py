"""Real upload transactions and owned parser directories, never normal storage."""

import json
import os
import subprocess
import time
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus
from app.models.identity import User
from app.models.portfolio import ProjectFile, ProjectVersion
from app.services import portfolio
from app.services.material_cleanup import attempt_paths, cleanup_attempt, recover_extractions
from app.tests import test_portfolio_api as shared_portfolio
from app.tests.test_portfolio_api import project_zip
from app.tools.storage import LocalStorage

app_database = shared_portfolio.app_database
student = shared_portfolio.student


async def upload(client, content=None):
    project = (await client.post("/api/v1/projects", json={"name": "quota fixture"})).json()
    return await client.post(
        f"/api/v1/projects/{project['data']['id']}/versions",
        files={"file": ("source.zip", content or project_zip(), "application/zip")},
    )


async def test_pending_admission_and_failed_reservation_release(student, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "material_pending_task_limit", 1)
    monkeypatch.setattr(
        "app.services.task_runner.FastAPIBackgroundTaskRunner.submit", lambda *args: None
    )
    first = await upload(student)
    assert first.status_code == 202
    task_id = UUID(first.json()["data"]["taskId"])
    second = await upload(student)
    assert second.status_code == 429
    async with portfolio.async_session_factory() as session:
        task = await session.get(AnalysisTask, task_id)
        task.status = TaskStatus.FAILED
        await session.commit()
    assert (await upload(student)).status_code == 202


async def test_storage_reserves_extraction_across_projects(student, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        "app.services.task_runner.FastAPIBackgroundTaskRunner.submit", lambda *args: None
    )
    monkeypatch.setattr(settings, "max_extracted_bytes", 1000)
    monkeypatch.setattr(settings, "material_storage_limit_bytes", 1600)
    first = await upload(student)
    assert first.status_code == 202
    second = await upload(student)
    assert second.status_code == 413
    async with portfolio.async_session_factory() as session:
        task = await session.get(AnalysisTask, UUID(first.json()["data"]["taskId"]))
        task.status = TaskStatus.FAILED
        await session.commit()
    assert (await upload(student)).status_code == 202


@pytest.mark.parametrize("failure", ["corrupt", "lost-lease", "index", "commit", "timeout"])
async def test_failed_attempt_removes_only_its_extraction(student, monkeypatch, failure):  # noqa: F811
    if failure == "lost-lease":
        monkeypatch.setattr(portfolio, "finish_task", _lost_lease)
    if failure == "index":

        async def fail_index(*args, **kwargs):
            raise RuntimeError("index/transaction rejected")

        monkeypatch.setattr(portfolio, "index_sources", fail_index)
    processes = []
    if failure == "timeout":
        from app.services.task_runner import run_isolated

        original_spawn = subprocess.Popen

        def capture(*args, **kwargs):
            process = original_spawn(*args, **kwargs)
            processes.append(process)
            return process

        async def bounded(function, *args, **kwargs):
            return await run_isolated(function, *args, timeout_seconds=0.5, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", capture)
        monkeypatch.setattr(portfolio, "process_project", _partial_then_wait)
        monkeypatch.setattr(portfolio, "run_isolated", bounded)
    if failure == "commit":
        from sqlalchemy.ext.asyncio import AsyncSession

        finish, commit = portfolio.finish_task, AsyncSession.commit
        commit_pending = set()

        async def arm_commit(session, *args, **kwargs):
            result = await finish(session, *args, **kwargs)
            if result and kwargs.get("status", TaskStatus.COMPLETED) == TaskStatus.COMPLETED:
                commit_pending.add(id(session))
            return result

        async def fail_once(session):
            if id(session) in commit_pending:
                commit_pending.remove(id(session))
                raise RuntimeError("commit rejected")
            return await commit(session)

        monkeypatch.setattr(portfolio, "finish_task", arm_commit)
        monkeypatch.setattr(AsyncSession, "commit", fail_once)
    response = await upload(student, b"not a zip" if failure == "corrupt" else None)
    assert response.status_code == 202
    version_id = UUID(response.json()["data"]["versionId"])
    root = settings.storage_base_dir / "projects" / "extracted" / str(version_id)
    assert not root.exists() or list(root.iterdir()) == []
    if failure == "timeout":
        assert processes and all(process.poll() is not None for process in processes)
    async with portfolio.async_session_factory() as session:
        version = await session.get(ProjectVersion, version_id)
        assert (
            LocalStorage(settings.storage_base_dir).resolve(version.archive_storage_key).is_file()
        )


async def _lost_lease(*args, **kwargs):
    return False


def _partial_then_wait(source, destination, *args, **kwargs):
    marker = destination.parent / f".{destination.name}.worker.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({**kwargs["run_context"], "pid": os.getpid()}))
    destination.mkdir(parents=True)
    (destination / "partial.txt").write_text("still writing")
    time.sleep(60)


@pytest.mark.parametrize("commit_applied", [False, True])
async def test_upload_commit_failure_preserves_only_committed_originals(
    student, monkeypatch, commit_applied
):  # noqa: F811
    project = (await student.post("/api/v1/projects", json={"name": "commit fixture"})).json()
    project_id = UUID(project["data"]["id"])
    async with portfolio.async_session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "alice@example.com"))
        commit = session.commit

        async def fail_commit():
            if commit_applied:
                await commit()
            raise RuntimeError("commit response lost")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="commit response lost"):
            await portfolio.PortfolioService(session).create_project_version(
                project_id=project_id,
                filename="source.zip",
                content=project_zip(),
                current_user=user,
            )
    async with portfolio.async_session_factory() as check:
        versions = list(
            await check.scalars(
                select(ProjectVersion).where(ProjectVersion.project_id == project_id)
            )
        )
        assert len(versions) == int(commit_applied)
        files = list((settings.storage_base_dir / "projects" / str(project_id)).rglob("*.zip"))
        assert len(files) == int(commit_applied)


async def test_orphan_recovery_protects_live_workers_and_saved_sources(student, monkeypatch):  # noqa: F811
    response = await upload(student)
    version_id = UUID(response.json()["data"]["versionId"])
    storage = LocalStorage(settings.storage_base_dir)
    async with portfolio.async_session_factory() as session:
        source = await session.scalar(
            select(ProjectFile).where(ProjectFile.project_version_id == version_id)
        )
        assert source and storage.resolve(source.storage_key).is_file()
        kept = storage.resolve(source.storage_key)
        token = UUID(source.storage_key.split("/")[3])
        assert (
            await cleanup_attempt(session, storage, version_id, token, worker_exited=True)
            == "referenced"
        )
        orphan = uuid4()
        directory, marker = attempt_paths(storage, version_id, orphan)
        directory.mkdir(parents=True)
        (directory / "partial.txt").write_text("partial")
        marker.write_text(
            json.dumps({"pid": os.getpid(), "versionId": str(version_id), "runToken": str(orphan)})
        )
        assert await cleanup_attempt(session, storage, version_id, orphan) == "worker-running"
        monkeypatch.setattr("app.services.material_cleanup.worker_running", lambda pid: False)
        result = await recover_extractions(session, storage, min_age_seconds=0)
        assert any(row["outcome"] == "eligible" for row in result)
        assert directory.exists() and kept.exists()
        await recover_extractions(session, storage, apply=True, min_age_seconds=0)
        assert not directory.exists() and kept.exists()
        # A worker can crash after its marker write, before making the directory.
        marker_only = uuid4()
        absent, marker = attempt_paths(storage, version_id, marker_only)
        marker.write_text(
            json.dumps({"pid": 1, "versionId": str(version_id), "runToken": str(marker_only)})
        )
        assert not absent.exists()
        plan = await recover_extractions(session, storage, min_age_seconds=0)
        assert any(
            row["runToken"] == str(marker_only) and row["outcome"] == "eligible" for row in plan
        )
        await recover_extractions(session, storage, apply=True, min_age_seconds=0)
        assert not marker.exists() and kept.exists()
