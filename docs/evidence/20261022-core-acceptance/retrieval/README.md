# 检索向量空间与PG分页fixture修复

基线 `ba0c970`，本组只修改 `retrieval.py`、`test_knowledge_semantic_postgres.py`、`test_paginated_lists_postgres.py`。未提交、未安装依赖，未访问正常数据库或模型服务。解释器为既有 `backend/.venv-dependency23/Scripts/python.exe`；本记录不是当前全部CI验收。

## 可复现问题与修复

- 实际PG查询虽然选定queryEngine，MATERIALIZED CTE只限定owner来源，仍把hash/语义/缺标签向量一起按同一余弦距离排序。新测试在未修源码上5失败/1通过，包含真实不同坐标空间、51条新hash掩盖1条旧语义、缺引擎标签和推理故障。修复在owner限定的同一CTE内先匹配`embeddingEngine`，再计算距离/计数。`ownedMatches`现在表示可比引擎内的自有候选数，不表示全部跨空间材料数。
- 引擎判定不再只看最新50条。SQL按全部自有候选的引擎分组、取各组最新时间，选择最新组；`mixedEngines`保留对旧异构/未知标签的提示。没有标签或未知标签不猜作hash、不删原索引；仅这类索引时不返回向量结果，需要按现有索引路径重新处理。混合时只查所选已知空间。语义模型缺失或推理失败不回退hash比较语义向量。
- 未改变`_allowed_source_ids`：材料库搜索仍包括本人未归档材料的所有保存版本；报告的明确版本选择另行保持。新增实际PG用例证明其他owner和本人已归档来源不能影响选择或进入结果。
- `matching_db`单文件可用、按CI实际16模块顺序收集时却不可用：该模块已作为普通测试模块先收集，后来`pytest_plugins`不再把fixture注册到其他模块可见范围。原顺序只选分页8例复现8个setup错误；分页模块改为显式导出同一原fixture，保持生成/检查/删除专属schema的全部逻辑，不扩大skip或修改conftest。相同顺序8通过。

## 实际验证

- 新PG回归红：5 failed / 1 passed，pytest exit1，`retrieval-red.raw.out`。
- 相关检索、版本范围和Z61召回：31 passed，exit0，`retrieval-green.raw.out`。
- CI同顺序分页红→绿：8 setup errors→8 passed / 124 deselected，exit1→0，`fixture-ci-{red,green}.raw.out`。这是同顺序限定分页，不冒充完整严格PG套件。
- 目标Ruff初次F811因fixture直接导入与参数同名；改为模块显式导出原fixture后通过。两轮日志均保留。
- 原始受限沙箱的PG进程无输出卡住，按精确`--basetemp=.tmp/retrieval-red`筛选后只停止自己的两个pytest进程，改为同命令获准权限运行，约2秒完成红例。没有修改ACL或触碰数据库服务。其后所有PG均在明确获准权限中运行。

专属容器 `careerproof-core-acceptance-20261022`、loopback55445、数据库`cp_ci`由总控分配；每例生成独立`cp_test_*` schema并finally清理。外部AI关闭，无真实材料。未访问5432或已有55442演示库。数据库/容器由总控继续拥有，不由本组启停。

精确命令数组、退出码、范围与三文件SHA256见`commands-and-hashes.json`。当前仅覆盖合成坐标空间路由/权限与分页，并非下载MiniLM权重后的真实语义质量评测；全量SQLite、完整PG严格集合、hard-stop、迁移和JUnit门禁由总控另行集成验证。
