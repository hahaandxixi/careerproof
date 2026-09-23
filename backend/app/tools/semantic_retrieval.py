"""Optional, local semantic recall over bounded project documentation.

The ONNX model never sees material outside the isolated analysis worker. Its
hits are source-exact, low-strength candidates; they cannot change rule scores.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from app.tools.code_analyzer import CodeEvidence, ProjectFileSnapshot
from app.tools.matcher import RequirementInput

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REPOSITORY = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
MODEL_REVISION = "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
MODEL_SHA256 = "634d0f66c29dc934c8fa72b8a4fe91dd4d420a22f1d82a241058d4316e659a99"
VERSION = "multilingual-minilm-docs-v1"
MAX_DOCUMENT_FILES = 64
MAX_WINDOWS_PER_FILE = 24
MAX_WINDOWS = 128
MAX_REQUIREMENTS = 8
MAX_HITS_PER_REQUIREMENT = 2
MIN_SIMILARITY = 0.33
DOCUMENT_SUFFIXES = {".md", ".txt", ".rst"}


class Embedder(Protocol):
    def embed(self, documents: list[str]) -> Iterable: ...


def model_directory(cache_dir: Path) -> Path:
    return (
        cache_dir
        / "models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
        / "snapshots"
        / MODEL_REVISION
    )


def model_available(cache_dir: Path) -> bool:
    return (model_directory(cache_dir) / "model_optimized.onnx").is_file()


def load_local_model(cache_dir: Path) -> Embedder:
    """Load a pinned, checksum-verified model without any runtime download."""
    location = model_directory(cache_dir)
    required = (
        "model_optimized.onnx",
        "tokenizer.json",
        "tokenizer_config.json",
        "config.json",
        "special_tokens_map.json",
    )
    if any(not (location / name).is_file() for name in required):
        raise FileNotFoundError("Local semantic model is not installed")
    digest = hashlib.sha256()
    with (location / "model_optimized.onnx").open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != MODEL_SHA256:
        raise ValueError("Local semantic model checksum mismatch")
    from fastembed import TextEmbedding

    return TextEmbedding(
        model_name=MODEL_NAME,
        specific_model_path=str(location),
        local_files_only=True,
        threads=2,
    )


def _windows(files: list[ProjectFileSnapshot]) -> list[tuple[ProjectFileSnapshot, int, str]]:
    windows: list[tuple[ProjectFileSnapshot, int, str]] = []
    accepted_files = 0
    for file in files:
        path = PurePosixPath(file.path.replace("\\", "/"))
        if path.suffix.lower() not in DOCUMENT_SUFFIXES:
            continue
        if path.name.lower() in {"license.txt", "license.md", "requirements.txt"}:
            continue
        accepted_files += 1
        if accepted_files > MAX_DOCUMENT_FILES:
            break
        lines = file.content.splitlines()
        per_file = 0
        for offset in range(0, len(lines), 2):
            if per_file >= MAX_WINDOWS_PER_FILE or len(windows) >= MAX_WINDOWS:
                break
            slice_lines = lines[offset : offset + 3]
            first = next((index for index, line in enumerate(slice_lines) if line.strip()), None)
            if first is None:
                continue
            anchor = offset + first + 1
            content = "\n".join(slice_lines[first:]).strip()
            if len(content) < 20 or len(content) > 1000:
                continue
            windows.append((file, anchor, content))
            per_file += 1
        if len(windows) >= MAX_WINDOWS:
            break
    return windows


def has_document_windows(files: list[ProjectFileSnapshot]) -> bool:
    return bool(_windows(files))


def _cosine(left, right) -> float:
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
    right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def retrieve_semantic_candidates(
    requirements: list[RequirementInput],
    files: list[ProjectFileSnapshot],
    model: Embedder,
) -> tuple[dict[UUID, list[CodeEvidence]], int]:
    """Find paraphrased documentation candidates; never infer implementation."""
    windows = _windows(files)
    selected_requirements = requirements[:MAX_REQUIREMENTS]
    if not windows or not selected_requirements:
        return {}, len(windows)
    queries = [f"{item.skill}：{item.title}" for item in selected_requirements]
    texts = [*queries, *(content for _, _, content in windows)]
    vectors = []
    for start in range(0, len(texts), 32):
        vectors.extend(model.embed(texts[start : start + 32]))
    if len(vectors) != len(queries) + len(windows):
        raise ValueError("Semantic model returned an incomplete batch")
    dimensions = len(vectors[0])
    if not dimensions or any(
        len(vector) != dimensions
        or any(not math.isfinite(float(value)) for value in vector)
        for vector in vectors
    ):
        raise ValueError("Semantic model returned invalid vectors")
    found: dict[UUID, list[CodeEvidence]] = {}
    document_vectors = vectors[len(queries) :]
    for requirement, query_vector in zip(selected_requirements, vectors, strict=False):
        ranked = sorted(
            (
                (_cosine(query_vector, vector), index)
                for index, vector in enumerate(document_vectors)
            ),
            reverse=True,
        )
        hits: list[CodeEvidence] = []
        seen_anchors: set[tuple[str, int]] = set()
        for similarity, index in ranked:
            if similarity < MIN_SIMILARITY:
                break
            file, anchor, _ = windows[index]
            path = file.path.replace("\\", "/")
            if (path, anchor) in seen_anchors:
                continue
            seen_anchors.add((path, anchor))
            line = file.content.splitlines()[anchor - 1]
            hits.append(
                CodeEvidence(
                    skill=requirement.skill,
                    evidence_type="semantic_document_candidate",
                    file_path=path,
                    line_start=anchor,
                    line_end=anchor,
                    snippet=line.strip()[:240],
                    strength="low",
                    explanation=(
                        "本地语义模型找到了与岗位要求相近的项目文档原文；"
                        "只是待核对线索，不能证明代码实现、运行结果或本人贡献。"
                    ),
                    content_hash=hashlib.sha256(file.content.encode("utf-8")).hexdigest(),
                )
            )
            if len(hits) >= MAX_HITS_PER_REQUIREMENT:
                break
        if hits:
            found[requirement.id] = hits
    return found, len(windows)
