"""Bounded regressions from confirmed synthetic runtime acceptance; no network calls."""
import pytest

from app.agents.contracts import runtime_plan_without_implementation_step
from app.services.career_planning import career_runtime_plan_without_implementation


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


@pytest.mark.parametrize("step", [
    "编写针对示例数据的 SQL 查询，覆盖异常值筛选。",
    "针对清洗前后的数据设计一条能查出异常记录的 SQL 查询。",
    "针对异常数据使用 SQL 进行排查，编写查询脚本并保存运行输出",
    "提交针对异常数据的 SQL 查询并附上输出",
    "使用 SQL 排查异常，编写对应的查询脚本并保存输出",
    "补充针对缺失值的 SQL 聚合统计查询脚本并记录执行输出",
    "编写SQL查询语句并保存执行输出",
    "提交SQL脚本并记录运行结果",
])
def test_saved_sql_rejection_excerpt_contains_implementation(step):
    assert not career_runtime_plan_without_implementation(
        "一份 SQL 异常核查记录文档。",
        [step, "运行查询并保存结果输出。"],
        skill="SQL",
    )


@pytest.mark.parametrize("step", [
    "无需提交 SQL 代码，只交运行结果。",
    "编写 Redis 缓存代码；保存 SQL 查询结果。",
    "修改 SQL 查询结果截图。",
    "运行 SQL 并展示查询结果以验证实现",
    "提交 SQL 查询脚本的运行日志",
    "使用 SQL 查询数据，编写 Python 脚本并保存输出",
    "使用 SQL 查询数据，不编写查询脚本，只交运行输出",
    "同学建议提交 SQL 查询脚本，我先附上运行结果日志",
    "提交 SQL 查询的验证结果",
    "编写 SQL 查询语句不是必须的，不用提交代码，只交运行结果",
])
def test_unrelated_or_negated_implementation_does_not_cover_sql(step):
    assert career_runtime_plan_without_implementation("SQL 查询结果截图", [step], skill="SQL")
