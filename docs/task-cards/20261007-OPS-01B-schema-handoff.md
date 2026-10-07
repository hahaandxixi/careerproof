# 传智杯17：核验持久请求模型与0016迁移

2026-10-07。传智杯16已实际停止且后端diff/未跟踪实现均为空，记录保留。完整核验协议仍以OPS-01B实施卡为准；此次按文件拆分，不缩小整个goal。你使用Start Plan免费Flash，只做下列确定的模型/迁移/对应测试；不重新设计provider或事务服务。

## 文件所有权

ZCode唯一可写：backend/app/models/ai_request_attempt.py，models/__init__.py注册，models/analysis.py仅新增AiUsageLog.attempt_id；backend/alembic/versions/0016_ai_request_attempts.py；新backend/app/tests/test_ai_request_attempt_schema.py、test_ai_request_attempt_migration.py；docs/evidence/20261007-OPS-01B-schema/及独立临时路径/专属cp_test随机schema。

Codex同时负责另外的文件：agents/attempt_receipts.py、agents/provider.py、services/ai_request_attempts.py、services/application_verification.py及其独立测试。你不得编辑这些文件，也不运行全后端测试；schema单测/迁移是当前唯一数据库fixture写入者，Codex此时只做无数据库解析测试。其它代码/正式文档/业务库/closure/.env/服务/真实模型/外发/Git写入/P2/历史清理禁止。

## 固定字段契约

类AiRequestAttempt，表ai_request_attempts，继承UUIDPrimaryKeyMixin/TimestampMixin。以下名字是与Codex服务约定，不自行改名：

- analysis_task_id UUID非空FK analysis_tasks.id ON DELETE RESTRICT；created_by UUID非空FK users.id ON DELETE RESTRICT；run_token UUID非空；step String(64)非空；physical_sequence Integer非空>0，unique(run_token,physical_sequence)。
- provider String(64)、model String(100)非空；state String(32)非空默认not_sent，CHECK仅not_sent/in_flight/received_unbooked/booked/usage_unknown。
- sending_day Date可空；estimated_input_tokens与max_output_tokens Integer非空>=0。
- usage_input_tokens/usage_output_tokens/usage_cache_hit_tokens/latency_ms Integer可空、非空值>=0；usage_raw JSON非空默认dict；response_digest String(64)可空。
- send_intent_at/receipt_at/booked_at/ended_at DateTime(timezone=True)可空；reason String(100)可空。not_sent已结束仍保持state=not_sent，以ended_at/reason说明明确未发，不新增取消状态。
- AiUsageLog新增attempt_id UUID可空，命名FK fk_ai_usage_logs_attempt_id →ai_request_attempts.id ON DELETE RESTRICT；唯一索引uq_ai_usage_logs_attempt_id（NULL允许多行）。原run_token/request_seq唯一索引与全部旧列值保留。

0016接0015，保持跨SQLite/PG迁移兼容，不新建数据库Enum类型。downgrade前必须检查未结清事实：除booked与not_sent且ended_at非空外，任何attempt都安全拒绝回退，不能删除unknown/in_flight/received_unbooked。允许回退时先移除新ledger FK/索引/列，再删attempt表；旧ledger全部原有列值/hash一致。

## 实施与交棒

直接先落盘schema/迁移红测试，再模型/迁移实现；不要重新全文件调查。测试覆盖字段/唯一键/非负约束/旧NULL行兼容、真实SQLite和专属PG升降级、未结清回退拒绝、旧账目所有原列完整hash前后不变。PG测试先验证目标cp_test schema存在/current_schema匹配，禁止回落public；仅清理本测试自己创建的schema。不得运行新provider/service或调用真实模型。

保存命令/完整原始输出/退出码/hash/自审、失败原文；一屏交棒后停止所有文件与fixture写入，供Codex集成/独立复核。此阶段完成只说明模型/迁移就绪，不代表核验链或goal完成。当前个人周剩34%，不自行切个人套餐。
