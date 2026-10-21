"""Export a committed CareerProof source snapshot without local runtime data.

Uses only Python's standard library and Git. No dependency installation,
network, database, worktree mutation or release approval is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import posixpath
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
REVIEW_FIXTURE = "docs/evidence/20261010-AI-blind-plan-review/review.json"
AGENT_FIXTURES = {
    "docs/evidence/20261019-agent-boundary/agent-live-preflight-20261020.json",
    "docs/evidence/20261017-task70-semantic-review-packet/current-smoke-preflight-20261018.json",
}
REVIEW_DOCS = {
    "docs/README.md", "docs/guides/使用与启动.md", "docs/guides/功能演示.md",
    "docs/guides/AI与数据边界.md", "docs/guides/证据与产品能力.md",
    "docs/guides/工具与接入.md", "docs/guides/评测与人工复核.md",
    "docs/guides/比赛交付.md",
}
# Historical outputs remain in Git; eval runners and frozen fixtures stay exported.
HISTORICAL_EVAL_OUTPUTS = {
    f"backend/evals/{stem}.{suffix}"
    for stem in ("demo-zhipu-20260916-run1", "demo-zhipu-v3-run1",
                 "demo-zhipu-v4-20260916-run1")
    for suffix in ("md", "json")
}
REQUIRED = {
    "README.md", "THIRD_PARTY_NOTICES.md", "Start-Local.ps1", "Stop-Local.ps1",
    "backend/pyproject.toml", "backend/app/main.py", "backend/.env.example",
    "backend/docker-compose.yml", "jianli/package.json", "jianli/package-lock.json",
    "jianli/src/app/page.tsx", "demo/build_role_packs.py", REVIEW_FIXTURE,
    "backend/evals/quality-blind-plan-review-input.json",
} | REVIEW_DOCS | AGENT_FIXTURES
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
    if name in HISTORICAL_EVAL_OUTPUTS:
        return False
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
    if path.parts[:2] == (".github", "workflows") and path.suffix in {".yml", ".yaml"}:
        return True
    if path.parts[0] == "jianli":
        return len(path.parts) == 2 or path.parts[1] in {"src", "public", "tests"}
    if path.parts[0] == "docs":
        return name in REVIEW_DOCS | AGENT_FIXTURES | {REVIEW_FIXTURE}
    return False


def reviewer_document(name: str) -> bool:
    """Only navigational documentation, not arbitrary test/source Markdown."""
    return name in REVIEW_DOCS | {
        "README.md", "THIRD_PARTY_NOTICES.md", "backend/README.md", "jianli/README.md",
    } or (name.startswith("demo/") and PurePosixPath(name).name == "README.md")


def markdown_destinations(content: str):
    """Read inline links/images and reference definitions outside code examples.

    This checks local file navigation, not Markdown rendering or URL availability.
    Anchor fragments are deliberately outside its acceptance claim.
    """
    fence = None
    inline = re.compile(
        r'!?\[[^\]\n]*\]\(\s*(?:<([^>\n]*)>|((?:[^()\s\\]|\\.|\([^()\n]*\))+))'
        r'(?:\s+(?:"[^"\n]*"|\'[^\'\n]*\'|\([^()\n]*\)))?\s*\)'
    )
    reference = re.compile(r'^\s{0,3}\[[^\]\n]+\]:\s*(?:<([^>\n]+)>|(\S+))')
    for number, line in enumerate(content.splitlines(), 1):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            run = marker[1]
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        line = re.sub(r"(`+).*?\1", "", line)
        for match in inline.finditer(line):
            yield number, match[1] if match[1] is not None else match[2]
        match = reference.match(line)
        if match:
            yield number, match[1] if match[1] is not None else match[2]


def validate_document_links(contents: dict[str, bytes]) -> list[str]:
    """Reject local links missing from this exact committed export."""
    names = set(contents) | {"SOURCE_PACKAGE.md", "SOURCE_MANIFEST.json"}
    checked = []
    failures = []
    for name, content in sorted(contents.items()):
        if not reviewer_document(name):
            continue
        checked.append(name)
        for line, destination in markdown_destinations(content.decode("utf-8")):
            destination = re.sub(r"\\([\\() ])", r"\1", destination)
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            path = unquote(parsed.path)
            target = posixpath.normpath(
                path.lstrip("/") if path.startswith("/") else
                posixpath.join(posixpath.dirname(name), path)
            )
            if (target not in names and target not in {".", ""}
                    and not any(item.startswith(target.rstrip("/") + "/") for item in names)):
                failures.append(f"{name}:{line}: {destination} -> {target}")
    if failures:
        raise ValueError("Missing package document links:\n" + "\n".join(failures))
    return checked


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
    checked_documents = validate_document_links({
        name: blobs[identity] for name, _mode, identity, _length in entries
    })
    timestamp = int(git(root, "show", "-s", "--format=%ct", commit).strip())
    date = datetime.fromtimestamp(timestamp, UTC)
    zip_date = (max(1980, date.year), date.month, date.day, date.hour, date.minute, date.second)
    manifest = {
        "kind": "committed-source-preview", "commit": commit,
        "worktree_included": False, "git_history_included": False,
        "license_file_present": any(name in {"LICENSE", "LICENSE.md", "COPYING"}
                                    for name, *_ in entries),
        "scope": "Application, tests, synthetic demo, reviewer guides and required test fixtures.",
        "document_link_check": {
            "documents": checked_documents,
            "local_files_and_directories": True, "anchors_and_external_urls_checked": False,
        },
        "omitted": "Local environments, credentials, uploads, caches, historical raw evidence "
                   "and internal development documents are excluded. Video/PDF are separate "
                   "deliverables. No release acceptance is implied.",
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
        "及内部协作记录不随包分发。视频与PDF另行交付；本包未内嵌历史PDF。\n\n"
        "已核对保留说明文档的包内文件与目录链接；未核查外部网址与页内锚点，"
        "也未因此完成干净环境启动验证。赛事要求的完整Git历史须通过原托管仓库"
        "及实际评审访问另行提供，不能用此快照ZIP代替。\n\n"
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
