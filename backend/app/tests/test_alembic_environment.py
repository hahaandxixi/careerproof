"""Execute the real Alembic env while trapping engine creation before any I/O."""

import runpy
from pathlib import Path

import pytest
from sqlalchemy.ext import asyncio as sa_async

from alembic import context
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[2]


def prepare(monkeypatch, options):
    monkeypatch.setattr(context, "config", Config(str(BACKEND / "alembic.ini")), raising=False)
    monkeypatch.setattr(context, "get_x_argument", lambda: options)
    monkeypatch.setattr(context, "is_offline_mode", lambda: False)


@pytest.mark.parametrize("option", [
    "dburl=sqlite+aiosqlite:///never-open.db",
    "database_url=postgresql://should-not-be-logged@127.0.0.1/never-open",
])
def test_unsupported_x_option_rejected_before_engine_creation(monkeypatch, option):
    prepare(monkeypatch, [option])
    engine_calls = []

    def forbidden_engine(*args, **kwargs):
        engine_calls.append(True)
        pytest.fail("Alembic tried to create an engine despite an unsupported selector")

    monkeypatch.setattr(sa_async, "async_engine_from_config", forbidden_engine)
    with pytest.raises(ValueError, match="Unsupported Alembic -x") as error:
        runpy.run_path(str(BACKEND / "alembic/env.py"))
    assert not engine_calls
    assert "should-not-be-logged" not in str(error.value)


def test_no_x_option_still_reaches_existing_engine_boundary(monkeypatch):
    prepare(monkeypatch, [])

    def observed_engine(*args, **kwargs):
        raise RuntimeError("expected-engine-boundary-no-connection")

    monkeypatch.setattr(sa_async, "async_engine_from_config", observed_engine)
    with pytest.raises(RuntimeError, match="expected-engine-boundary-no-connection"):
        runpy.run_path(str(BACKEND / "alembic/env.py"))
