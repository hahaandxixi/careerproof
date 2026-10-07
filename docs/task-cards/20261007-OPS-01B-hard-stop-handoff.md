# 传智杯18：核验链真实四窗口硬停

基线 main@d4ac845。传智杯17已交棒，模型/0016独立PG17通过；核验durable接入/独立服务PG62零跳过、SQLite57通过5跳过。还没有硬停验收。先读本卡和 kernel-review.md，不重新全仓调查。

## 所有权

你唯一写：backend/app/tests/ops_hard_stop_worker.py、backend/app/tests/test_attempt_hard_stop.py、docs/evidence/20261007-OPS-01B-hard-stop/。可新建小型专属fixture helper但先报告文件名。禁止改服务/provider/模型/迁移/旧测试/正式清单。Codex只读风险复核，当前不启动另一个数据库测试；你唯一持有本轮自有cp_test夹具与child进程。终态交棒后停止写入，Codex再复跑最高风险窗口。

## 已固定接口和实现方法

- production核验入口 execute_application_verification_task(task_id, factory)，内部 DurableRequestObserver/AttemptService 已接入；provider为DeepSeekProvider+httpx.MockTransport，不启用任何真实网络。复用 test_application_verification 的 case、matching_db、model_answer/completion 等合成数据。
- 在独立 Python child 中 patch AttemptService._phase，只包装原方法并在指定阶段提交真实 marker 后永久等待；不要改生产源码。父进程跑 pytest fixture 新建pending核验任务，child使用父进程同一自有schema和taskId执行真正核验入口。
- 四窗：send_intent_committed（HTTP前）、response_observed（收到HTTP但receipt未提交）、receipt_committed（收据已提交但账目未提交）、ledger_committed（账目已提交但业务任务未终结）。这些phase都已真实接入服务短事务之后或receive之前。
- child mock HTTP计数文件只做计数，不提供恢复收据；child返回合成完成payload。父进程恢复只能读取数据库，不能用marker/计数文件回填usage。
- subprocess.Popen 父进程持有child句柄。硬停前核对：alive/pid、自有taskId/schema、随机nonce、实际进程创建时间（Windows GetProcessTimes 或已安装的进程库；不安装新库）、marker.phase。只终止这个child，禁止杀服务、系统进程或复用旧PID。不得用取消协程替代真实硬停。
- child启动时强制ai_external_enabled=False；数据库URL仅测试环境，校验postgresql+asyncpg，schema仅cp_test_<32hex>。连接后先assert current_schema，逐表检查实际namespace，再允许任何数据库操作。create_all必须checkfirst=False，防止search_path复用public。不要迁移/重启closure或生产。
- worker启动参数可用自有配置文件（包含合成local PG URL；不要把.env/真实密钥写入证据）；证据须脱敏，不输出真实凭据。

## 父进程验收断言

1. 每窗kill前后保留：child身份/nonce/阶段、HTTP计数、task claim、attempt状态、ledger事实数及可信计数。确保kill退出码真实、child已死、PG连接锁已释放。
2. 回收旧claim为FAILED/run_token=None（仅本次fixture任务，沿用test_b08的reap）；用原run_token、原owner/provider/model的 AttemptContext + AttemptService.reconcile 重复两次。
3. 前两窗：HTTP计数分别0/1，缺少持久可信收据，usage_unknown，usageKnown=False，没有伪零账目。后两窗：HTTP计数均1，可信123/45/cache17恢复恰好一次；最后窗已有账目重复恢复为零新增。
4. 每次恢复不再请求HTTP、不写业务analysis、不复活旧task。原应用report_snapshot完整hash不变。跨owner/run identity拒绝、receipt写入失败0重发已独立测试，此处聚焦真实kill。
5. SQLite可跳过PG硬停但必须明确skip理由；最终专属PG四参数零跳过。每次失败另存原始输出，不覆盖；commands/退出码/hash/自审/summary留档，一屏回报。

模型默认 Start Plan 免费Flash，高。不得自行切个人计划；不要Git提交/推送、真实模型/外发、改.env/业务库/P2 stash或历史清理。阻碍应回报具体缺口，不降低验收断言。
