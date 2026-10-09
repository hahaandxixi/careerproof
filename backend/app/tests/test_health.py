from fastapi.testclient import TestClient

from app import main
from app.main import app


def test_health_returns_unified_response(monkeypatch) -> None:
    async def no_business_recovery():
        pass

    monkeypatch.setattr(main, "_recover_once", no_business_recovery)
    monkeypatch.setattr(main, "stop_dispatched_tasks", no_business_recovery)
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"
    assert body["requestId"]
    assert response.headers["X-Request-ID"] == body["requestId"]
