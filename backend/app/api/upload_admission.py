"""Authenticated, bounded multipart admission using python-multipart's public API.

Endpoints must not also declare File/Form parameters: FastAPI would parse those
before resolving authentication. The dependency below owns every temporary file
until the endpoint returns, including malformed input and BaseException cleanup.
"""
import asyncio
from collections.abc import Callable
from contextlib import ExitStack, asynccontextmanager
from tempfile import SpooledTemporaryFile
from typing import Literal
from uuid import UUID

from fastapi import Depends, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError, field_validator
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.datastructures import FormData, Headers
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.dependencies import get_current_user
from app.core.exceptions import AppError
from app.models.identity import User

SPOOL_BYTES = 1024 * 1024
MAX_FIELDS = 4
MAX_FIELD_BYTES = 8 * 1024
MAX_HEADER_BYTES = 8 * 1024
BODY_OVERHEAD_BYTES = 64 * 1024


class ResumeUploadForm(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    file: UploadFile


class ProjectUploadForm(BaseModel):
    file: UploadFile
    request_id: UUID | None = Field(default=None, alias="requestId")
    material_role: Literal["portfolio", "reference"] = Field(
        default="portfolio", alias="materialRole"
    )

    @field_validator("request_id", "material_role", mode="before")
    @classmethod
    def preserve_empty_form_defaults(cls, value, info):
        if value == "":
            return None if info.field_name == "request_id" else "portfolio"
        return value


def multipart_body(model: type[BaseModel]) -> dict:
    """Keep the browser/OpenAPI multipart contract despite manual admission."""
    return {
        "requestBody": {"required": True, "content": {
            "multipart/form-data": {"schema": model.model_json_schema(by_alias=True)}
        }},
        "responses": {"422": {"description": "Validation Error", "content": {
            "application/json": {"schema": {
                "$ref": "#/components/schemas/HTTPValidationError"
            }}
        }}},
    }


def _invalid() -> AppError:
    return AppError("上传表单格式无效或不完整", code=4030, status_code=400)


def _too_large() -> AppError:
    return AppError("上传正文或表单超过允许限制", code=4031, status_code=413)


async def _settled_io(operation):
    # A task cancellation must not close a spool while its thread-pool write is
    # still using it. Let that one bounded local operation settle, then propagate.
    task = asyncio.create_task(operation)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError()
    return result


class _MultipartReceiver:
    """Per-request callback state; no Starlette parser private-state mutation."""

    def __init__(self, file_limit: int):
        self.file_limit = file_limit
        self.handles = ExitStack()
        self.files: list[StarletteUploadFile] = []
        self.items: list[tuple[str, str | StarletteUploadFile]] = []
        self.writes: list[tuple[StarletteUploadFile, bytes]] = []
        self.finished: list[StarletteUploadFile] = []
        self.names: set[str] = set()
        self.fields = 0
        self.complete = False
        self.charset = "utf-8"

    def decode(self, data: bytes | bytearray) -> str:
        try:
            return data.decode(self.charset)
        except (UnicodeDecodeError, LookupError):
            # Match Starlette's existing form text/filename decoding contract.
            return data.decode("latin-1")

    def on_part_begin(self):
        self.header_name = b""
        self.header_value = b""
        self.header_bytes = 0
        self.headers: list[tuple[bytes, bytes]] = []
        self.name = ""
        self.file: StarletteUploadFile | None = None
        self.data = bytearray()
        self.size = 0

    def on_header_field(self, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > MAX_HEADER_BYTES:
            raise _too_large()
        self.header_name += data[start:end]

    def on_header_value(self, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > MAX_HEADER_BYTES:
            raise _too_large()
        self.header_value += data[start:end]

    def on_header_end(self):
        self.headers.append((self.header_name.lower(), self.header_value))
        self.header_name = self.header_value = b""

    def on_headers_finished(self):
        headers = Headers(raw=self.headers)
        kind, options = parse_options_header(headers.get("content-disposition", ""))
        if kind != b"form-data" or b"name" not in options:
            raise _invalid()
        self.name = self.decode(options[b"name"])
        if self.name in self.names:
            raise _invalid()
        self.names.add(self.name)
        if b"filename" in options:
            if self.files:
                raise _too_large()
            handle = self.handles.enter_context(
                SpooledTemporaryFile(max_size=SPOOL_BYTES, mode="w+b")  # noqa: SIM115
            )
            self.file = StarletteUploadFile(
                handle, size=0,
                filename=self.decode(options[b"filename"]),
                headers=headers,
            )
            self.files.append(self.file)
        else:
            self.fields += 1
            if self.fields > MAX_FIELDS:
                raise _too_large()

    def on_part_data(self, data, start, end):
        self.size += end - start
        if self.size > (self.file_limit if self.file else MAX_FIELD_BYTES):
            raise _too_large()
        if self.file:
            self.writes.append((self.file, data[start:end]))
        else:
            self.data.extend(data[start:end])

    def on_part_end(self):
        if self.file:
            self.finished.append(self.file)
            self.items.append((self.name, self.file))
        else:
            self.items.append((self.name, self.decode(self.data)))

    def on_end(self):
        self.complete = True

    async def flush(self):
        for file, data in self.writes:
            await _settled_io(file.write(data))
        for file in self.finished:
            await _settled_io(file.seek(0))
        self.writes.clear()
        self.finished.clear()

    def close(self):
        # No await here: cancellation must not interrupt deterministic closure.
        # Handles are local spools, never user-provided streams or business files.
        self.handles.close()


@asynccontextmanager
async def receive_upload(request: Request, file_limit: int):
    receiver = _MultipartReceiver(file_limit)
    try:
        total_limit = file_limit + BODY_OVERHEAD_BYTES
        length = request.headers.get("content-length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError as exc:
                raise _invalid() from exc
            if declared < 0:
                raise _invalid()
            if declared > total_limit:
                raise _too_large()
        kind, options = parse_options_header(request.headers.get("content-type", ""))
        boundary = options.get(b"boundary")
        if kind != b"multipart/form-data" or not boundary or len(boundary) > 200:
            raise _invalid()
        receiver.charset = options.get(b"charset", b"utf-8").decode("latin-1")
        parser = MultipartParser(boundary, {
            name: getattr(receiver, name) for name in (
                "on_part_begin", "on_header_field", "on_header_value", "on_header_end",
                "on_headers_finished", "on_part_data", "on_part_end", "on_end",
            )
        })
        total = 0
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > total_limit:
                    raise _too_large()
                parser.write(chunk)
                await receiver.flush()
            parser.finalize()
        except (MultipartParseError, ValueError) as exc:
            # Parser diagnostics may contain body bytes; expose only our message.
            raise _invalid() from exc
        if not receiver.complete:
            raise _invalid()
        yield FormData(receiver.items)
    finally:
        receiver.close()


def authenticated_upload(model: type[BaseModel], file_limit: Callable[[], int]):
    async def dependency(request: Request, _current_user: User = Depends(get_current_user)):
        async with receive_upload(request, file_limit()) as form:
            try:
                payload = model.model_validate(dict(form))
            except ValidationError as exc:
                errors = [{**error, "loc": ("body", *error["loc"])} for error in exc.errors()]
                raise RequestValidationError(errors) from exc
            yield payload
    return dependency
