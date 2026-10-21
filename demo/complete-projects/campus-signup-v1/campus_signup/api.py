import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .service import RegistrationError, RegistrationService
from .storage import Store


class EventInput(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    capacity: int = Field(ge=1, le=1000)


class SignupInput(BaseModel):
    event_id: int = Field(ge=1)
    student_code: str = Field(min_length=3, max_length=32)


def create_app(database_path: Path):
    store = Store(database_path)
    store.initialize()
    service = RegistrationService(store)
    app = FastAPI(title="Campus Signup")

    @app.exception_handler(RegistrationError)
    async def registration_error(_request: Request, error: RegistrationError):
        return JSONResponse(status_code=error.status_code, content={"detail": str(error)})

    @app.exception_handler(sqlite3.DatabaseError)
    async def database_error(_request: Request, _error: sqlite3.DatabaseError):
        return JSONResponse(status_code=503, content={"detail": "Storage unavailable"})

    @app.post("/events", status_code=201)
    def create_event(payload: EventInput):
        return service.create_event(payload.title, payload.capacity)

    @app.get("/events")
    def list_events():
        return store.list_events()

    @app.post("/registrations", status_code=201)
    def register(payload: SignupInput):
        return service.register(payload.event_id, payload.student_code)

    @app.get("/registrations")
    def list_registrations():
        return store.list_registrations()

    @app.post("/registrations/{registration_id}/cancel")
    def cancel(registration_id: int):
        return service.cancel(registration_id)

    return app
