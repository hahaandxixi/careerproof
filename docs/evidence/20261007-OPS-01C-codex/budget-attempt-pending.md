# 2026-10-09 attempt/observer 接入现场（未签收）

HEAD仍为1e14b6d。Codex未提交改动：ai_request_attempts.py增加可选SharedBudgetService、prepare_for_send返回同一事务的批准值、observer将该值写入实际max_tokens；intent重新校验日与授权，receive原子结清预算，book/close/unknown/reconcile使用day→attempt→reservation→ledger。恢复先锁全部日期再处理physical_sequence，避免序号不等于日顺序导致反向锁。外部两链构造器尚未接入预算，旧聚合审计/管理员激活/调整授权与预算后硬停仍待办。

新增test_ai_budget_attempt_integration.py直接运行实际provider._completion，全部MockTransport/专属夹具。首次SQLite4通过；随后新增可信503可释放多余上界再重试，同一原请求max_tokens从300降到293，两份可信账目24/14，恢复2/0。

最终SQLite新增5+attempt内核12+容量14：28通过、3真实PG锁跳过（budget-attempt-sqlite2.raw.out）。其中跳过为内核两项并发和容量一项PG并发。Ruff两处通过。未用这些数字冒称两链端到端完成。

PG首轮budget-attempt-pg.raw.out为6通过/33初始化错误：本机Docker Linux engine pipe不存在，连接尚未建立，没有执行合成seed。不能把基础设施失败声称代码失败或PG绿灯。以前的PG14不证明新attempt源码。本轮代码暂未提交，等PG与内核风险检查后形成可验证批次。

用户此前授权启动已有Docker Desktop；已实际执行`docker desktop start`，未重复启动或重置。当前尚活CLI handles：79334=start，89484=docker ps，66687=docker desktop status；最后均空输出/running。下轮先poll这些确切handle，观察超时不等于终止，不能重启任务。Docker后台/桌面进程已出现，但这不是引擎健康证据；数据库健康后用新日志重跑PG，保留失败原文。没有新建任务20或向其他软考任务发送项目文字。

原用户docs/当前接力.md的一条空白行保留；不reset/clean、不应用P2、不升级业务库/closure、不外发真实数据、不真实模型、不推送或部署。完整OPS目标保持进行中。
