"""Curated technical cards for the interview practice MVP.

Content is written from official documentation (Python 3.12, PostgreSQL 16,
pytest 8.3) and kept deliberately small: only the three skills the first release
supports. ``reference_points`` are feedback material and must never be returned
before the student answers.
"""

from __future__ import annotations

import hashlib
import json

TECHNICAL_KNOWLEDGE: list[dict] = [
    {
        "knowledge_id": "tech-python-clean-input-types",
        "title": "Python 清洗：先确认输入类型，再定义清洗边界",
        "skill": "Python",
        "topic": "python_data_cleaning",
        "summary": "输入可能是列表、生成器、字符串或 None，先固定类型契约。",
        "principle": (
            "Python 是动态类型语言，函数参数没有运行时类型约束。清洗函数如果直接迭代参数，"
            "传入 None 会抛 TypeError，传入字符串会按字符迭代而不是按记录迭代。"
            "可靠的做法是在函数入口声明可接受的类型（如 Iterable[str]），"
            "对 None 或非可迭代输入单独处理，并把类型不符转成明确的 ValueError/TypeError。"
            "类型契约应写进函数说明与测试，而不是靠调用方记忆。"
        ),
        "reference_points": [
            "说明输入类型契约（列表/可迭代对象/None 各自的处理）",
            "指出对字符串直接迭代会按字符拆分，是常见错误",
            "区分类型错误（TypeError）与值不合法（ValueError）的处理方式",
            "提到用类型注解或运行时校验固定契约，并配测试",
        ],
        "question_angles": [
            "如果调用方传进来的是 None 或单个字符串，你的清洗函数会怎样？",
            "你如何把输入类型契约写清楚，让别人不会误用？",
        ],
        "document": "Python 3.12 官方文档",
        "section": "内置类型 · 类型注解与可迭代对象",
        "source_locator": (
            "docs.python.org/3.12/library/stdtypes.html；docs.python.org/3.12/library/typing.html"
        ),
        "source_label": "Python 3.12 标准库文档：内置类型与 typing",
        "source_url": "https://docs.python.org/3.12/library/stdtypes.html",
        "source_version": "Python 3.12",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["清洗", "类型", "输入边界", "None"],
    },
    {
        "knowledge_id": "tech-python-clean-exception-boundary",
        "title": "Python 清洗：异常边界放在能决定跳过还是中止的位置",
        "skill": "Python",
        "topic": "python_data_cleaning",
        "summary": "逐行处理时，捕获范围要小，跳过与中止要显式区分。",
        "principle": (
            "批量清洗常在循环内转换单条记录。若用一个大 try 包住整个循环，"
            "第一条坏数据就会中止后续全部记录，也无法知道跳过了多少条。"
            "更稳妥的做法是把 try 放在单条记录的处理边界，记录失败行与原因，"
            "对不可恢复错误（如编码错误）再向上抛出。捕获具体异常类型，"
            "不要用裸 except 吞掉所有错误。"
        ),
        "reference_points": [
            "说明捕获范围应限制在单条记录，而不是整个循环",
            "指出裸 except 会隐藏编程错误，应捕获具体异常",
            "提到记录被跳过的行与原因，便于复核",
            "区分可跳过数据问题与应中止的环境问题",
        ],
        "question_angles": [
            "一批 10 万行数据里有 3 行格式错误，你希望程序怎么处理？",
            "你怎么让失败的行事后还能被找到？",
        ],
        "document": "Python 3.12 官方文档",
        "section": "教程 · 错误和异常",
        "source_locator": "docs.python.org/3.12/tutorial/errors.html",
        "source_label": "Python 3.12 教程：错误和异常",
        "source_url": "https://docs.python.org/3.12/tutorial/errors.html",
        "source_version": "Python 3.12",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["清洗", "异常", "错误处理", "跳过"],
    },
    {
        "knowledge_id": "tech-python-missing-values",
        "title": "Python 清洗：None、空字符串与缺失值不是同一件事",
        "skill": "Python",
        "topic": "python_data_cleaning",
        "summary": "缺失、空值和非法值要分别定义，不能统一按假值删除。",
        "principle": (
            'Python 中 None、""、0、False 都是假值，但业务含义完全不同：'
            "None 常表示缺失，空字符串可能是合法输入，0 往往是有效数值。"
            "用 ``if not value`` 统一过滤会把 0 和空字符串一起删掉。"
            '清洗时应显式判断 ``value is None``、``value.strip() == ""`` 等条件，'
            "并说明每种情况是删除、补默认值还是保留。"
        ),
        "reference_points": [
            "区分 None、空字符串、0 的不同业务含义",
            "指出 if not value 会误删 0 与合法空字符串",
            "说明缺失值策略（删除/填充/标记）需要显式定义",
            "提到策略应可测试，而不是隐含在布尔判断里",
        ],
        "question_angles": [
            "你的清洗代码怎么处理空字符串和 0？两者会被一起删掉吗？",
            "缺失值你选择删除还是填充，依据是什么？",
        ],
        "document": "Python 3.12 官方文档",
        "section": "内置类型 · 真值检验",
        "source_locator": "docs.python.org/3.12/library/stdtypes.html#truth-value-testing",
        "source_label": "Python 3.12 标准库文档：真值检验",
        "source_url": "https://docs.python.org/3.12/library/stdtypes.html",
        "source_version": "Python 3.12",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["清洗", "None", "空值", "真值"],
    },
    {
        "knowledge_id": "tech-python-csv-reading",
        "title": "Python 读取 CSV：编码、分隔符与新行处理要先声明",
        "skill": "Python",
        "topic": "python_data_cleaning",
        "summary": "csv 模块要求以 newline='' 打开文件，编码错误要单独处理。",
        "principle": (
            '官方文档建议用 ``open(..., newline="")`` 打开交给 csv 模块的文件，'
            "否则引号内的换行可能被错误拆分。编码不是 UTF-8 时需要显式指定，"
            "无法解码的字节会抛 UnicodeDecodeError，属于输入问题而不是程序缺陷。"
            "分隔符、引号规则也应与数据来源一致，不能默认所有 CSV 都用逗号。"
        ),
        "reference_points": [
            "说明 newline='' 是 csv 模块的官方要求",
            "指出编码应显式指定，UnicodeDecodeError 属于数据问题",
            "提到分隔符与引号规则要和数据源一致",
            "区分读取失败与清洗规则失败",
        ],
        "question_angles": [
            "如果文件是 GBK 编码，你的读取代码会怎样失败？",
            "为什么打开 CSV 文件时要写 newline=''？",
        ],
        "document": "Python 3.12 官方文档",
        "section": "csv — CSV 文件读写",
        "source_locator": "docs.python.org/3.12/library/csv.html",
        "source_label": "Python 3.12 标准库文档：csv",
        "source_url": "https://docs.python.org/3.12/library/csv.html",
        "source_version": "Python 3.12",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["清洗", "CSV", "编码", "文件读取"],
    },
    {
        "knowledge_id": "tech-sql-null-predicate",
        "title": "SQL：NULL 比较要用 IS NULL，不能用 = NULL",
        "skill": "SQL",
        "topic": "sql_query",
        "summary": "NULL 表示未知，任何 = NULL 比较结果都是 unknown，不会命中行。",
        "principle": (
            "SQL 使用三值逻辑：true、false、unknown。NULL 代表未知值，"
            "``col = NULL`` 的结果是 unknown，WHERE 只保留 true，因此查不到任何行；"
            "正确写法是 ``col IS NULL`` 或 ``col IS NOT NULL``。"
            "聚合与去重时 NULL 还有额外规则，例如 COUNT(col) 不统计 NULL。"
        ),
        "reference_points": [
            "说明 NULL 是三值逻辑中的 unknown，不是空字符串",
            "指出 = NULL 永远不成立，应使用 IS NULL",
            "提到 NOT IN 子查询遇到 NULL 会整体失效的风险",
            "举例说明缺失值统计应使用 IS NULL 或 COUNT(*) - COUNT(col)",
        ],
        "question_angles": [
            "要筛出没有填写手机号的用户，你会怎么写条件？为什么不能写 = NULL？",
            "NOT IN 子查询里如果出现 NULL，结果会怎样？",
        ],
        "document": "PostgreSQL 16 官方文档",
        "section": "SQL 语法 · 值表达式与比较运算",
        "source_locator": "postgresql.org/docs/16/functions-comparison.html",
        "source_label": "PostgreSQL 16 文档：比较函数与运算符",
        "source_url": "https://www.postgresql.org/docs/16/functions-comparison.html",
        "source_version": "PostgreSQL 16",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["SQL", "NULL", "三值逻辑", "查询条件"],
    },
    {
        "knowledge_id": "tech-sql-join-grain",
        "title": "SQL：JOIN 会改变行数，先确认粒度再聚合",
        "skill": "SQL",
        "topic": "sql_query",
        "summary": "一对多 JOIN 会放大行数，直接 SUM 会把主表数值重复累加。",
        "principle": (
            "JOIN 按匹配关系展开行：订单表 JOIN 明细表后，一条订单会变成多行。"
            "此时对订单金额求和会按明细条数重复计算。"
            "正确做法是先确认结果粒度（每订单一行还是每明细一行），"
            "或在子查询里先聚合再 JOIN。LEFT JOIN 还会为无匹配行补 NULL，"
            "用 COUNT(明细.id) 而不是 COUNT(*) 才能得到真实匹配数。"
        ),
        "reference_points": [
            "说明一对多 JOIN 会放大行数并导致重复求和",
            "提出先聚合子查询再 JOIN，或按明确粒度聚合",
            "区分 COUNT(*) 与 COUNT(右表列) 在 LEFT JOIN 下的差异",
            "提到核对 JOIN 前后行数是最直接的验证方式",
        ],
        "question_angles": [
            "订单表 JOIN 明细表后求和，金额为什么会翻倍？",
            "LEFT JOIN 之后，怎么统计真正有明细的订单数？",
        ],
        "document": "PostgreSQL 16 官方文档",
        "section": "查询 · 表表达式与连接",
        "source_locator": "postgresql.org/docs/16/queries-table-expressions.html",
        "source_label": "PostgreSQL 16 文档：表表达式（JOIN）",
        "source_url": "https://www.postgresql.org/docs/16/queries-table-expressions.html",
        "source_version": "PostgreSQL 16",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["SQL", "JOIN", "行数", "聚合"],
    },
    {
        "knowledge_id": "tech-sql-aggregate-null",
        "title": "SQL：COUNT、SUM、AVG 与数组聚合的 NULL 口径",
        "skill": "SQL",
        "topic": "sql_query",
        "summary": (
            "SUM/AVG 忽略 NULL，COUNT(col) 只计非 NULL，COUNT(*) 计行数；"
            "array_agg/json_agg 会保留 NULL。"
        ),
        "principle": (
            "聚合函数的 NULL 口径并不统一：SUM(col) 和 AVG(col) 计算时忽略 NULL，"
            "AVG 的分母是该列非 NULL 的行数；COUNT(col) 统计该列非 NULL 的行数，"
            "COUNT(*) 统计结果行数。全为 NULL 时 SUM/AVG 返回 NULL，COUNT 返回 0。"
            "PostgreSQL 的 array_agg(col) 和 json_agg(col) 会把 NULL 作为元素保留，"
            "不能概括为“所有聚合函数都忽略 NULL”。"
            "只有缺失比例，不能判断已观测平均值相对总体平均偏高还是偏低；"
            "还需要缺失机制、缺失值的业务含义以及缺失值本身的信息。"
            "“已观测值的平均数”和“把缺失值按零处理的平均数”回答不同的统计问题；"
            "COALESCE 为零会改变统计口径，必须有明确业务依据，不能作为默认修复。"
        ),
        "reference_points": [
            "区分 COUNT(*) 的行数、COUNT(col) 的非 NULL 数和 AVG 的非 NULL 分母",
            "说明 array_agg/json_agg 保留 NULL，不能概括所有聚合函数忽略 NULL",
            "指出只有缺失比例不能推断平均值偏差方向",
            "区分已观测值平均与缺失按零处理的平均，COALESCE 为零需业务依据",
            "说明还需要缺失机制与业务定义才能解释统计口径",
        ],
        "question_angles": [
            "一张表的 score 有 30% 为 NULL。请分别说明 AVG(score)、COUNT(score)、"
            "COUNT(*) 回答的统计口径。",
            "如果要判断平均分是否因缺失值产生偏差，你还需要了解哪些缺失机制或业务信息？不要预设偏高或偏低。",
            "在 PostgreSQL 中 array_agg(score) 遇到 NULL 会怎样？这与 AVG(score) 的口径有何不同？",
            "COALESCE(score, 0) 后求平均，与只对非 NULL 值求平均，分别代表什么业务定义？",
            "相同缺失比例是否可能对应平均值偏高或偏低？请用缺失机制说明。",
        ],
        "document": "PostgreSQL 16 官方文档",
        "section": "函数与运算符 · 聚合函数",
        "source_locator": "postgresql.org/docs/16/functions-aggregate.html",
        "source_label": "PostgreSQL 16 文档：聚合函数",
        "source_url": "https://www.postgresql.org/docs/16/functions-aggregate.html",
        "source_version": "PostgreSQL 16",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["SQL", "聚合", "NULL", "COUNT", "AVG", "array_agg"],
    },
    {
        "knowledge_id": "tech-sql-where-having",
        "title": "SQL：WHERE 过滤行，HAVING 过滤分组结果",
        "skill": "SQL",
        "topic": "sql_query",
        "summary": "聚合条件必须放在 HAVING，放错位置会报错或算错口径。",
        "principle": (
            "查询执行顺序是 FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY。"
            "WHERE 在分组前过滤原始行，不能引用聚合结果；"
            "HAVING 在分组后过滤，可引用 COUNT/SUM 等聚合。"
            "把聚合条件写进 WHERE 会报错；把普通行条件写进 HAVING 虽然可能执行，"
            "但会先分组再过滤，语义与性能都更差。"
        ),
        "reference_points": [
            "说明 WHERE 作用于行、HAVING 作用于分组",
            "指出 WHERE 不能引用聚合函数",
            "给出“筛选有效行 + 再筛分组”这类组合例子",
            "提到执行顺序决定写法，而不是风格偏好",
        ],
        "question_angles": [
            "要筛出订单数超过 10 的用户，条件应该写在哪一层？",
            "WHERE 里能写 COUNT(*) > 10 吗？为什么？",
        ],
        "document": "PostgreSQL 16 官方文档",
        "section": "SQL 命令 · SELECT",
        "source_locator": "postgresql.org/docs/16/sql-select.html",
        "source_label": "PostgreSQL 16 文档：SELECT（WHERE / HAVING）",
        "source_url": "https://www.postgresql.org/docs/16/sql-select.html",
        "source_version": "PostgreSQL 16",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["SQL", "WHERE", "HAVING", "分组"],
    },
    {
        "knowledge_id": "tech-pytest-assertion-specific",
        "title": "pytest：断言要指向具体结果，而不是只断言真值",
        "skill": "pytest",
        "topic": "pytest",
        "summary": "assert result 只能证明结果为真，不能定位错在哪一步。",
        "principle": (
            "pytest 用原生 assert，失败时会输出表达式细节。"
            "``assert clean(rows)`` 只能说明返回值是假值，无法说明清洗结果错在哪。"
            '应断言具体结构，例如 ``assert clean([" a ", ""]) == ["a"]``，'
            "让失败信息直接显示期望值与实际值。"
            "对列表还要注意顺序与元素类型，避免用真值断言掩盖结果偏差。"
        ),
        "reference_points": [
            "指出只断言真值无法定位差异",
            "建议断言完整期望结果或关键字段",
            "说明 pytest 会展示断言的期望与实际值",
            "提到测试输入要能体现清洗规则，而不是空输入",
        ],
        "question_angles": [
            "你写的 assert 如果失败了，能看出是哪条规则错了吗？",
            "为什么 assert result 不算有效断言？",
        ],
        "document": "pytest 8.3 官方文档",
        "section": "How to write and report assertions",
        "source_locator": "docs.pytest.org/en/8.3.x/how-to/assert.html",
        "source_label": "pytest 8.3 文档：断言",
        "source_url": "https://docs.pytest.org/en/8.3.x/how-to/assert.html",
        "source_version": "pytest 8.3",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["pytest", "断言", "测试质量"],
    },
    {
        "knowledge_id": "tech-pytest-raises-boundary",
        "title": "pytest：用 pytest.raises 固定异常类型与边界输入",
        "skill": "pytest",
        "topic": "pytest",
        "summary": "异常路径要断言具体异常，而不是只断言“会报错”。",
        "principle": (
            "``with pytest.raises(ValueError):`` 能确认异常类型，"
            "但断言过宽会放过同类型的其他错误。可以匹配消息或用 ``match=`` 缩小范围。"
            "边界测试要覆盖空输入、单元素、类型错误和超长输入，"
            "并确认正常输入不会被误判为异常。"
        ),
        "reference_points": [
            "说明 pytest.raises 应指定具体异常类型",
            "建议用 match 或断言消息固定失败原因",
            "列出应覆盖的边界：空输入、单元素、类型错误、超长",
            "提醒同时验证正常路径不被误伤",
        ],
        "question_angles": [
            "输入为 None 时你期望抛什么异常？测试怎么固定这个行为？",
            "空列表和只有一条记录的列表，你的测试分别覆盖了吗？",
        ],
        "document": "pytest 8.3 官方文档",
        "section": "断言预期异常",
        "source_locator": (
            "docs.pytest.org/en/8.3.x/how-to/assert.html#assertions-about-expected-exceptions"
        ),
        "source_label": "pytest 8.3 文档：断言预期异常",
        "source_url": "https://docs.pytest.org/en/8.3.x/how-to/assert.html",
        "source_version": "pytest 8.3",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["pytest", "异常", "边界测试"],
    },
    {
        "knowledge_id": "tech-pytest-parametrize",
        "title": "pytest：参数化覆盖边界组合，而不是复制用例",
        "skill": "pytest",
        "topic": "pytest",
        "summary": "同一规则的多组输入用 parametrize 表达，失败时能定位到具体参数。",
        "principle": (
            "``@pytest.mark.parametrize`` 把输入与期望写成表，"
            "每组参数生成独立用例，失败信息会标明是哪一组。"
            "相比复制多个函数，参数化更易补齐边界组合（空值、全空、混合类型），"
            "也避免漏改某一份复制代码。"
        ),
        "reference_points": [
            "说明参数化让每组输入成为独立用例",
            "指出复制用例容易漏改、难看出覆盖缺口",
            "建议参数表覆盖空值、混合类型、典型正常值",
            "提到失败输出会指出具体参数组合",
        ],
        "question_angles": [
            "你的几条清洗规则是怎么组织测试的？如果新增一种边界要改几处？",
            "参数化相比复制测试函数，能避免什么问题？",
        ],
        "document": "pytest 8.3 官方文档",
        "section": "Parametrizing tests",
        "source_locator": "docs.pytest.org/en/8.3.x/how-to/parametrize.html",
        "source_label": "pytest 8.3 文档：参数化",
        "source_url": "https://docs.pytest.org/en/8.3.x/how-to/parametrize.html",
        "source_version": "pytest 8.3",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["pytest", "参数化", "边界组合"],
    },
    {
        "knowledge_id": "tech-pytest-isolation",
        "title": "pytest：用例之间不共享可变状态",
        "skill": "pytest",
        "topic": "pytest",
        "summary": "模块级可变对象会让用例互相影响，执行顺序一变结果就变。",
        "principle": (
            "测试函数应各自构造所需数据。共享列表、缓存或全局配置时，"
            "前一个用例的修改会带进后一个用例，单独运行通过、全量运行失败。"
            "需要复用时用 fixture 提供独立实例，并在用例结束后清理外部状态。"
        ),
        "reference_points": [
            "指出模块级可变状态会导致用例相互污染",
            "建议用 fixture 提供独立数据或清理",
            "提到测试应能单独运行，也能任意顺序运行",
            "说明外部资源（文件、数据库）也要在用例后还原",
        ],
        "question_angles": [
            "你的测试单独跑通过、一起跑失败，可能是什么原因？",
            "测试里需要一份样例数据，你会放在哪里？",
        ],
        "document": "pytest 8.3 官方文档",
        "section": "Fixtures",
        "source_locator": "docs.pytest.org/en/8.3.x/how-to/fixtures.html",
        "source_label": "pytest 8.3 文档：fixture",
        "source_url": "https://docs.pytest.org/en/8.3.x/how-to/fixtures.html",
        "source_version": "pytest 8.3",
        "review_status": "reviewed",
        "reviewed_at": "2026-11-10",
        "tags": ["pytest", "fixture", "隔离"],
    },
]


def content_digest(entry: dict) -> str:
    payload = json.dumps(
        {
            "title": entry["title"],
            "principle": entry["principle"],
            "referencePoints": entry["reference_points"],
            "sourceVersion": entry["source_version"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
