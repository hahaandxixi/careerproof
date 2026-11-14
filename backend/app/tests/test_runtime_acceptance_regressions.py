"""Bounded regressions from confirmed synthetic runtime acceptance; no network calls."""
import pytest

from app.agents.contracts import runtime_plan_without_implementation_step


@pytest.mark.parametrize("step", ["编写 SQL 查询定位异常记录。", "编写SQL查询，并保存查询脚本。"])
def test_sql_query_implementation_is_not_misclassified_as_runtime_only(step):
    assert not runtime_plan_without_implementation_step(
        "一个 SQL 查询脚本或 Notebook 片段，包含查询语句、结果截图或输出，"
        "以及对异常结果的解释说明。",
        ["准备一个含异常数据的样例表并导入数据库。", step, "执行查询并保存输出。"],
    )


@pytest.mark.parametrize("steps", [
    ["执行现有 SQL 查询并截图输出。"],
    ["展示 SQL 查询结果并上传截图。"],
    ["查询异常记录并保存输出。"],
    ["无需编写SQL查询，只执行并截图输出。"],
    ["不需要编写 SQL 查询，只执行并截图输出。"],
])
def test_sql_runtime_artifacts_without_implementation_are_still_rejected(steps):
    assert runtime_plan_without_implementation_step("SQL 查询结果截图", steps)


def test_saved_sql_rejection_excerpt_contains_implementation():
    assert not runtime_plan_without_implementation_step(
        "SQL 查询脚本（含查询语句和注释）及异常结果解释文档。",
        ["编写针对示例数据的 SQL 查询，覆盖异常值筛选。", "运行查询并保存结果输出。"],
        skill="SQL",
    )


@pytest.mark.parametrize("step", [
    "无需提交 SQL 代码，只交运行结果。",
    "编写 Redis 缓存代码；保存 SQL 查询结果。",
    "修改 SQL 查询结果截图。",
])
def test_unrelated_or_negated_implementation_does_not_cover_sql(step):
    assert runtime_plan_without_implementation_step("SQL 查询结果截图", [step], skill="SQL")
