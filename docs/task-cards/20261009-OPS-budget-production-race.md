# 传智杯22：两条生产链共用日最后槽并发整合

基线96e02de，生产f14af62。BigModel个人GLM-5.3/最高，复杂事务测试；每周总消费最多70%且保留30%，不是新增70%。任务范围仍属当前OPS目标，不另宣称全站完成。

## 唯一文件所有权

ZCode唯一写新backend/app/tests/test_ai_budget_production_race.py与docs/evidence/20261009-OPS-production-race/。不改任何生产源码、现有fixture/测试/正式清单；如缺陷需修改生产，先用失败证据交棒Codex裁决。Codex不同时写该新文件或跑数据库测试，只读审查。

## 实际验收标准

- 先核对真实角色前提：verification.created_by是企业请求人，matching.created_by是学生；_authorized要求ENTERPRISE，_authorize_matching_inputs要求STUDENT，同一User只有一个role。因此同owner跨这两个真实入口在当前授权下不可构造，禁止改role/owner/绕过授权。应保留反例记录，并分别在匹配/核验生产入口构造同owner两个不同任务竞争最后槽，另证不同角色owner预算隔离，结合共享内核现有同owner跨chain专属PG竞争证据。原企业投递snapshot完整摘要不变；真实业务execute入口，不直接调用reserve代替。
- 每种生产链分别同owner日报告上限1，先准备两个不同pending任务；用独立session进入同链实际入口。不同角色两链各自owner预算上限不能相互混占。在实际AttemptService.prepare_for_send进入原函数之前设置两方到达barrier；原函数内部_live_identity会锁同owner User，故不得在reserve前设置双方barrier，否则会因第一方持User锁、第二方尚未进入而人为死锁。保持原事务及锁原样，不commit或跳过_live_identity来迁就测试。不能mock预算准入结果或顺序跑两链。特别禁止等胜方prepared/commit后才放行败方；须在胜方commit前两个原prepare均已创建独立session，可在_live_identity原调用前登记败方session、胜方取得原锁后等待败方到达，再继续原reserve/commit，保留真实锁等待。
- 两种生产链分别覆盖：matching同owner双任务/verification同owner双任务，落两边实际准备准入竞争；胜方MockTransport阻塞不返回，败方已到达且完成拒绝后检查。仅1份held、1个in_flight、1个实际HTTP，另一个daily_report_limit/规则降级须0外发、无预留；拒绝不消除胜方held。记录两session身份与事件时间，不以sleep推断竞争。
- PostgreSQL HTTP阻塞期间，以第三个独立session对User、Task、AiDailyBudget实际FOR UPDATE NOWAIT，证明不跨HTTP持锁；随后返回可信usage，容量actual仅一次、ledger仅一次，原快照未变。有限timeout，finally释放事件并收回自有协程，不杀服务。
- SQLite只能验证fixture准备/单链契约或收集，不能证明PG并发锁；PG案例必须显式skip无CAREERPROOF_TEST_DATABASE_URL。今日Docker不可用，禁止自动恢复/启动/安装或改.env、业务库。可写准备辅助回归与collect-only/Ruff，实际PG未跑明确登记，不声称通过。
- 只用现有本地MockTransport及随机cp_test schema、创建/seed前namespace检查，保留所有失败日志；不创建默认public表，不调用真实DeepSeek，不发消息/推送/提交/P2 stash/依赖安装。

先按索引读取上述helper及services/analysis、application_verification、ai_budget的必要函数，避免重读全仓。每项自审，交付命令/退出码/原始日志和hash，一屏回报后停止写入；Codex独立复验与提交。来源：[原目标审计](../evidence/20261007-OPS-01C-codex/goal-requirements-audit-20261009.md)、[预算复验卡](20261008-OPS-01C-budget-codex-review.md)。

## Codex角色可达性修正

此前预算复验卡的“同owner核验和匹配实际并发”前提与现行单角色授权冲突；同User无法同时满足STUDENT与ENTERPRISE。必须明确此不可达性与负向角色测试，不修改业务授权或伪造owner。同owner锁竞争在两个生产入口分别证明，共享内核跨chain用现有测试独立证明；这两层结论分开记录，不冒称同owner双角色真实流程存在。
