"""Refuse an outdated interpreter before E2E database creation or service startup."""

import importlib.metadata

import pytest

from evals.verify_dependency_environment import verify_environment


def test_pins_include_extras_without_changing_distribution_name(tmp_path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        '[project]\ndependencies = ["fastapi==0.143.0", "uvicorn[standard]==0.35.0"]\n'
    )
    installed = {"fastapi": "0.143.0", "uvicorn": "0.35.0"}
    assert verify_environment(manifest, installed.__getitem__) == installed


def test_old_framework_interpreter_is_rejected(tmp_path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\ndependencies = ["fastapi==0.143.0"]\n')
    with pytest.raises(ValueError, match="requires 0.143.0"):
        verify_environment(manifest, lambda _: "0.116.1")


def test_missing_package_is_rejected(tmp_path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\ndependencies = ["fastapi==0.143.0"]\n')

    def missing(_name):
        raise importlib.metadata.PackageNotFoundError("fastapi")

    with pytest.raises(ValueError, match="missing fastapi"):
        verify_environment(manifest, missing)


def test_unpinned_requirement_cannot_claim_reproducible_upgrade(tmp_path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\ndependencies = ["fastapi>=0.143.0"]\n')
    with pytest.raises(ValueError, match="exact production dependency pin"):
        verify_environment(manifest, lambda _: "0.143.0")
