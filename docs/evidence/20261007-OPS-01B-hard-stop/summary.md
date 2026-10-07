# OPS-01B 真实四窗口硬停验收记录（传智杯18）— 2026-10-07

基线：`main` 工作区，HEAD `cbb4b58`（含 d4ac845 核验 durable 接入）。本轮零 Git 提交，零 .env/业务库改动，未重启 closure/public 服务，未触碰正式清单、服务/provider/模型/迁移/旧测试。

## 交付文件（本轮唯一写入）

| 文件 | sha256 |
| --- | --- |
| `backend/app/tests/ops_hard_stop_worker.py` | f89e7d9a87a3c98a5cc1aded988f62747bc78f587d7c034180a5b700c1883ab9 |
| `backend/app/tests/test_attempt_hard_stop.py` | 35c20cf9ec9e9c1199b7bf84cc9a2242ffbf22dcd4d9ac7231826e986f155938 |

未新建第三文件：schema 以 `SELECT current_schema()` 现场核对，数据库 URL 从环境变量读取，无需独立 fixture helper。

## 命令与退出码（URL 已脱敏）

后端 venv：`backend/.venv/Scripts/python.exe`；工作目录 `backend/`。

```
ruff check app/tests/ops_hard_stop_worker.py app/tests/test_attempt_hard_stop.py   # exit 0
CAREERPROOF_TEST_DATABASE_URL='postgresql+asyncpg://<redacted-local-test-pg>' \
  python -u -m pytest app/tests/test_attempt_hard_stop.py -q --tb=short \
  -p no:cacheprovider --basetemp=.tmp-ops01b-hard-stop
```

| 运行 | 原始日志 | 结果 | 退出码 | sha256 |
| --- | --- | --- | --- | --- |
| 第1轮 | hard-stop-pg-first.raw.out | 4 failed（child 命名空间预检：`knowledge_chunks` 在共享 dev 库 public 中真实存在，检查集合过严；夹具建表集合=全部表减该表，已修正） | 1 | 3fc1d2a2…4bb00 |
| 第2轮 | hard-stop-pg-second.raw.out | 4 failed（暴露 venv `python.exe` 为转发启动器：Popen pid 与真实解释器 pid 不同；改为按 child 自报 pid 锁定真实 worker 进程，Windows 下用 NtQueryInformationProcess 验证父进程=启动器） | 1 | 026cdf7e…490f8 |
| 第3轮（终态） | hard-stop-pg-third.raw.out | **4 passed, 0 skipped** | **0** | 04085706…d7049794 |

每轮失败输出独立命名保存，未覆盖。

## 终态结果（专属 PG，四参数零跳过）

| 窗口 | 硬停时HTTP数 | 硬停时attempt状态 | 硬停时账目 | reconcile两次 | 恢复后 |
| --- | --- | --- | --- | --- | --- |
| send_intent_committed | 0 | in_flight 无收据 | 0条 | 0/0 | usage_unknown，usageKnown=False，无伪零账目 |
| response_observed | 1 | in_flight 收据未落库 | 0条 | 0/0 | 同上 |
| receipt_committed | 1 | received_unbooked 123/45/17 | 0条 | 1/0 | booked，账目恰好一条 123/45/17，usageKnown=True |
| ledger_committed | 1 | booked 123/45/17 | 1条 | 0/0 | 账目仍1条零新增，usageBooked=True |

每窗断言链：child 预检 current_schema+逐表 namespace（全部落在自有 `cp_test_<32hex>`）→ marker 核对（alive/pid/nonce/phase/taskId/schema/真实创建时间 GetProcessTimes/HTTP计数）→ `TerminateProcess` 真实杀 worker（持有句柄，WaitForSingleObject 后 GetExitCodeProcess，退出码非0；启动器随之退出）→ `FOR UPDATE NOWAIT` 证明任务/用户/attempt 行锁已释放 → b08 同款 reap（仅本 fixture 任务，FAILED/run_token=None）→ 原 run_token/owner/provider/model 的 `AttemptContext` + `AttemptService.reconcile` 两次 → 恢复零 HTTP（计数文件不变）、不写业务 analysis、任务不复活（application_verification 任务总数恒为1）、`report_snapshot` hash 前后一致。

SQLite 路径按卡明确 skip（理由写在测试内：跨进程行锁释放证明需要 PG）；本轮未触发。

## 自审

- 前两轮失败均已留存原始日志并定位根因，第三轮为终态；失败未降低任何验收断言，断言集只增未减。
- 真实硬停：终止的是 marker 中 child 自报的 worker pid（真实解释器进程），非协程取消、非仅杀启动器；父子关系经 NtQueryInformationProcess 核验。
- 恢复仅读 DB：reconcile/reap 全程无 provider 参与，HTTP 计数文件在 kill 后、两次 reconcile 后逐一断言不变；child 计数文件只做计数，父进程从不回填 usage。
- child 侧互锁：`ai_external_enabled=False` 强制 + `deepseek_api_key=None`；数据库 URL 校验 `postgresql+asyncpg://`、schema 校验 `cp_test_[0-9a-f]{32}`；任何数据操作前完成 current_schema 与全部建表 namespace 断言；provider 为 DeepSeekProvider+httpx.MockTransport 合成数据（复用 `model_answer`/`completion`），无真实网络。
- 未复用 public、未清理他人 schema（运行前后 `cp_test_*` 均为既有3个，本测自建自清）；运行后无孤儿 worker 进程、无 idle-in-transaction 连接。
- 证据已脱敏：三个原始日志与本文均无真实凭据；child 配置文件仅存于 pytest 临时目录。

## 交棒

本轮终态。后续 Codex 只读复核，建议复跑最高风险窗口 `response_observed`（HTTP 已应答但收据未落库）；Codex 不修改上述两个 tests 文件。交棒后本轮停止写入。
