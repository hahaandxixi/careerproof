# 传智杯19：主匹配所有物理请求接入持久账目

2026-10-07。基线37133e5。OPS-01B核验链已阶段签收，见Codex verification-stage-signoff.md。本卡是完整目标第二阶段的第一实施批；共有日预留/跨午夜和依赖审计仍必须随后完成。

## 现场及唯一所有权

你唯一写：backend/app/agents/evidence_workflow.py、backend/app/services/analysis.py、backend/app/services/report_history.py；新backend/app/tests/test_durable_matching.py，现有test_real_matching.py/test_report_history.py/test_ai_evidence_workflow.py/test_report_input_budget.py仅受影响必要回归；docs/evidence/20261007-OPS-01C-main/。你唯一写本轮自有cp_test夹具。Codex只读复核和协议文档，不同时跑数据库测试、不改你的文件。其他provider/attempt service/模型/0016/核验链/P2 stash全部冻结，禁止改动。需要额外文件先报告。

## 确定接口与链路

1. run_evidence_workflow增加可选durable_observer_factory(provider, step)关键字；未传参的离线/旧调用保持原API。规划每轮、分析、修正调用前给OpenAICompatibleProvider设置相应observer（step如planning_1/analysis/repair），其内部每次物理重试已会prepare/mark_intent/receive。不要只在成功次数或最终分析时记账。
2. execute_match_task持有由服务端绑定的taskId/creator/run_token/provider/model；factory使用现有AttemptContext/AttemptService/DurableRequestObserver，不改它们接口。同一run跨step所有physical_sequence共享。仅实际安装外部provider observer时视为durable模式；rules/mock/未调用provider的兼容路径不能凭配置名伪造attempt。
3. 每次发送前authorize callback新鲜复核owner活跃/学生角色、材料版本仍属本人且与任务固定materials snapshot一致、任务固定岗位/材料/同意字段未被替换。配合AttemptService已有claim/token/consent检查，不把路由授权当永久有效；旧run最终仍finish_task CAS，不发布报告。
4. HTTP前必须释放主session及授权事务。当前update_task_progress自身commit已验证；不能把它笼统视作持锁函数。历史loader实际每次读取MatchItem会重新开启借用session事务，改为短独立session或可靠在返回时释放，不依赖下一进度文字恰好提交。历史同owner/岗位/提交前固定report边界、历史不是当前证据仍保留。
5. 外部工作流结束、fallback、解析/校验失败、取消、租约丢失、保存报告失败时均从durable收据结清；仿核验链bounded/shield独立book逻辑，不能和业务finish/report事务同提交。不要跨模块引入verification→analysis循环import。若book失败保留received_unbooked并记录可恢复缺口，不重发HTTP、不覆盖可信事实。
6. 新mode报告usage/usageKnown/usageBooked/attemptSummary来自持久summary（未知时零可信收据不展示伪零总量，有可信部分只作partial），planning+analysis+repair+重试均包含。新mode绝对停止analysis.py原finalize聚合AiUsageLog写入；旧模式明确保留旧路径且不改历史行。报告旧规则/评分/引用/材料支持度不因记账改变。

## 测试与证据

- 先最小红测试再实现；合成DeepSeekProvider+MockTransport，规划→分析→一次定向修正；429/503→成功的物理重试，断言每个physical attempt身份/step及可信账目一次。HTTP error有可信usage也照实记；无usage的失败retry保持unknown且不双记。
- fallback/JSON或引用校验失败仍结清已持久收据；账目commit失败恢复0额外HTTP；lease/reap之后可记旧run费用但无新报告；并发重复book、owner停用/材料授权失效0发送。
- 报告保存失败不得丢账。新模式原聚合路径断言零新增；legacy模型/工作流测试兼容及旧ledger hash不变。历史loader在HTTP阻塞时无借用session事务（PG backend事务/锁探针），不删除授权检查来让旧fixture过。
- 受影响目标：新durable_matching、real_matching、ai_evidence_workflow、report_input_budget、report_history/persisted_history；先目标/受影响，阶段再全后端。PG仅随机自有cp_test schema，create_all(checkfirst=False)，写入前核对current_schema和每张被使用表namespace，结束仅清理自有schema。
- 每次失败单独.raw.out不覆盖；保存命令/退出码/完整输出/hash/自审/未验证项，一屏终态交棒后停止写入。Codex随后全文风险审查并独立复跑最高风险项。

本卡使用现场可用的Start Plan免费Flash/最高；用户2026-10-07明确允许免费模型在有助效率时开最高，本批属于复杂实现。默认模型顺序仍为免费GLM-5.3→免费Flash→个人GLM-5.3，发送前核对组别，不能把最高等同于个人套餐或效率必然提升。只读本卡与所需源码，直接落测试，避免全仓重复调研。不得自行切个人套餐；禁止真实模型/外发/.env/业务库/closure/public服务重启/Git提交推送/依赖安装/历史清理。共用预算预留尚未实施，不能把本批通过称为两链统一日预算已完成。
