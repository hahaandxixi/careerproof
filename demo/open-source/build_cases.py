"""Package pinned public-source excerpts as upload fixtures, not project code.

Run after cloning the three repositories at the commits listed below. The
generated ZIPs stay under backend/.tmp and are excluded from the submission.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "backend" / ".tmp" / "open-source-cases" / "sources"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "backend" / ".tmp" / "open-source-cases" / "generated"
MAX_UPLOAD_FILE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class SourceSpec:
    slug: str
    repo: str
    commit: str
    license_name: str
    files: tuple[str, ...]


SOURCES = (
    SourceSpec(
        "flask",
        "https://github.com/pallets/flask",
        "d73fa1cdcbd8b1465c151db8924ba58b1dd14e35",
        "BSD-3-Clause",
        (
            "LICENSE.txt",
            "examples/tutorial/LICENSE.txt",
            "examples/tutorial/README.rst",
            "examples/tutorial/flaskr/__init__.py",
            "examples/tutorial/flaskr/auth.py",
            "examples/tutorial/flaskr/blog.py",
            "examples/tutorial/flaskr/db.py",
            "examples/tutorial/flaskr/schema.sql",
            "examples/tutorial/tests/conftest.py",
            "examples/tutorial/tests/test_auth.py",
            "examples/tutorial/tests/test_blog.py",
            "examples/tutorial/tests/test_db.py",
        ),
    ),
    SourceSpec(
        "client_python",
        "https://github.com/prometheus/client_python",
        "9cd073cb4dc6ee617eadf02dcdec94e0225eff0a",
        "Apache-2.0",
        (
            "LICENSE",
            "NOTICE",
            "README.md",
            "prometheus_client/asgi.py",
            "prometheus_client/exposition.py",
            "prometheus_client/metrics.py",
            "prometheus_client/process_collector.py",
            "tests/test_core.py",
            "tests/test_exposition.py",
        ),
    ),
    SourceSpec(
        "peewee",
        "https://github.com/coleifer/peewee",
        "fa29ff5d56cc7b597a9309b83c245042ebd94ef1",
        "MIT",
        (
            "LICENSE",
            "README.rst",
            "peewee.py",
            "examples/analytics/app.py",
            "examples/analytics/reports.py",
            "examples/fastapi_example.py",
            "tests/db_tests.py",
        ),
    ),
)

CASES = (
    {
        "id": "flask-backend",
        "resume": "flask-backend.txt",
        "project": "flask",
        "suggestedJob": "Python 后端开发实习生（合成演示）",
        "expectedBoundary": "公开路由代码不能证明本人开发或服务已运行；FastAPI 等未展示要求应留作缺口。",
    },
    {
        "id": "prometheus-ops",
        "resume": "prometheus-ops.txt",
        "project": "client_python",
        "suggestedJob": "自动化运维工程师（合成演示）",
        "expectedBoundary": "指标暴露代码不能证明告警处置、部署、回滚或本人贡献。",
    },
    {
        "id": "peewee-dba",
        "resume": "peewee-dba.txt",
        "project": "peewee",
        "suggestedJob": "数据库工程师 DBA（合成演示）",
        "expectedBoundary": "ORM 查询或索引定义不能证明十倍提速、执行计划结果或恢复演练。",
    },
    {
        "id": "flask-qa",
        "resume": "flask-qa.txt",
        "project": "flask",
        "suggestedJob": "软件测试工程师（合成演示）",
        "expectedBoundary": "测试断言存在不能证明运行过、全部通过或由本人编写。",
    },
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_new_or_identical(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"Existing fixture differs: {path}")
        return
    path.write_bytes(data)


def package(spec: SourceSpec, source_root: Path, output_root: Path) -> dict:
    source = (source_root / spec.slug).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Clone is missing: {source}")
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != spec.commit:
        raise ValueError(f"{spec.slug} is at {commit}, expected {spec.commit}")

    file_rows = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in spec.files:
            parts = PurePosixPath(relative).parts
            if not parts or ".." in parts:
                raise ValueError(f"Unsafe source path: {relative}")
            path = source.joinpath(*parts)
            if not path.is_file() or path.is_symlink() or source not in path.resolve().parents:
                raise FileNotFoundError(f"Unsafe or missing source file: {path}")
            data = path.read_bytes()
            if len(data) > MAX_UPLOAD_FILE_BYTES:
                raise ValueError(f"Source exceeds upload per-file limit: {relative}")
            entry = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, data)
            file_rows.append({"path": relative, "sha256": sha256(data), "bytes": len(data)})
        attribution = (
            "THIRD-PARTY PUBLIC SOURCE / SYNTHETIC TEST FIXTURE\n"
            f"Original repository: {spec.repo}\n"
            f"Pinned commit: {spec.commit}\n"
            f"License: {spec.license_name}; see included license file(s).\n"
            "No synthetic resume claims ownership or contribution to this project.\n"
            "Inspect source as evidence of file content only, not of a person's ability.\n"
        ).encode("utf-8")
        entry = zipfile.ZipInfo("SOURCE.txt", date_time=(2026, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o644 << 16
        archive.writestr(entry, attribution)

    data = buffer.getvalue()
    archive_path = output_root / f"{spec.slug}-public-source.zip"
    write_new_or_identical(archive_path, data)
    return {
        "slug": spec.slug,
        "repository": spec.repo,
        "commit": spec.commit,
        "license": spec.license_name,
        "zip": archive_path.name,
        "zipSha256": sha256(data),
        "files": file_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources-dir", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    source_root = args.sources_dir.resolve()
    output_root = args.output_dir.resolve()
    sources = [package(spec, source_root, output_root) for spec in SOURCES]
    resumes = REPO_ROOT / "demo" / "open-source" / "resumes"
    cases = [
        {
            **case,
            "resumeSha256": sha256((resumes / case["resume"]).read_bytes()),
        }
        for case in CASES
    ]
    manifest = {
        "purpose": "Synthetic attribution, retrieval and AI career-guidance tests only",
        "sources": sources,
        "cases": cases,
    }
    serialized = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    write_new_or_identical(output_root / "manifest.json", serialized)
    print(f"Prepared {len(sources)} public-source ZIPs and {len(cases)} synthetic resumes")
    print(f"Output: {output_root}")


if __name__ == "__main__":
    main()
