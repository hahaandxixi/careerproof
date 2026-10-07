# 共用预算独立复验卡

主匹配阶段签收9b9080b；下一预算批以实际发送时HEAD为基线。实施协议见20261007-OPS-01C-shared-budget-implementation.md。本卡由Codex维护，ZCode不得把未跑场景写成通过。

## 文件所有权与启动条件

预算实施任务成功发送并核对后，ZCode唯一写协议卡列出的模型、注册、0017、预算服务、attempt服务、provider grant和两链接入、目标/受影响测试以及20261008-OPS-01C-budget证据。Codex只读这些文件，写正式清单和本卡；不得同时跑共享PG测试。独立风险测试只在交棒停止写入后增加。

UI人工切换后的新任务草稿不等于已委派，必须确认项目jbcode、真实嵌套Git根、任务编号20、模型组别、首个模型调用与写入范围。免费GLM-5.3未在当前菜单提供；免费Flash/最高可用，余额57%仅00:00现场。其他软考任务不属于网站写入者，不发送项目文字到它。

## Codex必须独立证明的反例

1. 同owner的核验与匹配实际并发，最后一个日报告槽：两个准备请求必须跨独立session，数据库锁保证只有一个获准，不是先后调用伪竞态。获准方HTTP期间User/Task/day锁可NOWAIT取得。
2. 输出剩额小于请求max_tokens：持久grant、reservation上界、实际MockTransport抓到的请求max_tokens三者相等。不得仅改预留数值；重试同样受新准入约束。
3. 午夜从23:59:59到00:00:01：通过服务端可注入时钟控制prepare和intent，断言两日占额逐项变化。新日不够必须0HTTP，旧日确定未发送占额释放；迟到收据回到原发送日，不落在恢复日。
4. 无usage的503确实HTTP已发生，未知上界继续占用并阻止超额retry。可信0收据允许真实0；未知记录不得填0、因TTL退出退额或恢复发送。
5. 既有0016有/无ledger的可信attempt、未知in_flight和活not_sent分别接续，统计不丢、不双计。缺失可信日期/身份、终态旧模式无收据：持久闸门拒绝准入，不能因Task终态放开。
6. 同一可信收据6个并发settle/book/reconcile：一份容量、一份ledger；收据commit失败保持上界，ledger commit失败保持真实已结清容量，恢复不增加HTTP。
7. 本人撤回/停用/材料失效或旧run：未发送释放且0HTTP；已发送独立结清且无报告复活。人工调整须新鲜ADMIN授权、幂等操作id与前后占额审计，未知usage事实不改known。
8. 两链分别真实子进程四窗口硬停，实际进程身份和HTTP计数留证。与协程Cancel、Mock raise、before_commit故障分别记录，不互相替代。

## 已核对的当前源码约束

现有AttemptService.prepare返回UUID；DurableRequestObserver尚未改wire max_tokens。预算实现必须提供可靠grant传递，不能调用完prepare后再独立读剩额猜grant。现有receive/book/mark_unknown/close/reconcile先锁attempt，新预算必须统一day→attempt而非直接嵌套反向锁。现有配置默认每报告input12000/output4000、每日reports20/input200000/output40000；测试可以覆盖配置，但生产上下界应由同一服务端配置快照计算。当前_daily_ai_budget只读已落ledger，不代表在途容量安全。

主匹配本轮14/21风险测试和既有92受影响检查只证明预算前源码。预算修改后需重新跑受影响范围，不能复用计数签收。完整OPS仍须最后当前依赖版本与权威公告审计、升级排序，未授权安装或部署。
