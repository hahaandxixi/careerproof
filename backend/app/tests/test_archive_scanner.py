import zipfile
from pathlib import Path

import pytest

from app.core.exceptions import AppError
from app.tools.archive_scanner import ArchiveLimits, inspect_zip


@pytest.fixture
def limits() -> ArchiveLimits:
    return ArchiveLimits(
        max_archive_bytes=1024 * 1024,
        max_extracted_bytes=2 * 1024 * 1024,
        max_file_bytes=1024 * 1024,
        max_files=10,
    )


def test_archive_skips_dependencies_and_binary_files(tmp_path: Path, limits: ArchiveLimits) -> None:
    archive_path = tmp_path / "project.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("src/main.py", "print('ok')")
        archive.writestr("node_modules/pkg/index.js", "ignored")
        archive.writestr("assets/logo.png", b"binary")

    entries = inspect_zip(archive_path, limits)

    assert [entry.relative_path for entry in entries] == ["src/main.py"]


def test_archive_rejects_path_traversal(tmp_path: Path, limits: ArchiveLimits) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.py", "print('unsafe')")

    with pytest.raises(AppError, match="不安全路径"):
        inspect_zip(archive_path, limits)
