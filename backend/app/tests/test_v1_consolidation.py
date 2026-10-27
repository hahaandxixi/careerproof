"""Protection boundaries for the one-off data consolidation tool."""

from pathlib import Path

import pytest

from scripts.merge_v1_data import merge_files, skill_signature


def test_storage_merge_preserves_distinct_materials_and_is_retry_safe(tmp_path):
    sources = []
    for tag in ("first", "second"):
        root = tmp_path / tag
        (root / tag).mkdir(parents=True)
        (root / tag / "service.py").write_text(tag, encoding="utf-8")
        (root / "same.txt").write_text("identical", encoding="utf-8")
        sources.append({"storage": str(root)})
    target = tmp_path / "unified"
    first = merge_files(sources, target, True)
    assert first["files"] == 3
    assert (target / "first/service.py").read_text() == "first"
    assert (target / "second/service.py").read_text() == "second"
    assert merge_files(sources, target, True) == first


def test_conflicting_file_is_rejected_without_overwriting_target(tmp_path):
    first, second, target = (tmp_path / name for name in ("first", "second", "target"))
    for root, text in ((first, "original"), (second, "different"), (target, "retained")):
        root.mkdir()
        (root / "service.py").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="Conflicting storage content"):
        merge_files([{"storage": str(first)}, {"storage": str(second)}], target, True)
    assert (target / "service.py").read_text() == "retained"


def test_only_dictionary_identity_and_bookkeeping_may_differ():
    original = {"id": "one", "name": "Python", "category": "language", "created_at": "old"}
    duplicate = {**original, "id": "two", "created_at": "new"}
    assert skill_signature(original) == skill_signature(duplicate)
    assert skill_signature(original) != skill_signature({**duplicate, "category": "framework"})


def test_storage_target_cannot_be_inside_source(tmp_path: Path):
    with pytest.raises(ValueError, match="separate"):
        merge_files([{"storage": str(tmp_path)}], tmp_path / "child", True)
