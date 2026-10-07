# OPS-01C 共用日预算：实现协议与交棒条件

2026-10-07。这是Codex在传智杯19主匹配接入期间准备的下一批协议，不是预算代码已完成，也不是新ZCode任务已发送。先签收19的完整物理请求接入，再按现场HEAD确定下一任务序号和唯一写入者。依据：[设计门槛](20261007-OPS-01C-main-budget-design.md)、核验链签收37133e5、主匹配实施卡。本卡不授权业务库迁移、真实模型、部署或推送。

## Codex确定的容量模型

日容量采用服务端Asia/Shanghai日，不相信客户端日期。已知消费与未知预留分开存储/展示；预算占用 = 可信实际消费 + 尚未结清上界 + 经审计保留的旧模式未知占额。缓存命中输入仍计入输入token，不因便宜或缓存命中就忽略。账目是可信事实，预留是准入上界，二者不能重复加总。

- 新模型`AiDailyBudget`：owner/day唯一行，仅用于短事务串行化及策略版本，不把内存锁作为跨worker保证。首次创建使用数据库唯一键/冲突忽略，再读排他锁。容量上限取服务端当前设置，展示同一快照；若配置降低到低于已有占用，禁止新准入，不回写或删除事实。
- 新模型`AiBudgetReservation`：每个physical attempt唯一一行，固定owner/task/run；保存reservation_day、input_bound、output_bound、状态（held/settled/released/adjusted）、可信结清input/output及时间。held按上界计，settled按真实值计，确定not_sent的released计0。字段/check/唯一键禁止负值、重复attempt和结清伪零；真实零收据仍允许。新表不存业务请求正文或密钥。
- 新模型`AiBudgetAdjustment`：人工处理未知预留的不可覆盖记录，包含操作id（幂等键）、真实操作者、owner/attempt、原因、处理前后占额、时间。调整只改变容量政策，不生成usage收据、不把usage_unknown改booked。没有调整许可的自动恢复器不能执行它。
- 新迁移预计0017，最终revision以现场Alembic head为准。注册模型、约束/索引及SQLite兼容；不改0016、不重写`AiUsageLog`历史列或旧业务行。downgrade有新增预算数据时必须有显式保护，不静默丢失未知占额或审计记录；隔离空数据往返与保留数据拒绝均须测试。

容量统计优先查询持久行而不是维护易漂移的重复累计计数。持有day锁时聚合同owner/day预留；现代attempt已有reservation只计它，不再加相同attempt的ledger。旧聚合ledger为`attempt_id IS NULL`，按既有created_at换算本地日，记录旧归属政策，不能追改旧行。0016已经存在、但尚无reservation的现代attempt不可被这条过滤遗漏：启用前按下文建立有来源的预留接续；接续不完整时闸门关闭，不能用空表统计放行。报告次数按task/day的集合并集去重（有效预留或已经发送/结清 + 当日legacy账目），同任务的规划/修正/retry不各算一份报告；确定全未发送并释放后可归还该日槽。同任务跨run累计已知和未知占用也计入报告token上限，不能重试重置报告预算。

## 准入、发送与结清接口

1. 两链都通过`DurableRequestObserver`进入同一预算服务；不得在外层各自读一次旧_daily_ai_budget就认定安全。给`AttemptService`增加预算协作者，所有prepare/intent/receive/book/close/reconcile走相同政策。关闭共用预算的离线兼容路径须显式，不让外部真实provider悄悄绕过。旧preflight可作显示提示，但持久准入才是最终判定。
2. 首次prepare短事务：复核User/Task claim与服务端绑定，锁当日日容量，核对旧模式切换闸门，计算同task全部run的已知/未知占用，原子创建not_sent attempt + held预留。失败整体回滚，0HTTP。采用当前observer的UTF8完整请求长度+1024作为input保守估计；它与provider的JSON字符估计不是同一口径，不伪称一致。输入超过剩额必须拒绝并给可解释原因，不盲目截断证据。
3. 输出准入采用`min(请求max_tokens, 报告剩余输出容量, 当日剩余输出容量)`；至少1，否则拒绝。把批准的max_tokens同时保存到attempt/预留并写入即将发送的请求，让wire上限确实不高于预留。prepare需给observer返回实际批准值；不通过另一次不加锁的查询猜grant。只减小输出上限，不增加调用者上限；持久准入异常不触发provider物理重试。最大输出提前裁剪避免规划已消费后所有分析都被机械拒绝，但仍保留输出截断降级语义。
4. mark_intent重新核对新鲜授权/claim/岗位材料固定输入，获得日锁后再锁attempt/预留。若仍在原日，验证原held未释放/调整，提交in_flight与send_intent_at/sending_day。如果已过午夜，按日期升序锁两天容量，把确定未发送的held转到新日，重新核对新日容量/报告槽；新日不够就关闭not_sent并归还旧日预留，0HTTP。午夜转移不扩大原grant；拒绝后不能保留可发送attempt。提交成功才允许HTTP。
5. receive在原sending_day下原子保存可信收据和结清预留，不能等业务报告提交。真实用量超过上界仍照实保留/结清并标偏差，当日或报告已超额时停止后续准入；不能拒记消费来维持表面预算。无效或缺失usage保存unknown，继续held。响应已到但收据事务失败仍保守held，禁止因此重发HTTP。
6. book_one同一原日日锁下校验收据、原子写唯一ledger和booked；已经settled不重复扣容量，不退两次差额。received_unbooked只按真实值占用，账目commit失败不复原为全额held。reconcile只修持久状态/可信账目，永不调用provider、恢复报告或制造收据。
7. 取消、撤回、材料授权失效及租约丢失不抹掉费用。确定not_sent可以release；有意图无可信收据必须held/unknown。慢活claim不能按TTL抢判，更不能自动退额。late可信收据按原日结清，哪怕已人工adjusted也不得重复退额或改历史provider事实；要明确留下实际消费与原调整差异。

## 锁序与旧模式切换

统一锁序：需要授权时User/Task/对应业务授权行 → 日期升序的day容量 → attempt → reservation → ledger。收据/恢复不锁活跃User也须遵守day在attempt之前。不能先调用当前`_locked_attempt`再倒过来锁day。跨日变动先读不加锁的归属，取得全部相关日期锁后复读身份和日期；若已变，释放并重试有限次数，不在错误day锁下写事实。核验`authorize`可能锁Application，应在day/attempt之前；业务终结不能持Task锁再等待一个反向持day锁并需Task的恢复器。

启用闸门不得假定新表空等于已消费0。保留旧账目实际统计；对启用前没有持久attempt的活跃外部run先禁止新外部准入，排空并人工核对。终态旧run仍可能没有可信账目，不能仅凭FAILED/COMPLETED或run_token清空就认定无消费。隔离验收须建立切换清单与审计决议；未知旧run保守占额或保持闸门关闭，绝不伪造物理attempt/收据。

已有0016现代attempt另作严格接续：reservation记录来源`pre_budget_attempt`，身份从原attempt读取，原attempt/ledger哈希不变。可信received_unbooked/booked重新严格校验原持久usage_raw与计数字段，以原sending_day建立settled，不因尚无ledger漏算，也不因已有ledger重复计费；in_flight/usage_unknown按原sending_day和原input/max_output上界建立held，不能按恢复日或TTL退掉。没有意图且确定未发送的not_sent按创建日保守接续held，终态无意图可由现有关闭逻辑释放，活claim不能擅自关闭。缺失意图日期、身份不一致或收据校验失败须阻止启用并留审计缺口，不能悄悄跳过。先完成全范围清单和接续，再在短锁下切换启用标志；每个worker/send检查同一持久闸门，不用进程内bool。一旦启用，发现任何应接续而缺预留的attempt即拒绝新发送并交恢复器核对，不将漏行解释成0消费。只在专属夹具模拟闸门启用；业务库现场闸门保持未切换，不自行迁移或处理既有用户记录。

## 下一批文件所有权

发送前先核对19已终态并停止写入，记录其提交HEAD。下一位ZCode唯一写：新`models/ai_budget.py`及注册、0017迁移、`services/ai_request_attempts.py`、新`services/ai_budget.py`、两链必要接入文件、provider observer grant传递、对应新预算测试和独立迁移探针、当轮原始证据目录。`analysis.py`等必须等19交棒后才转所有权，不并行改同一文件或数据库夹具。

Codex负责本卡协议、最终安全diff全文审查、跨链并发/午夜/unknown独立复验和本地提交；ZCode负责实现、目标+受影响首跑、首次真实硬停、迁移证据、自审与一屏交棒。新序号和模型现场确定，复杂度可用有额度的免费GLM-5.3或免费Flash/最高；符合授权才提前个人GLM-5.3，并保留周额度至少30%。代码未通过不得提前更新“完成”。

## 必须有的验收矩阵

| 场景 | 必须证明的结果 |
| --- | --- |
| 核验+匹配不同task、同owner、并发最后一个报告槽 | 专属PG真实并发，一方获准另一方0HTTP；事务外HTTP，User/Task锁可NOWAIT |
| 同task规划/分析/repair/503物理retry | 每次独立hold，序号不重用；报告槽一次，累计容量覆盖全部步骤及错误响应可信usage |
| unknown后retry | 未知上界不释放；不足容量的下一attempt拒绝0额外HTTP，展示未知原因而非0真实费用 |
| 同一预留/收据/book/recovery多次与并发 | 一份容量、一份可信账目、差額只释放一次，6并发结清无超放 |
| prepare与intent跨午夜，新日够/不够 | 原日原子转新日或拒绝0HTTP；锁按日期顺序；新日够时wire不超原grant |
| 午夜后的迟到可信收据/重启恢复 | 原sending_day真实结清，不使用ledger恢复日重新计费，旧日和新日统计无双计 |
| 实际usage超过预留 | 照实结清/入账，标偏差并停止后续准入，不吞掉超过部分 |
| 收据或账目commit失败 | 前者held/unknown可追查，后者可信received_unbooked可恢复1/0，均0额外HTTP |
| 撤回/owner停用/材料失效/旧run | 未发送0HTTP并释放；已发送费用独立保留，旧run无报告复活 |
| unknown人工调整、重复操作、无权操作者 | ADMIN活跃身份新鲜复核+审计理由；幂等操作一次，未授权无修改，usage事实仍unknown |
| 切换旧账目/活跃与终态未知旧run | 原hash不变、已用容量不归零；未完成审计闸门不放行；不捏造旧attempt |
| 已有0016 attempt但没有预算行 | 可信有/无ledger均按原日实际计一次，unknown按原日保守held；接续失败闸门拒绝，原attempt/ledger hash不变 |
| 两链真实子进程四窗口硬停 | 发送意图/响应未持久/收据已持久/账目已提交：保留/结清与恢复次数正确，HTTP计数不增长 |
| Alembic完整链与往返 | base到当前head、空预算回退再升级；存在未知或审计数据拒绝破坏性回退，旧原列和业务行hash不变 |

全部仅MockTransport和随机自有cp_test，逐表namespace校验先于seed，create_all(checkfirst=False)，清理只触及自有schema/已验证自有child。失败日志独立保留，原始命令/输出/退出码及未验证项明确。最终仍要当前依赖/权威公告审计和升级排序；career_planning/visual_evidence/job_drafting等未接入链独立列出，不将两链预算称为全站已经统一。
