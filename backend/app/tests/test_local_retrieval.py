import math

from app.services.retrieval import chunk_text, local_embedding


def test_local_chunks_keep_line_citations_and_overlap():
    chunks = chunk_text("第一行\n第二行内容\n第三行内容\n第四行", max_chars=12, overlap_lines=1)
    assert len(chunks) >= 2
    assert chunks[0].line_start == 1
    assert chunks[1].line_start <= chunks[0].line_end
    assert all(chunk.line_start <= chunk.line_end for chunk in chunks)


def test_local_embedding_is_deterministic_normalized_and_query_sensitive():
    first = local_embedding("FastAPI route PostgreSQL")
    second = local_embedding("FastAPI route PostgreSQL")
    unrelated = local_embedding("活动策划 用户调研")
    assert first == second
    assert math.isclose(sum(value * value for value in first), 1.0)
    assert sum(a * b for a, b in zip(first, unrelated, strict=True)) < 0.5
