"""Synthetic receive-boundary regressions. No network listener or business data."""
import asyncio
import tempfile
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import ClientDisconnect

from app.api import upload_admission
from app.api.dependencies import get_current_user
from app.api.v1 import portfolio
from app.core.database import get_session
from app.core.exceptions import AppError, install_exception_handlers
from app.core.security import create_token
from app.repositories.users import UserRepository
from app.schemas.portfolio import ProjectVersionUploadData, ResumeUploadData


def multipart(parts, boundary="owned-upload-test"):
    body = b""
    for name, filename, value in parts:
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        body += f"--{boundary}\r\nContent-Disposition: {disposition}\r\n\r\n".encode()
        body += value + b"\r\n"
    return body + f"--{boundary}--\r\n".encode(), {
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }


def synthetic_app(auth):
    app = FastAPI()
    app.include_router(portfolio.router)
    install_exception_handlers(app)
    app.dependency_overrides[get_current_user] = auth

    async def no_database():
        yield None

    app.dependency_overrides[get_session] = no_database
    return app


@pytest.mark.parametrize("path", ["/resumes", f"/projects/{uuid4()}/versions"])
async def test_authentication_rejects_before_receiving_any_body(path):
    consumed = 0

    async def deny():
        raise AppError("请先登录", code=4015, status_code=401)

    body, headers = multipart([("file", "a.txt", b"x" * 512)])

    async def chunks():
        nonlocal consumed
        for offset in range(0, len(body), 32):
            chunk = body[offset:offset + 32]
            consumed += len(chunk)
            yield chunk

    async with AsyncClient(transport=ASGITransport(app=synthetic_app(deny)),
                           base_url="http://synthetic") as client:
        response = await client.post(path, content=chunks(), headers=headers)
    assert response.status_code == 401
    assert consumed == 0


@pytest.fixture
def admitted(tmp_path, monkeypatch):
    calls, jobs, spools = [], [], []
    temp_directory = tmp_path / "spools"
    temp_directory.mkdir()
    original = tempfile.SpooledTemporaryFile

    def spool(*args, **kwargs):
        handle = original(*args, **kwargs, dir=temp_directory)
        spools.append(handle)
        return handle

    monkeypatch.setattr(upload_admission, "SpooledTemporaryFile", spool)
    monkeypatch.setattr(upload_admission, "SPOOL_BYTES", 16)
    monkeypatch.setattr(portfolio, "RESUME_MAX_BYTES", 64)
    monkeypatch.setattr(portfolio.settings, "max_archive_bytes", 64)
    user = SimpleNamespace(id=uuid4(), role="student", is_active=True)

    async def allow():
        return user

    class Service:
        def __init__(self, _session):
            pass

        async def create_resume_upload(self, **kwargs):
            calls.append(kwargs)
            return ResumeUploadData(resume_id=uuid4(), version_id=uuid4(),
                                    task_id=uuid4(), status="pending")

        async def create_project_version(self, **kwargs):
            calls.append(kwargs)
            return ProjectVersionUploadData(project_id=kwargs["project_id"],
                                            version_id=uuid4(), task_id=uuid4(),
                                            status="pending"), True

    monkeypatch.setattr(portfolio, "PortfolioService", Service)
    monkeypatch.setattr(portfolio.FastAPIBackgroundTaskRunner, "submit",
                        lambda *args: jobs.append(args))
    app = synthetic_app(allow)
    yield SimpleNamespace(app=app, calls=calls, jobs=jobs, spools=spools, user=user,
                          service=Service, directory=temp_directory)
    assert all(handle.closed for handle in spools)
    assert list(temp_directory.iterdir()) == []


async def send(case, parts, *, path="/resumes", declared=None, truncate=False):
    body, headers = multipart(parts)
    if truncate:
        body = body[:-25]
    if declared is not None:
        headers["Content-Length"] = str(declared)
    consumed = 0

    async def chunks():
        nonlocal consumed
        for offset in range(0, len(body), 32):
            chunk = body[offset:offset + 32]
            consumed += len(chunk)
            yield chunk

    async with AsyncClient(transport=ASGITransport(app=case.app),
                           base_url="http://synthetic") as client:
        response = await client.post(path, content=chunks(), headers=headers)
    return response, consumed, len(body)


async def test_legal_file_boundary_and_chinese_fields_close_spool(admitted):
    response, consumed, total = await send(admitted, [
        ("title", None, "校招简历".encode()), ("file", "简历.txt", b"x" * 64),
    ])
    assert response.status_code == 202, response.text
    assert consumed == total
    assert admitted.calls[0]["content"] == b"x" * 64
    assert admitted.calls[0]["title"] == "校招简历"
    assert admitted.calls[0]["filename"] == "简历.txt"
    assert admitted.calls[0]["current_user"] is admitted.user
    assert len(admitted.jobs) == 1
    assert admitted.spools[0]._rolled and admitted.spools[0].closed


async def test_existing_declared_form_charset_is_preserved(admitted):
    body, headers = multipart([("title", None, b"caf\xe9"), ("file", "a.txt", b"x")])
    headers["Content-Type"] += "; charset=latin-1"
    async with AsyncClient(transport=ASGITransport(app=admitted.app),
                           base_url="http://synthetic") as client:
        response = await client.post("/resumes", content=body, headers=headers)
    assert response.status_code == 202, response.text
    assert admitted.calls[0]["title"] == "café"


@pytest.mark.parametrize("empty_defaults", [False, True])
async def test_project_aliases_and_optional_empty_defaults(admitted, empty_defaults):
    project_id, request_id = uuid4(), uuid4()
    response, _, _ = await send(admitted, [
        ("file", "source.zip", b"synthetic"),
        ("requestId", None, b"" if empty_defaults else str(request_id).encode()),
        ("materialRole", None, b"" if empty_defaults else b"reference"),
    ], path=f"/projects/{project_id}/versions")
    assert response.status_code == 202, response.text
    assert admitted.calls[0]["project_id"] == project_id
    assert admitted.calls[0]["request_id"] == (None if empty_defaults else request_id)
    assert admitted.calls[0]["material_role"] == ("portfolio" if empty_defaults else "reference")


@pytest.mark.parametrize("declared", [None, 0])
async def test_cumulative_body_limit_without_trusting_content_length(
    admitted, monkeypatch, declared
):
    monkeypatch.setattr(upload_admission, "BODY_OVERHEAD_BYTES", 256)
    response, consumed, total = await send(admitted, [
        ("file", "a.txt", b"x" * 32), ("title", None, b"x" * 1024),
    ], declared=declared)
    assert response.status_code == 413, response.text
    assert 320 < consumed <= 352 and consumed < total
    assert admitted.spools and all(f.closed for f in admitted.spools)
    assert not admitted.calls and not admitted.jobs


async def test_declared_oversize_rejects_before_body_or_spool(admitted):
    response, consumed, _ = await send(admitted, [("file", "a.txt", b"x")], declared=10**9)
    assert response.status_code == 413
    assert consumed == 0 and not admitted.spools and not admitted.calls


@pytest.mark.parametrize("parts, expected", [
    ([("title", None, b"title"), ("file", "a.txt", b"x" * 65)], 413),
    ([("file", "a.txt", b"x" * 32), ("other", "b.txt", b"y")], 413),
    ([("file", "a.txt", b"x" * 32)] + [(str(i), None, b"a") for i in range(5)], 413),
    ([("file", "a.txt", b"x" * 32), ("title", None, b"x" * 8193)], 413),
    ([("file", "a.txt", b"x" * 32), ("title", None, b"a"), ("title", None, b"b")], 400),
    ([("file", "a.txt", b"x" * 32), ("title", None, b"x" * 201)], 422),
    ([("title", None, b"title")], 422),
])
async def test_part_limits_or_validation_reject_before_business(admitted, parts, expected):
    response, _, _ = await send(admitted, parts)
    assert response.status_code == expected, response.text
    assert not admitted.calls and not admitted.jobs


async def test_truncated_form_closes_already_rolled_spool(admitted):
    response, _, _ = await send(admitted, [("file", "a.txt", b"x" * 32)], truncate=True)
    assert response.status_code == 400, response.text
    assert admitted.spools[0]._rolled and admitted.spools[0].closed
    assert not admitted.calls and not admitted.jobs


async def test_business_rejection_closes_spool_and_preserves_error(admitted, monkeypatch):
    async def reject(_self, **kwargs):
        raise AppError("synthetic forbidden", code=4019, status_code=403)

    monkeypatch.setattr(admitted.service, "create_resume_upload", reject)
    response, _, _ = await send(admitted, [
        ("file", "a.txt", b"x" * 32), ("title", None, b"title"),
    ])
    assert response.status_code == 403
    assert admitted.spools[0].closed and not admitted.jobs


async def test_cancellation_waits_for_inflight_spool_write_before_close(admitted, monkeypatch):
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    factory = upload_admission.SpooledTemporaryFile
    completed = []

    def spool(*args, **kwargs):
        handle = factory(*args, **kwargs)
        original = handle.write

        def held_write(data):
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(3), "test barrier was not released"
            assert not handle.closed
            result = original(data)
            completed.append(True)
            return result

        handle.write = held_write
        return handle

    monkeypatch.setattr(upload_admission, "SpooledTemporaryFile", spool)
    body, headers = multipart([("file", "a.txt", b"x" * 32)])

    async def request():
        async with AsyncClient(transport=ASGITransport(app=admitted.app),
                               base_url="http://synthetic") as client:
            return await client.post("/resumes", content=body, headers=headers)

    task = asyncio.create_task(request())
    try:
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        await asyncio.sleep(0)  # deliver cancellation while the write barrier is held
        assert not admitted.spools[0].closed
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert completed and admitted.spools[0].closed
    assert not admitted.calls and not admitted.jobs


@pytest.mark.parametrize("abort", ["cancel", "disconnect", "io_error"])
async def test_interrupted_receive_closes_rolled_file_before_propagating(admitted, abort):
    boundary = "abort-owned-upload"
    first = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
             'filename="a.txt"\r\n\r\n').encode() + b"x" * 32
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": first, "more_body": True}
        assert admitted.spools[0]._rolled and not admitted.spools[0].closed
        if abort == "cancel":
            raise asyncio.CancelledError()
        if abort == "io_error":
            raise OSError("synthetic receive failure")
        return {"type": "http.disconnect"}

    async def discard(_message):
        pass

    scope = {"type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/resumes", "raw_path": b"/resumes", "query_string": b"",
             "headers": [(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
             "client": ("synthetic", 1234), "server": ("synthetic", 80)}
    exception = {"cancel": asyncio.CancelledError, "disconnect": ClientDisconnect,
                 "io_error": OSError}[abort]
    with pytest.raises(exception):
        await admitted.app(scope, receive, discard)
    assert admitted.spools[0].closed
    assert not admitted.calls and not admitted.jobs


@pytest.mark.parametrize("credentials", ["missing", "invalid", "disabled"])
async def test_real_auth_rejection_still_reads_zero_body(admitted, monkeypatch, credentials):
    admitted.app.dependency_overrides.pop(get_current_user)
    body, headers = multipart([("file", "a.txt", b"x" * 32)])
    if credentials == "invalid":
        headers["Authorization"] = "Bearer synthetic-invalid-token"
    elif credentials == "disabled":
        token, _, _ = create_token(uuid4(), "student", "access")
        headers["Cookie"] = f"careerproof_access={token}"

        async def disabled(_self, _user_id):
            return SimpleNamespace(is_active=False)

        monkeypatch.setattr(UserRepository, "get", disabled)
    consumed = 0

    async def chunks():
        nonlocal consumed
        consumed += len(body)
        yield body

    async with AsyncClient(transport=ASGITransport(app=admitted.app),
                           base_url="http://synthetic") as client:
        response = await client.post("/resumes", content=chunks(), headers=headers)
    assert response.status_code == 401, response.text
    assert consumed == 0 and not admitted.spools and not admitted.calls


def test_openapi_upload_contract_keeps_aliases_binary_required_fields_and_auth():
    app = synthetic_app(lambda: None)
    schema = app.openapi()
    for path, required in [("/resumes", ["title", "file"]),
                           ("/projects/{project_id}/versions", ["file"])]:
        operation = schema["paths"][path]["post"]
        body = operation["requestBody"]
        assert body["required"]
        form = body["content"]["multipart/form-data"]["schema"]
        assert form["required"] == required
        # FastAPI 0.143's prior File schema uses OpenAPI 3.1 contentMediaType.
        assert form["properties"]["file"]["contentMediaType"] == "application/octet-stream"
        assert operation["security"] == [{"HTTPBearer": []}]
        assert "422" in operation["responses"]
        assert "HTTPValidationError" in schema["components"]["schemas"]
    fields = schema["paths"]["/projects/{project_id}/versions"]["post"]["requestBody"][
        "content"]["multipart/form-data"]["schema"]["properties"]
    assert fields["materialRole"]["enum"] == ["portfolio", "reference"]
    assert fields["materialRole"]["default"] == "portfolio"
    assert "requestId" in fields and "request_id" not in fields
