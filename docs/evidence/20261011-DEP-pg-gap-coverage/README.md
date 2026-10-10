# 传智杯29 证据：升级环境剩余28项PG集成证据补齐（2026-10-11）

Git HEAD `ab8713e28b50a01365f5f8d8fdcbeb024debe0ef`（main）。任务卡：`docs/task-cards/20261011-upgraded-pg-gap-coverage.md`。
唯一DB测试执行者本轮：本任务。源码/测试全程只读，零修改；未暂存/提交/推送。

## 升级运行时

- 解释器：`backend/.venv-dependency23/Scripts/python.exe`，Python 3.12.14
- 依赖 pin 运行时核验16项与 `pyproject.toml` 全一致（fastapi 0.143.0 / sqlalchemy 2.0.43 / asyncpg 0.30.0 / pytest 9.0.3 / pytest-asyncio 1.4.0 等），见 `runtime-pins.txt`
- 数据库：仅 SELECT 1 连通检查；PostgreSQL 17.11，loopback 127.0.0.1:5432，db `careerproof`，非超级用户；未启停容器/服务、未安装任何东西。见 `connectivity-safe-facts.txt`

## 精确命令

```bash
cd backend
# 收集（无DB连接）：--collect-only -q -p no:cacheprovider --basetemp=backend/.tmp/dep-pg-gaps-20261011-collect，60节点
# Run1（9模块一次运行；URL经CAREERPROOF_TEST_DATABASE_URL由父进程传入子进程，不打印）：
.venv-dependency23/Scripts/python.exe .tmp/dep-pg-gaps-20261011-aux/run_gaps.py
# Run2（仅Run1失败的4个matching节点，basetemp改用backend/.tmp-dep-pg-gaps-20261011-matching-rerun满足worker仓库防护）：
.venv-dependency23/Scripts/python.exe .tmp/dep-pg-gaps-20261011-aux/rerun_matching.py
```

两次均 `-p no:cacheprovider -q -ra` + 自有观测插件（只记录，不改结果）。

## 结果汇总

| 运行 | 范围 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|
| Run1 | 9模块全量60节点 | 56 | 4 | 0 |
| Run2 | Run1失败的4节点 | 4 | 0 | 0 |
| 合计 | 60节点全部实跑 | 60 | 0 | 0 |

9模块28项原跳过节点 1/8/2/1/3/2/2/1/8 全部实跑且通过（0跳过），逐节点见 `28-nodes-results.txt`；其余32个普通用例作为本轮PG受影响回归全部通过。不覆盖也不重复已过全量1094与18项PG专项。

### Run1 4个失败的真实原因（原文保留于 run1-stdout-full.txt，未改任何断言）

`ValueError: Matching storage must belong to this hard-stop test's materials`（`ops_hard_stop_worker.py:71`，经测试自身 `redact()` 输出）。根因：worker 仓库防护要求 storage 相对 backend 的首段路径以 `.tmp-` 开头（`ops_hard_stop_worker.py:74`），而任务卡字面 basetemp `backend/.tmp/dep-pg-gaps-20261011-run` 使首段为 `.tmp`。属调用方式与既有防护不兼容，非被测代码缺陷；Run2 仅改 basetemp 形状（`backend/.tmp-dep-pg-gaps-20261011-matching-rerun`）后4节点全过，反证诊断。

## 隔离与硬停范围

- URL 处理：父进程 `app.core.config.settings.database_url` 读取，仅经环境变量传子进程；证据目录经全目录密钥扫描（password/URL/api key/secret/Bearer 等）零命中
- Schema 隔离：每个 fixture 仅创建/销毁自身随机 `cp_test_{uuid4().hex}`；创建后断言 `current_schema()` 与每张表 namespace == 自身 schema；finally 仅 `DROP SCHEMA 自己 CASCADE` 且带 `cp_test_[0-9a-f]{32}` 正则守卫（`test_real_matching.py` matching_db、`test_durable_attempt_service.py` durable_case、`test_knowledge_semantic_postgres.py` knowledge_db）。运行前后 cp_test_* schema 计数均为2（全是历史遗留，未触碰），public 业务零变更
- 硬停：仅 `test_real_child_hard_stop_then_database_only_recovery` 生成 nonce 子进程；terminate 前逐一核对 parent_pid==child.pid、nonce、phase、task、schema、创建时间窗、物理HTTP计数，只杀自身子PID
- 外发：conftest autouse `ai_external_enabled=False, provider=mock`；worker 子进程内部联锁同样关闭外发，provider 为 `httpx.MockTransport` 合成；无真实模型/邮件/联网
- 未验证项（超出本卡范围）：18项PG专项（不重复）、E2E/业务数据、真实外发链路、Codex 最高风险复验（交棒后由 Codex 独立执行）
