"""Unit tests for the knowledge embedding engine selection and fallbacks."""

from __future__ import annotations

import math

import pytest

from app.services import retrieval
from app.services.retrieval import (
    EMBEDDING_DIMENSIONS,
    HASH_ENGINE,
    SEMANTIC_ENGINE,
    _batch_embeddings,
    embed_for_index,
    local_embedding,
    select_query_engine,
)


class FakeEmbedder:
    def __init__(self, *, fail: bool = False, dimensions: int = EMBEDDING_DIMENSIONS):
        self.fail = fail
        self.dimensions = dimensions
        self.calls: list[list[str]] = []

    def embed(self, documents: list[str]):
        self.calls.append(list(documents))
        if self.fail:
            raise RuntimeError("inference failed")
        for text in documents:
            yield local_embedding(text)[: self.dimensions]


def test_local_embedding_is_unit_normalized_and_deterministic():
    first = local_embedding("熟悉 FastAPI 与 PostgreSQL 的后端开发")
    second = local_embedding("熟悉 FastAPI 与 PostgreSQL 的后端开发")
    assert len(first) == EMBEDDING_DIMENSIONS == 384
    assert first == second
    norm = math.sqrt(sum(value * value for value in first))
    assert norm == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize(
    ("engines", "available", "expected", "mixed"),
    [
        ([], True, None, False),
        ([HASH_ENGINE], True, HASH_ENGINE, False),
        ([SEMANTIC_ENGINE], True, SEMANTIC_ENGINE, False),
        ([SEMANTIC_ENGINE], False, None, False),
        ([HASH_ENGINE], False, HASH_ENGINE, False),
        # Mixed indexes resolve to the newest chunk's engine and surface the flag.
        ([HASH_ENGINE, SEMANTIC_ENGINE], True, HASH_ENGINE, True),
        ([SEMANTIC_ENGINE, HASH_ENGINE], True, SEMANTIC_ENGINE, True),
        ([SEMANTIC_ENGINE, HASH_ENGINE], False, None, True),
        (["future-engine"], True, None, False),
    ],
)
def test_select_query_engine_matrix(engines, available, expected, mixed):
    assert select_query_engine(engines, semantic_available=available) == (expected, mixed)


def test_embed_for_index_falls_back_to_hash_when_model_missing(monkeypatch):
    monkeypatch.setattr(retrieval, "load_semantic_embedder", lambda: None)
    vector, engine = embed_for_index("负责订单服务的数据库设计与查询优化")
    assert engine == HASH_ENGINE
    assert len(vector) == EMBEDDING_DIMENSIONS


def test_embed_for_index_uses_semantic_engine_when_available(monkeypatch):
    embedder = FakeEmbedder()
    monkeypatch.setattr(retrieval, "load_semantic_embedder", lambda: embedder)
    vector, engine = embed_for_index("负责订单服务的数据库设计与查询优化")
    assert engine == SEMANTIC_ENGINE
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert embedder.calls == [["负责订单服务的数据库设计与查询优化"]]


def test_batch_embeddings_fall_back_to_hash_when_inference_fails(monkeypatch):
    monkeypatch.setattr(retrieval, "load_semantic_embedder", lambda: FakeEmbedder(fail=True))
    texts = ["第一条材料", "第二条材料"]
    vectors, engine = _batch_embeddings(texts)
    assert engine == HASH_ENGINE
    assert len(vectors) == len(texts)
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors)


def test_batch_embeddings_reject_mismatched_dimensions(monkeypatch):
    monkeypatch.setattr(
        retrieval, "load_semantic_embedder", lambda: FakeEmbedder(dimensions=64)
    )
    vectors, engine = _batch_embeddings(["任意材料"])
    assert engine == HASH_ENGINE
    assert len(vectors[0]) == EMBEDDING_DIMENSIONS
