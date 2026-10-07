# 共用预算数据层检查点（非预算功能签收）

2026-10-08。由于ZCode窗口人工切换，传智杯20预算委派仍未发送；本批由Codex唯一写入模型、注册、0017与迁移测试。下轮需以本批真实HEAD和已有diff接续，不能要求ZCode重建或覆盖已验证部分。

新增AiDailyBudget、AiBudgetReservation、AiBudgetAdjustment和持久AiBudgetCutover。owner/day及attempt/operation唯一键；未知占额与可信实际用量字段分离，状态与实际/调整字段互相约束；空白审计理由拒绝，默认闸门禁用。有数据的0017回退一律拒绝，包含已结清容量和闸门证据，不静默丢失审计事实。没有业务迁移、闸门启用或外部调用。

实际命令与范围：

- `pytest app/tests/test_ai_shared_budget_migration.py -q --tb=short -p no:cacheprovider --basetemp=.tmp-budget-schema-review`：10项SQLite通过，原始budget-schema-sqlite.raw.out。后续新增PG用例。
- 同文件、显式本机CAREERPROOF_TEST_DATABASE_URL及随机自有cp_test：11通过零跳过，budget-schema-pg.raw.out；其中10为SQLite约束用例，1为专属PG迁移/唯一约束/未知占额回退保护，不能声称11项都在PG执行。PG seed前逐表namespace验证。
- `python -u ../docs/evidence/20261007-OPS-01C-codex/verify_budget_chain.py`：真实Alembic env.py base..0017，空预算0017→0016→0017，随后持久day容量使回退拒绝；版本仍0017、容量行仍1。旧账目原列SHA256始终78189d132f012a748af7fa3e8eab876cc370c5f491cd2a7eddef27051ad76a4e，合成旧报告/投递/成长行不变；自有schema清理通过。原始budget-full-chain-pg.raw.out。
- 最终Ruff检查模型、注册、新测试、0017及验证脚本通过。运行记录中生成迁移的初始格式/逗号错误已修复，未将这些失败解释为功能通过。

本批只证明DDL与迁移。没有BudgetService、跨链准入、wire grant、午夜转移、旧attempt接续、人工调整授权或两链预算后真实硬停证据；不能以表存在或enabled字段可写证明授权/预算正确。激活前仍需服务端完整清单、严格接续与管理员核验，业务闸门保持未切换。后续实施完整协议和独立验收卡，再做依赖公告审计及升级排序。
