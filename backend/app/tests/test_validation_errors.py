import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, field_validator

from app.core.exceptions import AppError, install_exception_handlers


class Input(BaseModel):
    note: str

    @field_validator("note")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("note must not be blank")
        return value


@pytest.mark.parametrize(
    "status,code", [(401, 4015), (403, 4037), (404, 4049), (409, 4098), (422, 4224)]
)
async def test_structured_app_error_preserves_reply_rejection_contract(status, code):
    app = FastAPI()
    install_exception_handlers(app)

    @app.post("/guarded-write")
    async def reject():
        raise AppError("合成契约拒绝", status_code=status, code=code)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/guarded-write")
        assert response.status_code == status
        assert response.json()["code"] == code
        assert response.json()["message"] == "合成契约拒绝"


async def test_invalid_body_keeps_422_without_echoing_private_input():
    app = FastAPI()
    install_exception_handlers(app)

    @app.post("/review")
    async def review(body: Input):
        return body

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/review", content=b'{"note":"synthetic-private-token"}',
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 422
        assert "synthetic-private-token" not in response.text
        assert response.json()["data"]["details"][0]["loc"] == ["body"]
        invalid = await client.post("/review", json={"note": " "})
        assert invalid.status_code == 422
        detail = invalid.json()["data"]["details"][0]
        assert detail["loc"] == ["body", "note"]
        assert set(detail) == {"loc", "msg", "type"}
