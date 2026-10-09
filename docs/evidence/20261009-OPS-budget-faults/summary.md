# OPS 预算事务提交故障回归 — 实施记录（传智杯20 / BigModel 个人 GLM-5.3）— 2026-10-09

任务卡：`docs/task-cards/20261009-OPS-budget-fault-tests.md`。开工时嵌套仓库 HEAD `9092eab`（分支 `main`）；会话期间叠加了你方 Codex 的文档提交 `4cbbb00`（仅 `docs/当前接力.md` +3/-1），与本轮无冲突。既有工作区修改与全部 `.tmp-*` 目录原样保留，零 Git 提交/推送、无 reset/clean/stash 应用、无真实模型、无外发、无安装部署、未触碰 .env/业务库/迁移/Docker。

## 交付文件（本轮唯一写入）

| 文件 | 说明 | sha256 |
| --- | --- | --- |
| `backend/app/tests/test_ai_budget_fault_recovery.py` | 新增，315 行，6 用例 | `076551aa75c2e7c2bcdc95ba84e246b8da8cc556581e5bf4525a3e852c52b575` |
| `docs/evidence/20261009-OPS-budget-faults/*.raw.out` + 本文件 | 原始输出与结论 | 见下表 |

## 注入方式与语义（诚实边界）

`CommitFaultFactory` 包装 `async_sessionmaker`，代理会话只拦截真实 `session.commit()`，按序号命中目标事务边界（prepare=1、mark_intent=2、receive=3、book_one=4，每个物理 attempt 恰好各一次提交）：

- `before`：先 `rollback()` 再抛 `CommitFault` —— COMMIT 语句从未发出，结果**确定未提交**。不把它说成网络断连歧义。
- `after`：真实 COMMIT 已落库后再抛 —— 歧义提交的**"实际已应用"分支**（断连但服务端已执行 COMMIT）；"未应用"分支即 `before`。

不是用业务函数抛异常代替数据库边界；断言读库均走原始 factory（不经注入包装）。

## 三个故障边界 × 两分支（全部通过）

1. **prepare 提交失败（#1）**：before_send 在 provider 重试 catch 之外，异常直接传播，**0 HTTP**；before 分支 attempt/预留 0 行、容量归零；after 分支 not_sent+held 落库，容量保守 held（不视为空闲）。
2. **收据提交失败（#3）**：包装为 `ProviderReceiptPersistenceError` 且不重发（calls==1）；before 分支不伪造可信费用（usage_raw 空、digest/用量 None、hold 无 actuals，known=(0,0)），`on_failure` 保守恢复 usage_unknown、held 不释放；after 分支可信收据已持久（received_unbooked、(12,7)、digest、settled），迟到失败回调不改写不抹除。
3. **book 提交失败（#4）**：可信收据与预算 actuals 在收据事务中已持久，book 失败不丢（settled (12,7)）；恢复 `reconcile()` 恰好入账一次（唯一 AiUsageLog 行，attempt_id+request_seq 键，(12,7)），再跑 0，全程不重发 HTTP（calls==1）。

## 命令与退出码（backend/，venv `./.venv/Scripts/python.exe`，均 `-p no:cacheprovider` + 新项目内 basetemp）

| 命令 | 原始日志 | 结果 | 退出码 |
| --- | --- | --- | --- |
| pytest `app/tests/test_ai_budget_fault_recovery.py`（SQLite 首跑） | fault-tests-sqlite-first.raw.out | 6 errors：缺 `durable_db` 导入（夹具解析） | 1 |
| 同上（补导入后） | fault-tests-sqlite-second.raw.out | 6 passed | 0 |
| ruff check `app/tests/test_ai_budget_fault_recovery.py` | ruff-new-test.raw.out | 首次 1 error（F811 wire 参数遮蔽）→ 修复后 All checks passed | 1 → 0 |
| pytest 新文件 + `test_ai_budget_attempt_integration` + `test_ai_shared_budget_service` + `test_ai_budget_workflows` + `test_durable_matching` | affected-target-tests-sqlite.raw.out | 34 passed, 2 skipped（PG 专属跳过） | 0 |

## 夹具隔离核查（卡点 2）

`budget_data` → `durable_db`（`test_durable_matching.py:43-125`）：未设 `CAREERPROOF_TEST_DATABASE_URL`（本轮未设）时用 tmp_path 下临时 SQLite；若设则强制 `postgresql+asyncpg` 并创建一次性 `cp_test_[0-9a-f]{32}` 独立 schema（断言校验），DROP 仅限该自建 schema，**public 不落任何行**。全程 MockTransport 合成响应，无真实模型。

## 结论与限制

- 三个边界在 SQLite 上 both-branch 全绿，**未发现实现缺陷**，无红测试交棒。
- SQLite 通过**不等于** PG/真实硬停通过：本注入未覆盖 PG 网络级中断、asyncpg 断连歧义与行锁竞争；PG 门槛待 Docker 修复后由数据库侧运行补齐（保留待办，未自行重启 Docker）。
- 受影响目标测试全绿 + Ruff 干净；未跑全量后端套件（卡未要求，避免与 Codex 并行数据库测试冲突）。
