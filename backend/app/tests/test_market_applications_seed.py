"""Isolation refusals happen before any HTTP request, subprocess or database connection."""

import pytest

from evals.seed_market_applications import CONTAINER, guard_runtime


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://user:secret@127.0.0.1:5432/careerproof",
    "postgresql+asyncpg://user:secret@127.0.0.1:55447/careerproof",
    "postgresql+asyncpg://user:secret@remote:55447/cp_home_discovery_test_20261027",
    "postgresql+asyncpg://user:secret@127.0.0.1:55447/cp_home_discovery_test_20261027?x=1",
])
def test_market_seed_refuses_other_targets(tmp_path, url):
    runtime = {"container": CONTAINER, "env": {
        "DATABASE_URL": url, "STORAGE_BASE_DIR": str(tmp_path / "backend/.tmp/storage"),
    }}
    with pytest.raises(ValueError, match="owned synthetic"):
        guard_runtime(runtime, tmp_path)


def test_market_seed_requires_own_storage_and_container(tmp_path):
    runtime = {"container": CONTAINER, "env": {
        "DATABASE_URL": "postgresql+asyncpg://user:secret@127.0.0.1:55447/cp_home_discovery_test_20261027",
        "STORAGE_BASE_DIR": str(tmp_path / "backend/.tmp/storage"),
    }}
    guard_runtime(runtime, tmp_path)
    runtime["env"]["STORAGE_BASE_DIR"] = str(tmp_path / "normal-storage")
    with pytest.raises(ValueError, match="storage"):
        guard_runtime(runtime, tmp_path)
    runtime["container"] = "normal-database"
    with pytest.raises(ValueError, match="owned synthetic"):
        guard_runtime(runtime, tmp_path)
