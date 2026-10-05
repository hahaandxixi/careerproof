# E2E-01：按复杂度升级个人 GLM-5.3 的接续卡

Codex持有。用户2026-10-04明确允许复杂任务提前使用个人GLM-5.3；本卡涉及数据库/API/进程/构建隔离组合，采用该授权。必须新建任务，前任务确认停止后才接续。

1. 先核对`D:\jbcode\web ai\jianli`的Git status、HEAD、stash，读GOAL、当前接力、E2E原卡与隔离审查卡。前免费Flash已有seed_e2e.py、12项安全测试、Start/Stop脚本、next.config.mjs及证据草稿；先读diff，继续未完成处，不重复重写已经正确部分。
2. 文件所有权沿用原卡和审查卡扩展：seed、安全测试、Start/Stop、最小next.config/.gitignore及本任务证据目录；正式文档/任务卡由Codex持有，不动其他任务。
3. 首轮Codex8项基线通过，升级后12项仅为Flash自报，Codex尚未复核。审查卡含7项及第二版备注，均需核对：API目标与启动清单绑定、数据库query/run绑定、准确引用、A/A2同岗+B跨岗、完整日志退出码、健康等待与3001来源、存储/构建保护。
4. 已知高风险备注必须验证：ctypes HANDLE位宽及进程存活探测、PowerShell UTF8 BOM读取、IPv6 URL括号、自有PID与开始时间校验；不是仅修测试期望。关注部分失败遗留记录和父环境恢复。
5. 完成代码、目标/受影响回归、Ruff、PS解析、静态配置校验及review-agent自审，把原始脱敏输出和退出码写证据。依赖存在才用技能，不编造调用。聊天回报限一屏。
6. 本卡仍不实际CREATE DATABASE、Alembic或启动隔离服务；交Codex高风险复核后才放行。不开真实DeepSeek、不改.env/业务库/原演示投递，不提交/推送，不动P2 stash。
7. 如需扩大文件范围，报告依赖再等Codex裁决；发现没有现成安全方案时保留红灯并写清阻碍，不临时跳过或降级护栏。
