from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_context import get_request_id


class AppError(Exception):
    def __init__(self, message: str, *, code: int = 4000, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def error_body(code: int, message: str, details: Any = None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if details is not None:
        data["details"] = details
    return {
        "code": code,
        "message": message,
        "data": data,
        "requestId": get_request_id(),
    }


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Invalid bodies can be bytes and validator contexts can contain exceptions.
        # Return only field diagnostics, never echo credentials or uploaded content.
        details = [
            {key: error[key] for key in ("loc", "msg", "type") if key in error}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(4220, "请求参数校验失败", details),
        )
