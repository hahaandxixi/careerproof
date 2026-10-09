# 传智杯20：预算事务故障测试

实际 Git 根：`D:\jbcode\web ai\jianli`。用户最新授权直接用 BigModel 个人计划，复杂预算事务任务 GLM-5.3；每周总消费最多70%，保留至少30%。

## 唯一写入范围

- 新建 `backend/app/tests/test_ai_budget_fault_recovery.py`。
- 新建 `docs/evidence/20261009-OPS-budget-faults/` 中的原始命令、输出、结论与自审记录。
- 不修改现有测试、生产源码、模型、迁移、正式接力文档和硬停测试。发现实现缺陷时用失败测试与具体定位交棒，Codex决定修复。

## 工作与验收

1. 先报告嵌套仓库 HEAD、分支和 status；保留全部已有修改。只读本卡、预算接入服务及相关测试，不重新全仓调查。
2. 复用 `test_ai_budget_attempt_integration.py` 的真实 provider + MockTransport + 独立 `budget_data` 夹具。先检查夹具如何防止public落库。不调用真实模型。
3. 补三个有意义的故障边界：prepare持久事务提交失败时0 HTTP且attempt/预留均未落库；收据持久提交失败时不得伪造可信费用，既有intent/held仍能保守恢复unknown；可信收据已持久而账目book提交失败时恢复只入账一次、预算actual不丢失且不重发HTTP。
4. 注入真实SQLAlchemy事务提交边界，注明是在commit前失败还是提交结果不明。不要用单纯抛业务函数代替数据库边界，不把commit前注入声称为网络断连的歧义提交验证。
5. 先SQLite首跑，保存每次失败完整输出；再受影响目标测试及Ruff。使用新的项目内basetemp和 `-p no:cacheprovider`，不得删除旧临时目录。命令退出码单独记录，不能让输出管道吞掉失败。
6. 当前Docker故障，PG门槛未恢复。不得自行重启/修复Docker、操作业务库、运行迁移或清理进程。SQLite通过不能冒称PG/真实硬停通过；保留PG运行待办。
7. 自审断言确实检查可信收据、持久容量和恰好一次账目，不只断言异常。交棒限一屏：文件、命令/计数、失败是否仍在、语义限制、下一项。

禁止Git提交/推送/reset/clean、应用P2 stash、外部发送/真实模型、改.env/安装/部署。Codex当前仅写硬停准备与正式文档，不写你的新测试，也不同时跑数据库测试。完成后明确停止写入。
