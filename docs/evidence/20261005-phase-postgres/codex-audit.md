# 阶段全量证据核对

2026-10-05，HEAD76dfd59。Codex读取实际完整PG输出与退出码：939 passed、零跳过、7 warnings、PYTEST_EXIT=0；前端153 pass、零失败/跳过；RUFF_EXIT=0、TSC_EXIT=0。16份源码/新测试SHA256逐项重新计算，与01-source-hashes.txt相同（SOURCE_HASH_MISMATCH_COUNT=0）。这批覆盖当前未提交岗位协议及前端改动，而非旧SQLite906基线。

最高风险真实迁移、并发锁和通用重试旁路已由Codex先行独立运行：growth-target-job/postgres.raw.out 18通过，ordinary-retry-pg.raw.out 1通过，以及先红后绿组合40通过/1跳过。全量由ZCode执行，本次审计未重复全量。

closure实际生产迁移/构建/重启已在closure-rebuild.raw.out记录终态SUCCESS=True EXIT=0，Mock且外发禁用；原next-env.d.ts和tsconfig.json恢复。阶段自动检查通过不代表学生三个真实页面场景、独立语义或企业整体已签收。

不删除来源不明的旧孤儿schema；只有确知本任务自有schema可由其夹具清理。本轮未操作学生浏览器、E2E数据或业务库。
