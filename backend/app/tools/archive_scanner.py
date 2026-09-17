from __future__ import annotations

import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.exceptions import AppError

IGNORED_PARTS = {".git", "node_modules", "dist", "build", ".next", "target"}
ALLOWED_SUFFIXES = {
    ".py",
    ".java",
    ".go",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".sql",
    ".json",
    ".xml",
    ".yml",
    ".yaml",
    ".toml",
    ".md",
    ".txt",
    ".sh",
    ".properties",
}
ALLOWED_NAMES = {"Dockerfile", ".gitignore"}


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_archive_bytes: int
    max_extracted_bytes: int
    max_file_bytes: int
    max_files: int


@dataclass(frozen=True, slots=True)
class SafeArchiveEntry:
    relative_path: str
    size_bytes: int


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = info.external_attr >> 16
    return stat.S_ISLNK(unix_mode)


def _safe_relative_path(filename: str) -> PurePosixPath:
    path = PurePosixPath(filename.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise AppError("压缩包包含不安全路径", code=4008, status_code=400)
    return path


def inspect_zip(archive_path: Path, limits: ArchiveLimits) -> list[SafeArchiveEntry]:
    if archive_path.stat().st_size > limits.max_archive_bytes:
        raise AppError("压缩包超过30MB限制", code=4009, status_code=413)
    accepted: list[SafeArchiveEntry] = []
    extracted_bytes = 0
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            path = _safe_relative_path(info.filename)
            if _is_symlink(info):
                raise AppError("压缩包不得包含符号链接", code=4012, status_code=400)
            extracted_bytes += info.file_size
            if extracted_bytes > limits.max_extracted_bytes:
                raise AppError("解压后内容超过100MB限制", code=4013, status_code=413)
            if any(part in IGNORED_PARTS for part in path.parts):
                continue
            if info.file_size > limits.max_file_bytes:
                continue
            if path.suffix.lower() not in ALLOWED_SUFFIXES and path.name not in ALLOWED_NAMES:
                continue
            accepted.append(SafeArchiveEntry(str(path), info.file_size))
            if len(accepted) > limits.max_files:
                raise AppError("可分析文件数量超过限制", code=4014, status_code=413)
    return accepted


def extract_selected_files(
    archive_path: Path,
    destination: Path,
    entries: list[SafeArchiveEntry],
) -> list[Path]:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    allowed = {entry.relative_path for entry in entries}
    extracted: list[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            normalized = str(_safe_relative_path(info.filename))
            if normalized not in allowed:
                continue
            output = (destination / Path(*PurePosixPath(normalized).parts)).resolve()
            if destination not in output.parents:
                raise AppError("文件解压目标越界", code=4015, status_code=400)
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, output.open("wb") as target:
                while chunk := source.read(64 * 1024):
                    target.write(chunk)
            extracted.append(output)
    return extracted
