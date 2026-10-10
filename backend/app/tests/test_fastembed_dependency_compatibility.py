"""Dependency-metadata and real-embedding compatibility gates for the fastembed pin.

Two separate concerns, deliberately kept apart:

- The metadata tests read the actually installed distributions. They fail on the
  historical breakage where fastembed 0.7.4 declared ``pillow<12.0`` while the
  project pinned Pillow 12.x. They never mock anything.
- The embedding smoke uses the production ``load_local_model`` entry point with
  the real CPU ONNX weights. When the configured weights are not installed the
  test skips loudly instead of substituting a fake embedder: a skip is a skip,
  never a compatibility pass. The 6x384 cross-version evidence lives in
  docs/evidence/20261010-DEP-fastembed-compatibility/, produced by
  evals/probe_fastembed_compatibility.py.
"""

from __future__ import annotations

import importlib.metadata
import math
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from app.core.config import settings
from app.tools.semantic_retrieval import model_available

PINNED_PACKAGES = ("fastembed", "pillow", "pyjwt", "python-multipart")


def _project_pins() -> dict[str, str]:
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    )
    pins: dict[str, str] = {}
    for item in pyproject["project"]["dependencies"]:
        requirement = Requirement(item)
        if requirement.name.lower() in PINNED_PACKAGES:
            assert len(requirement.specifier) == 1, item
            pins[requirement.name.lower()] = next(iter(requirement.specifier)).version
    return pins


def test_installed_pins_match_pyproject_exactly():
    pins = _project_pins()
    assert set(pins) == set(PINNED_PACKAGES)
    for name, pinned in pins.items():
        installed = importlib.metadata.version(name)
        assert installed == pinned, f"{name}: installed {installed} != pin {pinned}"


def test_fastembed_declared_requirements_accept_installed_environment():
    """The in-process equivalent of the pip check clause that used to fail."""
    for raw in importlib.metadata.requires("fastembed") or []:
        requirement = Requirement(raw)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        installed = importlib.metadata.version(requirement.name)
        assert requirement.specifier.contains(installed, prereleases=True), (
            f"fastembed requires {raw}, installed {requirement.name}=={installed}"
        )


def test_real_local_onnx_embedding_smoke():
    if not model_available(settings.semantic_model_cache_dir):
        pytest.skip("local semantic weights not installed; see probe evidence instead")

    from app.tools.semantic_retrieval import load_local_model

    model = load_local_model(settings.semantic_model_cache_dir)
    vectors = [
        [float(value) for value in vector]
        for vector in model.embed(["数据库事务回滚。", "Image upload validation."])
    ]
    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == 384
        assert all(math.isfinite(value) for value in vector)
        assert math.sqrt(sum(value * value for value in vector)) > 0
