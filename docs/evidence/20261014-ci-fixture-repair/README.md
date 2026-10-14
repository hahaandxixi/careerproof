# 干净夹具复现修正（2026-10-14）

推进G4/G5，仅修改四个测试文件，产品预算、解析器、数据库迁移和演示数据不变。独立快照基于dc5cfb9的backend、demo合成资源及已入库评测JSON，再覆盖四个夹具改动；不带本机.env或未提交的guard/launcher。配置APP_ENV=test、AI_PROVIDER=mock、AI_EXTERNAL_ENABLED=false，未调用真实模型。

## 已定位与修正

- matching_db/durable_db在PostgreSQL下漏建knowledge_chunks，但上传解析会写入该表。PG改为创建并逐表核对全部模型表属于专属cp_test schema；SQLite仍不创建向量表。
- knowledge_db遗漏材料版本外键引用的analysis_tasks，现补齐并逐表核对namespace。离线元数据检查外键依赖闭合；不是实际PG执行。
- 撤回重投迁移测试改为显式导入attempt_pg，避免整批收集时隐式插件夹具不可见。完整收集1243项可正确解析；第一次快照未包含demo资源的收集失败也保留。
- durable_db明确设置合成重试/修正流程的40000输入预算，与已有硬停夹具一致；各预算用例仍可覆盖自己的限额。初次失败的内存观察确认BudgetAdmissionError(report_input_token_limit)，不是未发送就伪称已调用。产品默认12000不改。

## 验证

- Ruff四文件通过。
- 首轮SQLite：3通过、1失败、1跳过；[原始记录](sqlite.raw.out)及[JUnit](sqlite.xml)。失败为合成请求被默认输入预算拦截；[诊断](durable-diagnosis.raw.out)内部测试仍失败，不能将观察脚本的进程退出码当作测试通过。
- 修正后关联四模块：26通过、2跳过（需PG），[原始记录](sqlite-final.raw.out)、[JUnit](sqlite-final.xml)。覆盖真实MockTransport发送/收据、重试/修正、取消/保存失败/恢复及预算边界；不是静态自查。
- 完整收集与依赖闭合：[收集](collection-with-demo.raw.out)、[元数据](schema-closure.raw.out)。历史失败输出不覆盖。
- 完整SQLite首跑：1179通过、5失败、10错误、49跳过；[原始日志](unit-full.raw.out)、[JUnit](unit-full.xml)。本轮准备快照漏带了已入库的docs/evidence/20261010-AI-blind-plan-review/review.json，15项问题均在读取此资源时发生；不归咎于产品，也不把这轮写成全量通过。
- 补齐该Git资源后，只复跑两个受影响评测模块，38通过、零失败/跳过；[日志](review-recheck.raw.out)、[JUnit](review-recheck.xml)。完整回归未再次重跑；不能把合并数字冒充一次全量绿灯。

## 未完成

Docker Linux Engine当前不可用，未为用户手动测试擅自启动Docker或重启服务；专属PG验证待恢复。旧CI草案本身还需补专属库vector扩展初始化，不能把本批夹具或SQLite通过冒充PG/远端CI通过。未降低门禁、跳过失败或使用业务库验证。
