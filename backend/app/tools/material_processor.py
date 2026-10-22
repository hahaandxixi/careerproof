"""Blocking material processing, invoked exclusively in an isolated worker."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from app.core.exceptions import AppError
from app.tools.archive_scanner import ArchiveLimits, extract_selected_files, inspect_zip
from app.tools.document_parser import DocumentSection, language_for, parse_document


def process_document(path: Path, mime_type: str, max_characters: int) -> list[DocumentSection]:
    sections = parse_document(path, mime_type)
    if sum(len(section.content) for section in sections) > max_characters:
        raise AppError("文档文字过多，请拆分或精简后重新上传", code=4027)
    return sections


def process_project(
    source: Path,
    destination: Path,
    storage_base: Path,
    original_filename: str,
    limits: ArchiveLimits,
    max_characters: int,
    *,
    run_context: dict | None = None,
) -> list[dict]:
    if run_context:
        destination.parent.mkdir(parents=True, exist_ok=True)
        marker = destination.parent / f".{destination.name}.worker.json"
        with marker.open("x", encoding="utf-8") as handle:
            json.dump({**run_context, "pid": os.getpid()}, handle)
    if source.suffix.lower() == ".zip":
        entries = inspect_zip(source, limits)
        # Duplicate normalized archive paths cannot identify immutable source files.
        if len({entry.relative_path for entry in entries}) != len(entries):
            raise AppError("压缩包包含重复文件路径，请整理后重试", code=4028)
        extracted = extract_selected_files(source, destination, entries)
    else:
        sections = process_document(source, "", max_characters)
        destination.mkdir(parents=True, exist_ok=True)
        normalized = destination / "document.txt"
        text = "\n\n".join(
            f"[第{section.page_number}页]\n{section.content}"
            if section.page_number
            else section.content
            for section in sections
        )
        normalized.write_text(text, encoding="utf-8")
        extracted = [normalized]
    if not extracted:
        raise AppError(
            "没有可分析文件，请上传源代码ZIP或包含文字的PDF、DOCX、TXT、图片作品",
            code=4029,
        )
    records = []
    for path in extracted:
        content = path.read_bytes()
        text = content.decode("utf-8", errors="replace")
        if "\x00" in text:
            continue
        records.append(
            {
                "relative_path": path.relative_to(destination).as_posix(),
                "content_hash": hashlib.sha256(content).hexdigest(),
                "language": language_for(path) or ("Document" if source.suffix != ".zip" else None),
                "size_bytes": len(content),
                "line_count": text.count("\n") + 1,
                "storage_key": path.relative_to(storage_base).as_posix(),
                "analysis_status": "indexed",
            }
        )
    if not records:
        raise AppError("未找到可预览的文本文件", code=4029)
    return records
