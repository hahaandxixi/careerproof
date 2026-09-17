from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_unified_response() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"
    assert body["requestId"]
    assert response.headers["X-Request-ID"] == body["requestId"]
