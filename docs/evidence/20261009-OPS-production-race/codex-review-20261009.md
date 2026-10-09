# Codex 独立复核：生产入口并发测试准备

2026-10-09，基线 b1e824e。传智杯22已终态停止，精确 session `sess_05d2ef94-b7db-477a-9625-ce38e40b3c32` 的 finish=stop 见 `../20261007-OPS-01C-codex/z22-report-check-20261009.json`。当前唯一写入者为 Codex。

## 结论与边界

接受为可提交的测试准备检查点，**不签收 PostgreSQL 竞态或完整预算**。检查原身份锁调用保留、败方登记后立即尝试原锁，胜方在原锁内只等不依赖行锁的登记事件并观察真实 pg_blocking_pids；prepare 双方屏障在原函数外。信号量配置=2且惰性重建；User/Task/日预算 NOWAIT 失败均不豁免。两生产链同角色同 owner 双任务，跨角色不同 owner 隔离，未改生产授权边界。

ZCode 报告正文仍含旧版本“双方登记齐才进锁”及旧源码哈希，须以其 rev2 说明、最终源文件和本复核为准。这些编排结论来自代码检查，尚无 PG 运行证据。

## 独立加固与实测

- 逐收据结清可支持 K 次合法物理调用，但原断言未把实际 HTTP 数与 attempt 数相连。Codex 增加 `len(attempts)==http_calls>=1`，所有五处调用传入实际计数；匹配报告 trustedReceiptCount 与 gate.calls 相等，避免多请求漏账或报告漏计仍绿灯。
- 原 b 系列两 POST 失败日志保留；该轮第二次请求没有分类，原因**未确定**，不能断言必为合法 planning/repair，也未据此改生产源码。后续分类日志仅证明所记录运行为 analysis。每次物理请求账目不变量仍保留。
- 独立命令（backend）：`.venv/Scripts/python.exe -m pytest app/tests/test_ai_budget_production_race.py -q -rs -s -p no:cacheprovider --basetemp=.tmp-production-race-codex-final-20261009`，退出0，**1通过、3明确PG跳过**；原日志 `codex-independent-final-20261009.raw.out`。修改后首次独立运行同结果，另存 `codex-independent-20261009.raw.out`。
- `.venv/Scripts/ruff.exe check app/tests/test_ai_budget_production_race.py` 最终退出0，`codex-ruff-final-20261009.raw.out`；首次加固造成6处超长行已修正，原失败 `codex-ruff-20261009.raw.out` 未覆盖。
- 最终源码 SHA-256：`e8f2a38970f2df94a3924a0e4360595b520df9ee9540122d1ba02dbc67ecdd50`。
- 22:07:54 +08:00，独立 TCP 127.0.0.1:5432 探测2秒超时。没有再发 Docker CLI 查询、重启或清理 socket。

## 恢复后必须执行

1. 先确认 Docker Engine 与 PG 可用，使用现有安全 fixture 建随机 cp_test schema；本轮未使用业务库、public、真实模型、外发、安装或推送。
2. 实跑当前预算受影响PG专项及本文件3项生产入口PG测试，要求零跳过；保存完整命令/退出码/失败原文与 RACE-EVIDENCE backend、锁等待、HTTP、账目、快照证据。
3. 两条预算链真实8硬停窗口，随后 Codex 独立风险重放；SQLite和旧内核PG证据不替代这些门槛。
4. 若再次出现额外调用，保留分类与原始失败，按请求类别与生产策略调查；不能仅通过重复绿灯关闭原因未知项。

依赖最终排序已完成，尚未升级/部署。完整目标未完成；当前阻碍是已反复出现的 Docker 启动故障，恢复后从以上门槛继续，下一新ZCode任务编号23。
