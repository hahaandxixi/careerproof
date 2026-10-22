"""Test sensitivity experiment: process-local mutation, never edits production."""

import pytest

from app.services import portfolio


async def no_owner_lock(session, owner):
    return None


portfolio.lock_material_owner = no_owner_lock
raise SystemExit(pytest.main([
    "app/tests/test_material_admission_postgres.py",
    "-k", "serializes_different_upload_targets",
    "-q", "-p", "no:cacheprovider",
    "--basetemp=.tmp/material-admission-mutation",
]))
