# Codex独立审查与补边界

日期2026-10-09。ZCode传智杯20已在界面终态报告停止写入（标题自动改为“预算事务故障回归测试与证据补齐”）。交付原文件6项及受影响34通过2PG跳过；原summary与失败日志全部保留，原hash仅代表ZCode交付，后续源码由Codex补边界。

## 增强与实测

- 增加mark_intent提交前/提交后故障两个分支：两者实际0 HTTP；未持久intent可释放，持久intent即使测试私有计数知道未发送，也必须恢复unknown/held，不可把外部计数当可信收据。
- prepare已提交但调用方见异常的分支，增加终止旧租约后新服务实例reconcile两次；not_sent结束、预留释放、容量归零且不重发。
- book失败后改用原factory新建独立服务恢复，不复用故障代理对象；可信actual仍在、账目唯一、重复恢复0新增账目/HTTP。
- 修正文案：commit前rollback与commit后抛错覆盖两个持久结果，均不是实际asyncpg断连实验，不能宣称完整网络歧义验证。

独立目标8通过（codex-independent.raw.out），受影响五文件36通过2PG跳过（codex-affected.raw.out），Ruff通过。运行backend/.venv Python，`-p no:cacheprovider`及新的`.tmp-budget-fault-codex-20261009`、`.tmp-budget-fault-affected-codex-20261009`，测试退出码均0。原始输出已保留；不扩大为后端全量或PG通过。

## 剩余门槛

Docker恢复后当前源码专属PG预算/两条workflow、实际子进程8窗口首验与Codex独立风险复跑仍必须完成。当前测试未注入网络级COMMIT断连；若需要此结论须另有实际证据。最终依赖当前版本与权威公告核对/升级排序未完成。无真实模型、业务迁移、推送、部署、安装。
