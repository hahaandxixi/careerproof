"""Export a committed CareerProof source snapshot without local runtime data.

Uses only Python's standard library and Git. No dependency installation,
network, database, worktree mutation or release approval is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
REVIEW_FIXTURE = "docs/evidence/20261010-AI-blind-plan-review/review.json"
PDF = "output/pdf/CareerProof-技术文档-提交候选稿.pdf"
REQUIRED = {
    "README.md", "THIRD_PARTY_NOTICES.md", "Start-Local.ps1", "Stop-Local.ps1",
    "backend/pyproject.toml", "backend/app/main.py", "backend/.env.example",
    "backend/docker-compose.yml", "jianli/package.json", "jianli/package-lock.json",
    "jianli/src/app/page.tsx", "demo/build_role_packs.py", REVIEW_FIXTURE,
    "docs/guides/使用与启动.md", "backend/evals/quality-blind-plan-review-input.json",
}
PRIVATE_PARTS = {".git", "storage", "node_modules", "__pycache__", ".pytest_cache",
                 ".ruff_cache", ".cache"}
SECRET_ASSIGNMENT = re.compile(
    rb"(?:DEEPSEEK|DASHSCOPE|ZHIPU)_API_KEY\s*=\s*['\"]?(sk-[A-Za-z0-9_-]{24,})"
)


def git(root: Path, *arguments: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *arguments], cwd=root, input=data, capture_output=True, check=True,
    ).stdout


def included(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or "\\" in name or ":" in name or ".." in path.parts:
        return False
    if any(ord(character) < 32 for character in name):
        return False
    if any(part.lower() in PRIVATE_PARTS or part.lower().startswith((".tmp", ".venv", ".next"))
           for part in path.parts):
        return False
    lower = path.name.lower()
    if lower.startswith(".env") and lower != ".env.example":
        return False
    if (lower.endswith((".pem", ".key", ".p12", ".pfx", ".credentials.json"))
            or lower == "demo-credentials.json"):
        return False
    if len(path.parts) == 1:
        return name in {"README.md", "THIRD_PARTY_NOTICES.md", ".gitignore",
                        ".gitattributes", "LICENSE", "LICENSE.md", "COPYING"} or (
            name.startswith(("Start-", "Stop-")) and path.suffix in {".ps1", ".cmd"}
        )
    if path.parts[0] in {"backend", "demo", "scripts"}:
        return True
    if path.parts[0] == "jianli":
        return len(path.parts) == 2 or path.parts[1] in {"src", "public", "tests"}
    if path.parts[0] == "docs":
        return (len(path.parts) == 2 and path.suffix == ".md") or (
            path.parts[1] == "guides" and path.suffix == ".md"
        ) or name == REVIEW_FIXTURE
    return name == PDF


def read_blobs(root: Path, identities: list[str]) -> dict[str, bytes]:
    stream = io.BytesIO(git(root, "cat-file", "--batch", data=(
        "\n".join(identities) + "\n"
    ).encode("ascii")))
    blobs = {}
    for expected in identities:
        identity, kind, length = stream.readline().decode("ascii").strip().split()
        if identity != expected or kind != "blob":
            raise ValueError("Git returned an unexpected source object")
        content = stream.read(int(length))
        if len(content) != int(length) or stream.read(1) != b"\n":
            raise ValueError("Truncated source object")
        blobs[identity] = content
    return blobs


def build(root: Path, output: Path, revision: str = "HEAD") -> dict:
    commit = git(root, "rev-parse", "--verify", "--end-of-options",
                 f"{revision}^{{commit}}").decode().strip()
    entries = []
    for record in git(root, "ls-tree", "-r", "-l", "-z", commit).split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        mode, kind, identity, length = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if not included(name):
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"Unsupported link or object in source package: {name}")
        entries.append((name, mode, identity, int(length)))
    missing = REQUIRED - {entry[0] for entry in entries}
    if missing:
        raise ValueError(f"Missing required source/resources: {', '.join(sorted(missing))}")
    if sum(entry[3] for entry in entries) > 128 * 1024 * 1024:
        raise ValueError("Source snapshot exceeds 128 MiB; review large tracked files first")
    blobs = read_blobs(root, sorted({entry[2] for entry in entries}))
    for name, _mode, identity, _length in entries:
        content = blobs[identity]
        if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            raise ValueError(f"Unmaterialized LFS object: {name}")
        for match in SECRET_ASSIGNMENT.finditer(content):
            if not match[1].startswith((b"sk-synthetic", b"sk-test", b"sk-dummy")):
                raise ValueError(f"Possible provider key in committed content: {name}")
    timestamp = int(git(root, "show", "-s", "--format=%ct", commit).strip())
    date = datetime.fromtimestamp(timestamp, UTC)
    zip_date = (max(1980, date.year), date.month, date.day, date.hour, date.minute, date.second)
    manifest = {
        "kind": "committed-source-preview", "commit": commit,
        "worktree_included": False, "git_history_included": False,
        "license_file_present": any(name in {"LICENSE", "LICENSE.md", "COPYING"}
                                    for name, *_ in entries),
        "scope": "Application, tests, synthetic demo, guides and the required frozen review.",
        "omitted": "Local environments, credentials, uploads, caches, historical raw evidence "
                   "and development task cards are excluded. No release acceptance is implied.",
        "files": {name: {"sha256": hashlib.sha256(blobs[identity]).hexdigest(),
                         "bytes": length, "git_mode": mode}
                  for name, mode, identity, length in sorted(entries)},
    }
    introduction = (
        "# CareerProof 源码预审包\n\n"
        f"来源提交：{commit}\n\n"
        "本包来自已提交源码，不包含工作区未提交改动、Git历史、本机环境、账号密码、"
        "上传材料或模型缓存。依赖安装见backend/README.md和jianli/README.md，"
        "运行与演示见docs/guides。需要在本机准备配置和合成账号，不能复用作者的临时环境。\n\n"
        "包含自动测试所需的合成演示源与冻结评测JSON。历史截图、原始日志及开发任务卡"
        "不随包分发；相关历史证据链接需在原仓库查阅。\n\n"
        "SOURCE_MANIFEST.json列出实际提交和逐文件哈希。本包不是最终验收、许可确认、"
        "评审授权或正式提交证明，视频及最终签署仍须另行完成。\n"
    ).encode()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output.open("xb") as handle:
            created = True
            with ZipFile(handle, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
                def write(name: str, content: bytes, mode: str = "100644"):
                    info = ZipInfo(name, date_time=zip_date)
                    info.create_system = 3
                    info.external_attr = int(mode, 8) << 16
                    info.compress_type = ZIP_DEFLATED
                    archive.writestr(info, content, compresslevel=9)
                for name, mode, identity, _length in sorted(entries):
                    write(name, blobs[identity], mode)
                write("SOURCE_PACKAGE.md", introduction)
                write("SOURCE_MANIFEST.json", (json.dumps(
                    manifest, ensure_ascii=False, sort_keys=True, indent=2
                ) + "\n").encode("utf-8"))
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output/source/CareerProof-source-preview.zip")
    args = parser.parse_args()
    manifest = build(ROOT, args.output, args.ref)
    print(f"Source snapshot {manifest['commit']}: {len(manifest['files'])} files")
    print(f"Written: {args.output.resolve()}")
    print("Uncommitted changes are excluded; final acceptance and permissions remain pending.")


if __name__ == "__main__":
    main()
