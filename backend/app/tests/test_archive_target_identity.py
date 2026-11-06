import os
import zipfile

import pytest

from app.core.exceptions import AppError
from app.tools.archive_scanner import (
    ArchiveLimits,
    SafeArchiveEntry,
    extract_selected_files,
    inspect_zip,
)

LIMITS = ArchiveLimits(100_000, 100_000, 10_000, 10)


def archive_at(tmp_path, names):
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for i, name in enumerate(names):
            handle.writestr(name, f"content-{i}")
    return archive


@pytest.mark.skipif(os.name != "nt", reason="Windows default extraction contract")
def test_windows_case_collision_refused_before_extraction(tmp_path):
    archive = archive_at(tmp_path, ["src/A.py", "src/a.py"])
    destination = tmp_path / "owned-output"
    with pytest.raises(AppError, match="冲突"):
        entries = inspect_zip(archive, LIMITS)
        extract_selected_files(archive, destination, entries)
    assert not destination.exists()
    assert archive.exists()


def test_normalized_duplicate_refused_in_inspection(tmp_path):
    archive = archive_at(tmp_path, ["src/./a.py", "src/a.py"])
    with pytest.raises(AppError, match="冲突"):
        inspect_zip(archive, LIMITS)


def test_extraction_rechecks_duplicates_before_any_write(tmp_path):
    archive = archive_at(tmp_path, ["src/./a.py", "src/a.py"])
    destination = tmp_path / "owned-output"
    with pytest.raises(AppError, match="冲突"):
        extract_selected_files(archive, destination, [SafeArchiveEntry("src/a.py", 9)])
    assert not destination.exists()


def test_different_directories_preserve_two_contents(tmp_path):
    archive = archive_at(tmp_path, ["dir1/a.py", "dir2/a.py"])
    destination = tmp_path / "owned-output"
    files = extract_selected_files(archive, destination, inspect_zip(archive, LIMITS))
    assert len(files) == 2
    assert (destination / "dir1/a.py").read_text() == "content-0"
    assert (destination / "dir2/a.py").read_text() == "content-1"


def test_explicit_case_sensitive_contract_is_not_globally_lowercased(tmp_path):
    archive = archive_at(tmp_path, ["src/A.py", "src/a.py"])
    assert len(inspect_zip(archive, LIMITS, case_sensitive=True)) == 2
    with pytest.raises(AppError, match="冲突"):
        inspect_zip(archive, LIMITS, case_sensitive=False)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("direct_extract", [False, True])
def test_file_directory_namespace_collision_rejected_before_any_write(
    tmp_path, reverse, direct_extract
):
    names = ["src/a.py", "src/a.py/child.py"]
    if reverse:
        names.reverse()
    archive = archive_at(tmp_path, names)
    destination = tmp_path / "owned-output"
    with pytest.raises(AppError, match="冲突"):
        if direct_extract:
            extract_selected_files(archive, destination, [SafeArchiveEntry(n, 9) for n in names])
        else:
            inspect_zip(archive, LIMITS)
    assert not destination.exists()
