# B-08 总控复核（2026-10-04）

范围：ZCode 在免费 GLM-5.3 与免费 GLM-5.3-Flash 两个新任务中完成用量入账修复；本文件记录其交棒后 Codex 的独立边界复核。ZCode 的原始命令、输出和退出码在本目录 `red-sqlite.log`、`green-*.log`、`regression-*.log`、`ruff.log`、`full-suite-sqlite.log`、`migration-verify.log`。`review.md` 是交棒时的自审快照，其关于宽松整数解析的 P3 备忘已由下述补丁解决。

## 最终行为与边界

- `application_verification` 在模型响应后用独立短事务记录实际响应中的 token 用量；任务租约丢失、撤回、取消或收尾提交失败不使已提交的用量行回滚。`run_token + request_seq` 部分唯一索引和冲突忽略保证同次请求重试不重复入账；旧行的空键保持原样。
- 仅 JSON 非负整数 `prompt_tokens` 与 `completion_tokens` 都存在时写入用量行。缺失、字符串、小数、布尔、负数均只保留展示用的占位值，`usageKnown=false`。多次响应时必须每次都有可信用量，才标记总用量已知；`usageKnown` 表示响应数据可知，不表示账本提交成功。
- 取消在入账任务等待期间到达时，外层执行可以退出，独立入账在 5 秒有界窗口中继续；新增故障注入在 SQLite 与隔离 PostgreSQL 中均证明行最终落库，原任务不保存结论。进程硬停或数据库持续故障仍可能留下未入账间隙，仅日志记录，尚无自动对账机制；在途模型请求的并发预算超额也不在本次修复范围。
- 固定投递快照和撤回后的结论授权仍由原有最终复查保护。本轮未调用真实 DeepSeek、未使用真实简历、未外发消息、未提交或推送 Git。

## 复核结果

| 检查 | 结果与边界 |
| --- | --- |
| ZCode 红灯与初次修绿 | 原始 `red-sqlite.log` 为 7 项预期失败；交棒时 SQLite 7/7、隔离 PostgreSQL 7/7、PG 验证流程 42/42、Ruff 通过。 |
| ZCode 后端全量 | `full-suite-sqlite.log` 原始输出与退出码：823 通过、24 跳过、退出码 0。该次运行早于下述 Codex 补强，不能冒充最终补强后的全量结果。 |
| Codex 补强后定向复跑 | 在 `backend/` 用 `./.venv/Scripts/python.exe -m pytest app/tests/test_b08_usage_accounting.py -q -p no:cacheprovider --basetemp=./.tmp-b08-codex-final-sqlite`：13 通过；加 `CAREERPROOF_TEST_DATABASE_URL` 指向本地 compose PostgreSQL、使用独立 `cp_test_*` schema 后同文件 13 通过。两次退出码均为 0。终端输出见本轮会话，未另存原始日志。 |
| Codex 静态检查 | B-08 六个改动/新增 Python 文件运行 Ruff：`All checks passed!`；`git diff --check` 退出码 0。 |

`migration-verify.log` 披露：ZCode 首次误用 `CAREERPROOF_DATABASE_URL` 做 Alembic 验证，实际对 compose 的 `careerproof` 库执行了 `0013`。事后确认数据库处于 `0013`、旧用量行仍可查询（48 行）、新增两列与索引存在；随后对 SQLite 单独核验了旧行、空键豁免与重复键拒绝。这里的 48 行是**事后计数**，没有迁移前计数，不能仅凭数字声称逐行哈希不变。
Codex 随后独立用只读 `docker exec ... psql` 核对 `alembic_version=0013_ai_usage_idempotency`、`ai_usage_logs` 仍有 48 行；未对业务数据做更新。

下一轮优先做企业双投递/筛选的生产页面验收，以及 B-16 在真实产品下载流程中的复现。B-08 若继续扩展，应先设计可审计的账本失败标记与重试/对账，不得把 `usageKnown` 当成 `usageBooked`。
