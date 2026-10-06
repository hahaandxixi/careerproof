# PRODUCT-01 独立 PG Alembic 全链交棒

2026-10-06；Git 根 `D:\jbcode\web ai\jianli`；测试时 HEAD `2f91484`。仅本目录新增脚本、原始输出、哈希与本交棒；未改业务源码、正式清单、前端、配置或 Git。

## 结论

- **通过**：现有 `alembic/env.py`，从空随机 `cp_test_7f54eab143d94c80b7847e28a4006093` schema 经 `0001→…→0014→0015`，再 `0015→0014→0015`。每次迁移连接先断言 `current_schema()`，预检事务回退后交给 Alembic。原始记录 `run2.raw.out`，EXIT 0。
- **通过**：0014 插入的合成任务、报告、投递三行在升级、回退、再升级后 row JSON SHA256 均为 `f49db423a8bd4a0cc62cc5f713b99f5c00cb08602d49ee482748150e477531cb`。0015 草稿可写可读，唯一约束与增长任务 FK 拒绝违规行。
- **通过**：两次随机测试 schema 均已清除。只读复核 `public.alembic_version=0013_ai_usage_idempotency`、public `target_job_id` 不存在、public `growth_answer_drafts` 不存在，见 `public-readonly-after.raw.out`。
- **未验证**：运行库正式升级、真实业务行、真实模型、前端页面和完整 PRODUCT-01 功能签收。

## 首次失败及处置

首次 `run.raw.out` 的脚本仅检查 `current_schema`，但空测试 schema 无 `alembic_version`，搜索路径的 `public` 回落让 Alembic 误读 `public` 的 0013，执行了 0014 DDL 路径。预检 `SELECT` 开启的事务未提交，退出时回滚；随后只读检查确认 public 版本和列未变化。该次**不计全链通过**，也不能说未曾尝试 public DDL。已保留原日志，未对 public 补写或回退。修正脚本先证明新 schema 为空，再在其内建空的 Alembic 版本表，同时结束迁移前的预检事务；第二次运行显示从 `0001` 起完整执行。该版本表仅为 Alembic 自身账本，不是业务预置表。

源码参照：`backend/alembic/env.py` 直接调用 `async_engine_from_config` 且未显式设版本表 schema；`backend/alembic/versions/0015_growth_answer_drafts.py` 新表、唯一 FK 与回退逻辑。脚本 `verify_chain.py` 在进程内替换引擎工厂，将全部连接固定到新 schema，并且只会清理与自身随机 UUID 匹配的 schema。
