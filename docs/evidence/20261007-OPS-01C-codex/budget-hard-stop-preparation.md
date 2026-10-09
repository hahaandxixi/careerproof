# 两条预算链硬停准备检查点

日期：2026-10-09。这是测试准备提交，不是预算最终签收。

`test_attempt_hard_stop.py` 扩为核验/主匹配 × send_intent、response_observed、receipt_committed、ledger_committed 共8项。运行真实业务入口和固定MockTransport子进程；核对PID/父PID/创建时间/nonce后硬停。恢复须不重发HTTP、不产生业务报告、不改变原固定投递快照；未知收据保留held，可信收据保留actual并幂等入账。新增预算日锁释放探针与预留状态断言。

worker拒绝非本地careerproof、非专属cp_test schema、非法链/窗口/输入上限。状态标记先写pending，再原子替换，避免父进程读取半截JSON；回归检查父进程在发布前看到完整旧标记。

## 已运行

- 8项成功收集：`budget-hard-stop-collection.raw.out`，只证明收集成功。
- 原11项guard通过：`budget-hard-stop-guards.raw.out`。
- 新12项首跑因系统临时目录权限失败：`budget-hard-stop-guards-final.raw.out`（11通过、1初始化错误），保留原日志。
- 改用新的项目内basetemp重跑：`budget-hard-stop-guards-retry.raw.out`，12通过。命令：`.venv/Scripts/python.exe -m pytest app/tests/test_hard_stop_worker_guards.py -q -p no:cacheprovider --basetemp .tmp-budget-hard-stop-guards-20261009`。
- 四个修改测试/worker文件 Ruff 通过。

## 未完成

这8项尚未在PG执行，更未完成独立复跑。今日5432探测失败；旧Docker状态句柄66687已终态退出1，start79334/ps89484仍等待无输出。不能以CLI等待或历史PG通过证明引擎健康。恢复后先当前预算/两链PG门槛，再首跑8项并使用新的审计目录，Codex独立最高风险复验；出现失败先定位，不修改断言来迎合结果。

无真实模型、业务迁移、部署或推送。生产源码仍f14af62；本提交仅准备测试。后续依赖权威公告审计和升级排序仍未完成。
