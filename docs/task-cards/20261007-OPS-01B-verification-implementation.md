# 传智杯16：OPS-01B 核验链持久请求实现

2026-10-07。设计基线main@ec6e7a2。PRODUCT-01已签收，当前仅用户空白行改动及历史未跟踪文件，P2 stash保持暂停。本卡是完整OPS目标的第一实施阶段；不以核验链完成代替主匹配、日预算或依赖审计。读原OPS-01B准备卡和调查复核，再按本卡实施。

## 现行证据与目标

provider.py `_completion`在client.post内发起物理请求，`_capture_usage`成功响应后才增加request_seq；verification的persist_verification_usage虽然独立事务+唯一索引，但来源usage_records仅内存。必须为每次物理HTTP尝试持久保存身份/发送意图/可信收据，并提供只基于持久数据、不重发HTTP的幂等对账恢复。硬停后没有收据则unknown，不能承诺精确消费。

## 协议裁决（Codex）

1. 新模型AiRequestAttempt及0016（接0015），分析任务、创建者、claim run_token、step标识、独立attempt_id、物理sequence绑定；unique(run_token,physical_sequence)。sequence在发送前分配，重试429/5xx/timeout也各有身份，不用成功响应序号。不得更改/重编号历史AiUsageLog；新增可空唯一attempt_id关联供新路径使用，保留旧run_token/request_seq约束。避免级联删除attempt/账目丢失；迁移兼容旧NULL行，升降级旧账目完整hash保持。
2. 状态：not_sent（持久身份，尚未提交发送意图）、in_flight（短事务提交发送意图后，可能发送）、received_unbooked（可信usage已持久）、booked（可信账目与状态同事务）、usage_unknown（无可用可信收据，含原因）。已明确未发出的not_sent拒绝/取消须有可查询结束原因，不可混称unknown。实际HTTP与发送意图之间不可消除窗口如实标可能发送；TTL不能自动当0或抹掉可能消费。
3. 保存发送日Asia/Shanghai、估算input上界与输出max_tokens、provider/model及安全摘要，给后续日预算预留；本阶段不声称在途预算已解决。禁止保存请求业务正文、API key、HTTP授权头、完整响应业务内容。收据可保存严格过滤后的原始usage字段、响应标识摘要/响应时间；prompt/completion必须真实非负整数、拒绝bool/float/负数/缺项，合法0是可信0，缺项不是0。缓存字段存在时严格核对类型及<=prompt，不得放大或隐瞒可信消费。
4. 在OpenAICompatibleProvider物理client.post边界提供可选异步durable observer/hook。无observer的既有接口/usage展示行为兼容，不给Mock伪造外发账目。prepare/发送意图持久失败必须阻止HTTP，不能降级成内存路径继续发。每次物理重试重新授权准入；核验仍max_attempts=1，绝不增加默认重试。
5. 核验在请求前安装observer并固化新ledger模式。发送前独立短事务复核created_by、当前claim/run/授权/固定快照；User→任务/attempt锁序明确，HTTP期间不持用户/投递锁。既有撤回和终结新鲜授权检查保留。不能用旧run恢复结果；旧run已发生可信消费仍可入账。观察到响应后先持久可信usage，再允许业务JSON解析/校验；HTTP错误响应若确有可信usage同样记账。收据保存失败不返回成功结果，持久in_flight仍可查询为待调查事实。
6. 接入模式与对账：新增observer路径只从attempt收据生成AiUsageLog，旧persist_verification_usage在此模式不得再从provider.usage_records双计；未接入旧路径保留，不改既有主匹配聚合账目。事务内锁attempt→检查既有账目/插入唯一账目→更新booked→commit，重复/并发恢复只入账一次；既有冲突须核对归属/可信数值，不用DO NOTHING掩盖不一致。数据库失败回滚后仍received_unbooked，重试只写数据库，不HTTP重发。
7. 新增安全对账服务：可按task/run列出未结清状态与原因；只恢复可信received_unbooked，处理旧run也不触碰任务结果/投递。无收据in_flight仅在确定关联执行已结束/claim失效后标unknown，不能因并行活请求慢直接归未知。保留人工处理审计接口设计，后续预算阶段实现调整；此轮不自动释放未知占额、不新增对企业发送入口。

## 唯一写入者与允许范围

ZCode是下列实现/测试及专属cp_test夹具唯一写入者；Codex只读审查并写正式任务卡/清单，不改这些源码。允许：新backend/app/models/ai_request_attempt.py、services/ai_request_attempts.py（可加小的专属durable observer模块）；models/__init__.py注册；models/analysis.py仅新增AiUsageLog可空attempt_id关联；agents/provider.py仅通用可选hooks/复用可信usage解析；services/application_verification.py仅核验durable接入/模式分流；alembic/versions/0016_ai_request_attempts.py；新tests/test_ai_request_attempts*.py、新tests/ops_hard_stop_worker.py及现有test_b08_usage_accounting.py/三个provider测试的必要回归；docs/evidence/20261007-OPS-01B-verification/原始证据及专属临时目录。

禁止：修改主匹配services/analysis.py或其他AI业务接入、前端/正式清单/PRODUCT脚本、.env/业务库/closure/public、旧投递/报告/草稿、服务启动/重启、Git提交推送、真实模型或真实数据外发、依赖安装升级、P2 stash。不得清理历史文件。0016仅专属cp_test随机schema验证，本轮不升实际closure。

## 交付与故障门槛

先有意义红测试，最小实现，再目标/受影响回归、自审与证据。至少覆盖：物理重试号、发送前DB失败0HTTP、缺失/错误usage unknown、合法0、JSON解析/校验失败已有可信收据仍入账、取消/撤回/旧run不可恢复结果但可入账、并发幂等、账目commit失败恢复0额外HTTP、租约失效和慢活请求区别、旧路径兼容且不双计、升级/回退旧账目hash。

必须真实独立子进程+mock提供商+专属PG四窗口硬停（不是仅抛异常/取消协程）：发送意图commit后至HTTP前；HTTP返回后至收据commit前；收据commit后至账目commit前；账目commit后至任务终结前。父进程持有child句柄，PID/创建时间/随机nonce/专属fixture全核对后才能Stop/kill；禁止杀服务或其他进程。每窗记录已发送HTTP计数、持久行/状态、恢复前后ledger数/可信值、任务结果不复活。unknown窗口保持unknown，可信窗口恢复一次，恢复不重发HTTP。若实现限制使某窗口无法可靠控制，报告具体缺口而不是换成更容易的mock断言。

源码hash、命令/完整原始输出/退出码、PG schema身份及清理仅专属schema、四窗安全身份和数据断言、自审发现进入证据文件；一屏交棒。工具可用时用review-agent只读自审。失败原文保留，不改预期掩盖产品错误。完成后停止写入，Codex独立复跑最高风险1–2项及安全diff审查、验证后本地提交。此阶段未签收前不让另一任务改同源码或共享数据库。

## Codex追加边界复核（同日，仍同一实现范围）

- usageKnown在durable模式必须来自持久attempt的可信收据覆盖情况，不继续仅all(provider.usage_records.usage_present)。例如cache>prompt的新严格收据判未知，而旧_capture_usage只校验prompt/completion，会误显示已知；物理失败重试也不能因成功响应列表缺失该次而冒充全数已知。known partial与booked不同，查询/展示如实区分，新增针对此差异的回归。
- test_b08_usage_accounting原stalled_authorized把任何lock=True当响应后检查。新增发送前短锁复查会使这个注入错误地卡住第一次HTTP。按真实阶段（如handler已确实应答的事实）适配测试，不为了旧fixture把发送前授权锁或终结复查删除。
- 本进程明确观察到某次物理HTTP尝试异常结束后，可按该attempt身份持久unknown原因；另一对账进程只看到慢活任务的in_flight不能据TTL抢判未知。区分物理attempt结束与整个父task仍活跃，后续重试独立身份，不共用未知收据。

- 锁语义勘误：本机with_for_update(key_share=True)、read=False实际渲染FOR NO KEY UPDATE，见Codex lock-clause-compile.raw.json，不是共享KEY SHARE。发送前User短锁保留NO KEY UPDATE，避免用更强FOR UPDATE与撤回→通知User FK KEY SHARE形成循环；AnalysisTask身份短锁也优先NO KEY UPDATE，与新账目FK检查兼容，仍对claim状态更新互斥。Application授权锁仍新鲜串行且在HTTP前提交释放。必须实际PG验证撤回与准入/账目并发，不靠参数名或文档断言冒充通过。

## 2026-10-07 当前执行归属覆盖

原传智杯16已停止且未写源码。原整体范围与四硬停门槛继续有效；文件所有权以[模型迁移交接卡](20261007-OPS-01B-schema-handoff.md)为准：ZCode17仅模型、0016、两schema/迁移测试及证据；Codex持有receipts/provider/attempt service/核验接入及各自测试。数据库fixture当前仅17写，正式交棒后再独立复验。provider相关74项离线Mock已通过c8286ab；这不等于数据库事务或硬停验收通过。
