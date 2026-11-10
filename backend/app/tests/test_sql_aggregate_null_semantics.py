"""Read-only SQL semantics for the corrected aggregate/NULL knowledge card.

These tests execute the database's own aggregate behavior instead of asserting
that a prose string exists. The SQLite cases cover SUM/AVG/COUNT and the
zero-fill alternative; PostgreSQL-only array_agg behavior lives in the
PostgreSQL semantic test module.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def _row(sql: str):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text(sql))).one()
    finally:
        await engine.dispose()


async def test_sum_avg_and_count_use_different_null_denominators():
    avg, count_col, count_star, total = await _row(
        "SELECT AVG(x), COUNT(x), COUNT(*), SUM(x) FROM "
        "(SELECT 10 AS x UNION ALL SELECT NULL UNION ALL SELECT 30)"
    )
    assert avg == 20
    assert count_col == 2
    assert count_star == 3
    assert total == 40


async def test_all_null_agg_inputs():
    row = await _row(
        "SELECT SUM(x), AVG(x), COUNT(x), COUNT(*) FROM (SELECT NULL AS x UNION ALL SELECT NULL)"
    )
    assert row[0] is None
    assert row[1] is None
    assert row[2] == 0
    assert row[3] == 2


async def test_zero_fill_is_a_different_metric_from_observed_average():
    observed, zero_filled = await _row(
        "SELECT AVG(x), AVG(COALESCE(x, 0)) FROM "
        "(SELECT 10 AS x UNION ALL SELECT 20 UNION ALL SELECT NULL)"
    )
    assert observed == 15
    assert zero_filled == 10


async def test_same_missing_ratio_does_not_imply_one_direction():
    row = await _row(
        "SELECT COUNT(*), COUNT(x), AVG(x), "
        "AVG(CASE WHEN x IS NULL THEN 0 ELSE x END), "
        "AVG(CASE WHEN x IS NULL THEN 30 ELSE x END) FROM "
        "(SELECT 10 AS x UNION ALL SELECT 20 UNION ALL SELECT NULL)"
    )
    assert row[0:2] == (3, 2)  # fixed one-third missing ratio
    observed, missing_zero, missing_thirty = row[2], row[3], row[4]
    assert observed == 15
    assert missing_zero == 10  # observed average is higher
    assert missing_thirty == 20  # observed average is lower
    # The same missing ratio and observed values can imply either direction
    # once missing values are unknown; no fixed bias conclusion is valid.
    assert (observed > missing_zero) != (observed > missing_thirty)


async def test_seed_text_states_the_distinctions_without_a_fixed_bias():
    from app.knowledge.technical_seed import TECHNICAL_KNOWLEDGE

    entry = next(
        item for item in TECHNICAL_KNOWLEDGE if item["knowledge_id"] == "tech-sql-aggregate-null"
    )
    text_value = (
        entry["title"]
        + entry["principle"]
        + "".join(entry["reference_points"])
        + "".join(entry["question_angles"])
    )
    assert "COUNT(*)" in text_value
    assert "COUNT(col)" in text_value
    assert "COUNT(*) = N" in text_value
    assert "COUNT 返回 0" not in text_value
    assert "array_agg" in text_value
    assert "json_agg" in text_value
    assert "不能" in text_value and "偏高" in text_value
    assert "COALESCE" in text_value
    assert "reviewed" not in entry["question_angles"]
    assert entry["review_status"] == "reviewed"
