"""Framework compatibility through application middleware, without business DB access."""

import httpx
from fastapi.testclient import TestClient
from sse_starlette.sse import EventSourceResponse

from app import main
from app.core.config import settings
from app.core.exceptions import AppError


def test_lifespan_starts_recovery_and_stops_owned_dispatcher(monkeypatch):
    calls = []

    async def recover():
        calls.append("recover")

    async def stop():
        calls.append("stop")

    monkeypatch.setattr(main, "_recover_once", recover)
    monkeypatch.setattr(main, "stop_dispatched_tasks", stop)
    with TestClient(main.create_app()) as client:
        assert calls == ["recover"]
        response = client.get("/api/v1/health", headers={"X-Request-ID": "synthetic-id"})
        assert response.status_code == 200
        assert response.json()["requestId"] == "synthetic-id"
        assert response.headers["x-request-id"] == "synthetic-id"
    assert calls == ["recover", "stop"]


async def test_cors_validation_and_safe_exception_contract():
    app = main.create_app()

    @app.get("/__framework_contract/error", include_in_schema=False)
    async def fail():
        raise AppError("synthetic denial", code=4030, status_code=403)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://synthetic.test"
    ) as client:
        origin = settings.frontend_origins[0]
        preflight = await client.options(
            "/api/v1/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin
        rejected = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://untrusted.invalid", "Access-Control-Request-Method": "GET"
            },
        )
        assert rejected.status_code == 400
        assert "access-control-allow-origin" not in rejected.headers
        invalid = await client.post(
            "/api/v1/auth/login", content=b'{"password":"synthetic-private',
            headers={"Content-Type": "application/json", "X-Request-ID": "invalid-body"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == 4220
        assert invalid.json()["requestId"] == "invalid-body"
        assert "synthetic-private" not in invalid.text
        denied = await client.get(
            "/__framework_contract/error", headers={"X-Request-ID": "denial-id"}
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == 4030
        assert denied.headers["x-request-id"] == denied.json()["requestId"] == "denial-id"


async def test_sse_starlette_stream_survives_application_middleware():
    app = main.create_app()

    @app.get("/__framework_contract/events", include_in_schema=False)
    async def events():
        async def synthetic_events():
            yield {"event": "progress", "data": "synthetic progress"}
            yield {"event": "complete", "data": "synthetic complete"}

        return EventSourceResponse(synthetic_events())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://synthetic.test"
    ) as client:
        response = await client.get(
            "/__framework_contract/events", headers={"X-Request-ID": "stream-id"}
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-request-id"] == "stream-id"
    assert "event: progress" in response.text and "event: complete" in response.text
    assert response.text.index("synthetic progress") < response.text.index("synthetic complete")
