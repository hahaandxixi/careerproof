# 传智杯22：两条生产链共用日最后槽并发整合

基线96e02de，生产f14af62。BigModel个人GLM-5.3/最高，复杂事务测试；每周总消费最多70%且保留30%，不是新增70%。任务范围仍属当前OPS目标，不另宣称全站完成。

## 唯一文件所有权

ZCode唯一写新backend/app/tests/test_ai_budget_production_race.py与docs/evidence/20261009-OPS-production-race/。不改任何生产源码、现有fixture/测试/正式清单；如缺陷需修改生产，先用失败证据交棒Codex裁决。Codex不同时写该新文件或跑数据库测试，只读审查。

## 实际验收标准

- 复用test_application_verification.case、test_attempt_hard_stop.prepare_chain_task构造同一个学生owner的核验任务与新材料匹配任务。原企业投递snapshot完整摘要不变；真实业务execute入口，不直接调用reserve代替。
- 同owner日报告上限1，先准备两个pending任务；用独立session从两条生产入口进入。仅在实际预算reserve调用前设置两方到达barrier，必须先释放入口预检的User/Task锁，不在持锁阶段设barrier导致人工死锁。不能mock预算准入结果或顺序跑两链。
- 两种可控胜方均覆盖：matching先/verification先，落两边实际准备准入竞争；胜方MockTransport阻塞不返回，败方已到达且完成拒绝后检查。仅1份held、1个in_flight、1个实际HTTP，另一个daily_report_limit/规则降级须0外发、无预留；拒绝不消除胜方held。记录两session身份与事件时间，不以sleep推断竞争。
- PostgreSQL HTTP阻塞期间，以第三个独立session对User、Task、AiDailyBudget实际FOR UPDATE NOWAIT，证明不跨HTTP持锁；随后返回可信usage，容量actual仅一次、ledger仅一次，原快照未变。有限timeout，finally释放事件并收回自有协程，不杀服务。
- SQLite只能验证fixture准备/单链契约或收集，不能证明PG并发锁；PG案例必须显式skip无CAREERPROOF_TEST_DATABASE_URL。今日Docker不可用，禁止自动恢复/启动/安装或改.env、业务库。可写准备辅助回归与collect-only/Ruff，实际PG未跑明确登记，不声称通过。
- 只用现有本地MockTransport及随机cp_test schema、创建/seed前namespace检查，保留所有失败日志；不创建默认public表，不调用真实DeepSeek，不发消息/推送/提交/P2 stash/依赖安装。

先按索引读取上述helper及services/analysis、application_verification、ai_budget的必要函数，避免重读全仓。每项自审，交付命令/退出码/原始日志和hash，一屏回报后停止写入；Codex独立复验与提交。来源：[原目标审计](../evidence/20261007-OPS-01C-codex/goal-requirements-audit-20261009.md)、[预算复验卡](20261008-OPS-01C-budget-codex-review.md)。
